from __future__ import annotations

import os
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

_request_base_url: ContextVar[str | None] = ContextVar("_request_base_url", default=None)

DEFAULT_API_BASE_URL = "https://poliedro-api.iden.is"


def bind_request_base_url_from_request(request: Request) -> Token[str | None]:
    """Associa a URL pública da requisição ao contexto (domínio customizado no Render)."""
    return _request_base_url.set(str(request.base_url).rstrip("/"))


def reset_request_base_url(token: Token[str | None]) -> None:
    _request_base_url.reset(token)


def api_base_url() -> str:
    """
    URL pública da API para metadados OAuth/MCP e OpenAPI.

    Prioridade: API_BASE_URL → Host da requisição → RENDER_EXTERNAL_URL → default.
    """
    configured = os.getenv("API_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured

    from_request = _request_base_url.get()
    if from_request:
        return from_request

    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return render_url

    return DEFAULT_API_BASE_URL


def mcp_base_url() -> str:
    return f"{api_base_url()}/mcp"
