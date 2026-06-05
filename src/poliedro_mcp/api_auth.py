from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_required_api_key() -> str:
    api_key = os.getenv("API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "API_KEY não configurada. Defina a variável de ambiente no Render."
        )
    return api_key


def verify_api_key(api_key_header: str | None = Security(_api_key_header)) -> None:
    expected = get_required_api_key()

    if not api_key_header or not secrets.compare_digest(api_key_header, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente.",
        )
