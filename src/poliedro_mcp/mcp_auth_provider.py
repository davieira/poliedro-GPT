from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .api_base import mcp_base_url
from .profile_discovery import decode_jwt_claims

AUTH_CODE_TTL = 120
PENDING_LOGIN_TTL = 600
ACCESS_TOKEN_TTL = 3600
DEFAULT_SCOPES = ["openid", "profile", "email"]


@dataclass
class _PendingLogin:
    client: OAuthClientInformationFull
    params: AuthorizationParams
    created_at: float


@dataclass
class _CodePayload:
    code: AuthorizationCode
    poliedro_access_token: str
    poliedro_refresh_token: str | None
    expires_in: int


class PoliedroMcpAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """OAuth do MCP remoto — emite o JWT do Poliedro como access_token."""

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, _PendingLogin] = {}
        self._codes: dict[str, _CodePayload] = {}
        self._refresh: dict[str, tuple[RefreshToken, str | None]] = {}
        self._access: dict[str, AccessToken] = {}

    def _purge_pending(self) -> None:
        now = time.time()
        expired = [
            key
            for key, entry in self._pending.items()
            if now - entry.created_at > PENDING_LOGIN_TTL
        ]
        for key in expired:
            self._pending.pop(key, None)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise RegistrationError("invalid_client_metadata", "client_id ausente")
        if not client_info.redirect_uris:
            raise RegistrationError("invalid_client_metadata", "redirect_uris é obrigatório")

        if client_info.scope is None:
            client_info = client_info.model_copy(
                update={"scope": " ".join(DEFAULT_SCOPES)}
            )
        self._clients[client_info.client_id] = client_info

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        self._purge_pending()
        pending_id = secrets.token_urlsafe(24)
        self._pending[pending_id] = _PendingLogin(
            client=client,
            params=params,
            created_at=time.time(),
        )
        query = urlencode({"pending": pending_id})
        return f"{mcp_base_url()}/login?{query}"

    def get_pending(self, pending_id: str) -> _PendingLogin | None:
        self._purge_pending()
        entry = self._pending.get(pending_id)
        if entry is None:
            return None
        if time.time() - entry.created_at > PENDING_LOGIN_TTL:
            self._pending.pop(pending_id, None)
            return None
        return entry

    def complete_login(
        self,
        pending_id: str,
        *,
        poliedro_access_token: str,
        poliedro_refresh_token: str | None,
        expires_in: int,
    ) -> str:
        entry = self.get_pending(pending_id)
        if entry is None:
            raise ValueError("Sessão de login expirada. Tente novamente.")

        client = entry.client
        params = entry.params
        code_str = secrets.token_urlsafe(32)
        now = time.time()

        auth_code = AuthorizationCode(
            code=code_str,
            scopes=params.scopes or DEFAULT_SCOPES,
            expires_at=now + AUTH_CODE_TTL,
            client_id=client.client_id or "",
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        self._codes[code_str] = _CodePayload(
            code=auth_code,
            poliedro_access_token=poliedro_access_token,
            poliedro_refresh_token=poliedro_refresh_token,
            expires_in=expires_in,
        )
        self._pending.pop(pending_id, None)

        return construct_redirect_uri(
            str(params.redirect_uri),
            code=code_str,
            state=params.state,
        )

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        payload = self._codes.get(authorization_code)
        if payload is None:
            return None
        if payload.code.client_id != client.client_id:
            return None
        if time.time() > payload.code.expires_at:
            self._codes.pop(authorization_code, None)
            return None
        return payload.code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        payload = self._codes.pop(authorization_code.code, None)
        if payload is None:
            raise TokenError("invalid_grant", "authorization code inválido")

        access = AccessToken(
            token=payload.poliedro_access_token,
            client_id=client.client_id or "",
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + payload.expires_in,
        )
        self._access[payload.poliedro_access_token] = access

        refresh_key: str | None = None
        if payload.poliedro_refresh_token:
            refresh_key = secrets.token_urlsafe(32)
            self._refresh[refresh_key] = (
                RefreshToken(
                    token=refresh_key,
                    client_id=client.client_id or "",
                    scopes=authorization_code.scopes,
                ),
                payload.poliedro_refresh_token,
            )

        return OAuthToken(
            access_token=payload.poliedro_access_token,
            token_type="Bearer",
            expires_in=payload.expires_in,
            refresh_token=refresh_key,
            scope=" ".join(authorization_code.scopes),
        )

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        entry = self._refresh.get(refresh_token)
        if entry is None:
            return None
        token, _ = entry
        if token.client_id != client.client_id:
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        entry = self._refresh.get(refresh_token.token)
        if entry is None:
            raise TokenError("invalid_grant", "refresh_token inválido")

        _, poliedro_refresh = entry
        if not poliedro_refresh:
            raise TokenError("invalid_grant", "refresh_token indisponível")

        from .auth import refresh_access_token
        from .user_context import get_base_config

        tokens = refresh_access_token(get_base_config()["base_url"], poliedro_refresh)
        new_access = tokens["access_token"]
        new_poliedro_refresh = tokens.get("refresh_token") or poliedro_refresh
        expires_in = int(tokens.get("expires_in") or ACCESS_TOKEN_TTL)

        self._access[new_access] = AccessToken(
            token=new_access,
            client_id=client.client_id or "",
            scopes=scopes,
            expires_at=int(time.time()) + expires_in,
        )

        new_refresh_key = secrets.token_urlsafe(32)
        self._refresh.pop(refresh_token.token, None)
        self._refresh[new_refresh_key] = (
            RefreshToken(
                token=new_refresh_key,
                client_id=client.client_id or "",
                scopes=scopes,
            ),
            new_poliedro_refresh,
        )

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=expires_in,
            refresh_token=new_refresh_key,
            scope=" ".join(scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        stored = self._access.get(token)
        if stored is not None:
            if stored.expires_at and time.time() > stored.expires_at:
                self._access.pop(token, None)
                return None
            return stored

        try:
            claims = decode_jwt_claims(token)
            exp = claims.get("exp")
            if exp and time.time() > float(exp):
                return None
        except Exception:
            return None

        return AccessToken(
            token=token,
            client_id="poliedro",
            scopes=DEFAULT_SCOPES,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._access.pop(token.token, None)
        else:
            self._refresh.pop(token.token, None)


_provider: PoliedroMcpAuthProvider | None = None


def get_mcp_auth_provider() -> PoliedroMcpAuthProvider:
    global _provider
    if _provider is None:
        _provider = PoliedroMcpAuthProvider()
    return _provider
