from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

CLIENT_ID_TTL = 60 * 60 * 24 * 30
PENDING_TTL = 600
AUTH_CODE_TTL = 120
SESSION_TTL = 3600
LOGIN_CHOICE_TTL = 600
MAX_AUTH_CODE_URL_LEN = 2000


@dataclass(frozen=True)
class SessionContext:
    access_token: str
    school_id: int | None = None
    dependent_id: int | None = None


@dataclass(frozen=True)
class LoginChoice:
    access_token: str
    refresh_token: str | None
    expires_in: int
    username: str
    school_id: int | None = None
    dependent_id: int | None = None


def _secret() -> bytes:
    secret = os.getenv("OAUTH_CLIENT_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "OAUTH_CLIENT_SECRET não configurada. "
            "Defina no Render para o OAuth do MCP remoto."
        )
    return secret.encode()


def sign_payload(payload: dict[str, Any], *, ttl: int) -> str:
    data = dict(payload)
    data["exp"] = int(time.time()) + ttl
    body = base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
    ).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_payload(token: str, expected_type: str) -> dict[str, Any]:
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError("token inválido") from exc

    expected_sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("assinatura inválida")

    padded = body + "=" * (-len(body) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded))
    if data.get("typ") != expected_type:
        raise ValueError("tipo de token inválido")
    if int(data.get("exp") or 0) < time.time():
        raise ValueError("token expirado")
    return data


def mint_client_id(client_data: dict[str, Any]) -> str:
    return sign_payload({"typ": "mcp_client", **client_data}, ttl=CLIENT_ID_TTL)


def mint_pending_token(client_data: dict[str, Any], params_data: dict[str, Any]) -> str:
    return sign_payload(
        {
            "typ": "mcp_pending",
            "client": client_data,
            "params": params_data,
            "jti": secrets.token_urlsafe(16),
        },
        ttl=PENDING_TTL,
    )


def mint_auth_code_token(code_data: dict[str, Any]) -> str:
    return sign_payload(
        {"typ": "mcp_code", "jti": secrets.token_urlsafe(16), **code_data},
        ttl=AUTH_CODE_TTL,
    )


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def mint_session_access_token(
    poliedro_access_token: str,
    *,
    expires_in: int,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> str:
    payload: dict[str, Any] = {"typ": "mcp_session", "pt": poliedro_access_token}
    if school_id is not None:
        payload["sid"] = int(school_id)
    if dependent_id is not None:
        payload["did"] = int(dependent_id)
    return sign_payload(payload, ttl=expires_in)


def parse_session_context(session_or_jwt: str) -> SessionContext | None:
    try:
        data = verify_payload(session_or_jwt, "mcp_session")
    except Exception:
        return None
    value = data.get("pt")
    if not value:
        return None
    return SessionContext(
        access_token=str(value),
        school_id=_as_optional_int(data.get("sid")),
        dependent_id=_as_optional_int(data.get("did")),
    )


def extract_poliedro_access_token(session_or_jwt: str) -> str | None:
    parsed = parse_session_context(session_or_jwt)
    return parsed.access_token if parsed else None


def mint_login_choice_token(
    *,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    username: str,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> str:
    payload: dict[str, Any] = {
        "typ": "login_choice",
        "pt": access_token,
        "exp_in": int(expires_in),
        "username": username,
    }
    if refresh_token:
        payload["rt"] = refresh_token
    if school_id is not None:
        payload["sid"] = int(school_id)
    if dependent_id is not None:
        payload["did"] = int(dependent_id)
    return sign_payload(payload, ttl=LOGIN_CHOICE_TTL)


def parse_login_choice_token(token: str) -> LoginChoice | None:
    try:
        data = verify_payload(token, "login_choice")
    except Exception:
        return None
    access_token = data.get("pt")
    username = data.get("username")
    if not access_token or not username:
        return None
    return LoginChoice(
        access_token=str(access_token),
        refresh_token=str(data["rt"]) if data.get("rt") else None,
        expires_in=int(data.get("exp_in") or SESSION_TTL),
        username=str(username),
        school_id=_as_optional_int(data.get("sid")),
        dependent_id=_as_optional_int(data.get("did")),
    )

