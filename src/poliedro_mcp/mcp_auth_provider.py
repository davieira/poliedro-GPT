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
from .logger import logger
from .mcp_oauth_tokens import (
    AUTH_CODE_TTL,
    MAX_AUTH_CODE_URL_LEN,
    extract_poliedro_access_token,
    mint_auth_code_token,
    mint_client_id,
    mint_pending_token,
    mint_session_access_token,
    verify_payload,
)

CLAUDE_REDIRECT_URIS = (
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
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
        self._codes: dict[str, tuple[float, _CodePayload]] = {}
        self._used_code_jtis: dict[str, float] = {}

    def _purge_used_jtis(self) -> None:
        now = time.time()
        expired = [key for key, seen_at in self._used_code_jtis.items() if now - seen_at > AUTH_CODE_TTL]
        for key in expired:
            self._used_code_jtis.pop(key, None)

    def _purge_expired_codes(self) -> None:
        now = time.time()
        expired = [
            key
            for key, (created_at, _) in self._codes.items()
            if now - created_at > AUTH_CODE_TTL
        ]
        for key in expired:
            self._codes.pop(key, None)

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

    def _build_code_payload(
        self,
        *,
        code: str,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
        poliedro_access_token: str,
        poliedro_refresh_token: str | None,
        expires_in: int,
        expires_at: float,
    ) -> _CodePayload:
        auth_code = AuthorizationCode(
            code=code,
            scopes=params.scopes or DEFAULT_SCOPES,
            expires_at=expires_at,
            client_id=client.client_id or "",
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        return _CodePayload(
            code=auth_code,
            poliedro_access_token=poliedro_access_token,
            poliedro_refresh_token=poliedro_refresh_token,
            expires_in=expires_in,
        )

    def _load_code_payload(self, authorization_code: str) -> _CodePayload | None:
        self._purge_expired_codes()
        entry = self._codes.get(authorization_code)
        if entry is not None:
            created_at, payload = entry
            if time.time() - created_at > AUTH_CODE_TTL:
                self._codes.pop(authorization_code, None)
                return None
            return payload

        try:
            data = verify_payload(authorization_code, "mcp_code")
        except Exception:
            return None

        jti = str(data.get("jti") or "")
        if not jti:
            return None
        self._purge_used_jtis()
        if jti in self._used_code_jtis:
            return None

        client = self._restore_client(str(data.get("client_id") or ""))
        if client is None:
            return None

        params = AuthorizationParams(
            state=None,
            scopes=data.get("scopes") or DEFAULT_SCOPES,
            code_challenge=data["code_challenge"],
            redirect_uri=AnyUrl(data["redirect_uri"]),
            redirect_uri_provided_explicitly=bool(data.get("redirect_uri_provided_explicitly")),
            resource=data.get("resource"),
        )
        return self._build_code_payload(
            code=authorization_code,
            client=client,
            params=params,
            poliedro_access_token=str(data.get("poliedro_access_token") or ""),
            poliedro_refresh_token=data.get("poliedro_refresh_token"),
            expires_in=int(data.get("expires_in") or ACCESS_TOKEN_TTL),
            expires_at=float(data.get("exp") or time.time()),
        )

    def _resolve_poliedro_access_token(self, payload: _CodePayload) -> str:
        if payload.poliedro_access_token:
            return payload.poliedro_access_token

        if payload.poliedro_refresh_token:
            from .auth import LoginError, refresh_access_token
            from .user_context import get_base_config

            try:
                tokens = refresh_access_token(
                    get_base_config()["base_url"],
                    payload.poliedro_refresh_token,
                )
                return str(tokens["access_token"])
            except LoginError as exc:
                raise TokenError("invalid_grant", str(exc)) from exc

        raise TokenError("invalid_grant", "token do Poliedro indisponível")

    def _issue_oauth_token(
        self,
        client: OAuthClientInformationFull,
        payload: _CodePayload,
        scopes: list[str],
    ) -> OAuthToken:
        poliedro_access = self._resolve_poliedro_access_token(payload)
        expires_in = payload.expires_in
        session_access = mint_session_access_token(poliedro_access, expires_in=expires_in)

        self._access[session_access] = AccessToken(
            token=poliedro_access,
            client_id=client.client_id or "",
            scopes=scopes,
            expires_at=int(time.time()) + expires_in,
        )

        refresh_key: str | None = None
        if payload.poliedro_refresh_token:
            refresh_key = secrets.token_urlsafe(32)
            self._refresh[refresh_key] = (
                RefreshToken(
                    token=refresh_key,
                    client_id=client.client_id or "",
                    scopes=scopes,
                ),
                payload.poliedro_refresh_token,
            )

        return OAuthToken(
            access_token=session_access,
            token_type="Bearer",
            expires_in=expires_in,
            refresh_token=refresh_key,
            scope=" ".join(scopes),
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._restore_client(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.redirect_uris:
            raise RegistrationError("invalid_client_metadata", "redirect_uris é obrigatório")

        if client_info.scope is None:
            client_info.scope = " ".join(DEFAULT_SCOPES)

        redirect_uris = {str(uri) for uri in (client_info.redirect_uris or [])}
        redirect_uris.update(CLAUDE_REDIRECT_URIS)
        client_info.redirect_uris = [AnyUrl(uri) for uri in sorted(redirect_uris)]

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

        code_str = secrets.token_urlsafe(32)
        code_payload = self._build_code_payload(
            code=code_str,
            client=client,
            params=params,
            poliedro_access_token=poliedro_access_token,
            poliedro_refresh_token=poliedro_refresh_token,
            expires_in=expires_in,
            expires_at=now + AUTH_CODE_TTL,
        )
        self._codes[code_str] = (now, code_payload)

        redirect_url = construct_redirect_uri(
            str(params.redirect_uri),
            code=code_str,
            state=params.state,
        )
        logger.info(
            "MCP OAuth: login OK, redirect %d chars (code %d chars)",
            len(redirect_url),
            len(code_str),
        )

        return redirect_url

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        payload = self._load_code_payload(authorization_code)
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
        memory_entry = self._codes.pop(authorization_code.code, None)
        if memory_entry is None:
            logger.warning("MCP OAuth: code não encontrado (expirou ou outra instância)")
            raise TokenError("invalid_grant", "authorization code inválido ou expirado")
        _, payload = memory_entry

        if payload.code.client_id != client.client_id:
            raise TokenError("invalid_grant", "authorization code inválido")

        try:
            token = self._issue_oauth_token(
                client,
                payload,
                authorization_code.scopes,
            )
            logger.info("MCP OAuth: token emitido com sucesso")
            return token
        except TokenError:
            raise
        except Exception as exc:
            logger.exception("MCP OAuth: falha ao emitir token")
            raise TokenError("invalid_grant", f"Não foi possível emitir token: {exc}") from exc

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

        session_access = mint_session_access_token(new_access, expires_in=expires_in)
        self._access[session_access] = AccessToken(
            token=new_access,
            client_id=client.client_id or "",
            scopes=scopes,
            expires_at=int(time.time()) + expires_in,
        )

        return OAuthToken(
            access_token=session_access,
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

        poliedro_token = extract_poliedro_access_token(token)
        if poliedro_token:
            try:
                claims = decode_jwt_claims(poliedro_token)
                exp = claims.get("exp")
                if exp and time.time() > float(exp):
                    return None
            except Exception:
                return None
            return AccessToken(
                token=poliedro_token,
                client_id="poliedro",
                scopes=DEFAULT_SCOPES,
            )

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
