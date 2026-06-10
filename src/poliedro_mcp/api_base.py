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


def configured_api_base_url() -> str:
    """
    URL estável para inicializar OAuth/MCP (lifespan, singleton do servidor).

    Não usa o Host da requisição — evita recriar o MCP mid-flight e quebrar o task group.
    """
    configured = os.getenv("API_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured

    return DEFAULT_API_BASE_URL


def api_base_url() -> str:
    """
    URL pública efetiva para metadados OAuth/MCP e OpenAPI.

    Prioridade: API_BASE_URL → Host da requisição → default.
    """
    configured = os.getenv("API_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured

    from_request = _request_base_url.get()
    if from_request:
        return from_request

    return DEFAULT_API_BASE_URL


def mcp_base_url(*, stable: bool = False) -> str:
    base = configured_api_base_url() if stable else api_base_url()
    return f"{base}/mcp"
