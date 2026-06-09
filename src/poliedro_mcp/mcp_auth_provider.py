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
from pydantic import AnyUrl

from .api_base import api_base_url
from .mcp_oauth_tokens import (
    AUTH_CODE_TTL,
    mint_auth_code_token,
    mint_client_id,
    mint_pending_token,
    verify_payload,
)
from .profile_discovery import decode_jwt_claims

ACCESS_TOKEN_TTL = 3600
DEFAULT_SCOPES = ["openid", "profile", "email"]


@dataclass
class _PendingLogin:
    client: OAuthClientInformationFull
    params: AuthorizationParams


@dataclass
class _CodePayload:
    code: AuthorizationCode
    poliedro_access_token: str
    poliedro_refresh_token: str | None
    expires_in: int


class PoliedroMcpAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """OAuth do MCP remoto — tokens assinados (stateless) para sobreviver a restarts."""

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._refresh: dict[str, tuple[RefreshToken, str | None]] = {}
        self._access: dict[str, AccessToken] = {}
        self._used_code_jtis: dict[str, float] = {}

    def _purge_used_codes(self) -> None:
        now = time.time()
        expired = [key for key, seen_at in self._used_code_jtis.items() if now - seen_at > AUTH_CODE_TTL]
        for key in expired:
            self._used_code_jtis.pop(key, None)

    def _client_to_dict(self, client: OAuthClientInformationFull) -> dict[str, Any]:
        data = client.model_dump(mode="json", exclude_none=True)
        data.pop("client_id", None)
        return data

    def _client_from_dict(self, client_id: str, data: dict[str, Any]) -> OAuthClientInformationFull:
        payload = dict(data)
        payload["client_id"] = client_id
        return OAuthClientInformationFull.model_validate(payload)

    def _restore_client(self, client_id: str) -> OAuthClientInformationFull | None:
        cached = self._clients.get(client_id)
        if cached is not None:
            return cached
        try:
            data = verify_payload(client_id, "mcp_client")
            data.pop("typ", None)
            data.pop("exp", None)
            client = self._client_from_dict(client_id, data)
            self._clients[client_id] = client
            return client
        except Exception:
            return None

    def _parse_code_token(self, code: str) -> _CodePayload | None:
        try:
            data = verify_payload(code, "mcp_code")
        except Exception:
            return None

        jti = data.get("jti")
        if not jti:
            return None

        self._purge_used_codes()
        if jti in self._used_code_jtis:
            return None

        client = self._restore_client(str(data["client_id"]))
        if client is None:
            return None

        auth_code = AuthorizationCode(
            code=code,
            scopes=data.get("scopes") or DEFAULT_SCOPES,
            expires_at=float(data["expires_at"]),
            client_id=client.client_id or "",
            code_challenge=data["code_challenge"],
            redirect_uri=AnyUrl(data["redirect_uri"]),
            redirect_uri_provided_explicitly=bool(data.get("redirect_uri_provided_explicitly")),
            resource=data.get("resource"),
        )
        return _CodePayload(
            code=auth_code,
            poliedro_access_token=data["poliedro_access_token"],
            poliedro_refresh_token=data.get("poliedro_refresh_token"),
            expires_in=int(data.get("expires_in") or ACCESS_TOKEN_TTL),
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._restore_client(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.redirect_uris:
            raise RegistrationError("invalid_client_metadata", "redirect_uris é obrigatório")

        if client_info.scope is None:
            client_info.scope = " ".join(DEFAULT_SCOPES)

        stateless_id = mint_client_id(self._client_to_dict(client_info))
        client_info.client_id = stateless_id
        self._clients[stateless_id] = client_info

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        client_data = self._client_to_dict(client)
        client_data["client_id"] = client.client_id
        pending = mint_pending_token(
            client_data,
            params.model_dump(mode="json"),
        )
        query = urlencode({"pending": pending})
        return f"{api_base_url()}/mcp/login?{query}"

    def get_pending(self, pending_id: str) -> _PendingLogin | None:
        try:
            data = verify_payload(pending_id, "mcp_pending")
            client_blob = dict(data["client"])
            client_id = str(client_blob.pop("client_id", "") or "")
            if not client_id:
                client_id = mint_client_id(client_blob)
            client = self._client_from_dict(client_id, client_blob)
            params = AuthorizationParams.model_validate(data["params"])
            self._clients[client_id] = client
            return _PendingLogin(client=client, params=params)
        except Exception:
            return None

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
        now = time.time()

        client_data = self._client_to_dict(client)
        client_data["client_id"] = client.client_id
        code_str = mint_auth_code_token(
            {
                "client_id": client.client_id,
                "client": client_data,
                "scopes": params.scopes or DEFAULT_SCOPES,
                "expires_at": now + AUTH_CODE_TTL,
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": params.resource,
                "poliedro_access_token": poliedro_access_token,
                "poliedro_refresh_token": poliedro_refresh_token,
                "expires_in": expires_in,
            }
        )

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
        payload = self._parse_code_token(authorization_code)
        if payload is None:
            return None
        if payload.code.client_id != client.client_id:
            return None
        if time.time() > payload.code.expires_at:
            return None
        return payload.code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        payload = self._parse_code_token(authorization_code.code)
        if payload is None:
            raise TokenError("invalid_grant", "authorization code inválido")

        data = verify_payload(authorization_code.code, "mcp_code")
        jti = str(data.get("jti") or "")
        self._used_code_jtis[jti] = time.time()

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
