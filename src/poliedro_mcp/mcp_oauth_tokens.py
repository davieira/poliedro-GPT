from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

CLIENT_ID_TTL = 60 * 60 * 24 * 30
PENDING_TTL = 600
AUTH_CODE_TTL = 120


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
        {
            "typ": "mcp_code",
            "jti": secrets.token_urlsafe(16),
            **code_data,
        },
        ttl=AUTH_CODE_TTL,
    )
