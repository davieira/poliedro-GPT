from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from .logger import logger
from .services import PoliedroService

API_PREFIX = "/api/v1"
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_required_api_key() -> str:
    api_key = os.getenv("API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "API_KEY não configurada. Defina a variável de ambiente no Render."
        )
    return api_key


def verify_api_key(api_key_header: str | None = Security(_api_key_header)) -> None:
    expected = _get_required_api_key()
    if not api_key_header or not secrets.compare_digest(api_key_header, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente.",
        )


def _service() -> PoliedroService:
    return PoliedroService()


def _handle_service_error(exc: Exception) -> JSONResponse:
    logger.exception("Erro ao executar operação Poliedro")
    if isinstance(exc, FileNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": str(exc)},
        )
    if isinstance(exc, RuntimeError):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": str(exc)},
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Erro interno ao consultar o Poliedro."},
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("API Poliedro iniciando (porta=%s)", os.getenv("PORT", "8000"))
    yield
    logger.info("API Poliedro encerrando")


app = FastAPI(
    title="Poliedro API",
    description=(
        "API REST não oficial para consultar boletim, mensagens e calendário "
        "do portal Poliedro/P+. Projetada para uso com ChatGPT Actions."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "ApiKeyAuth"
    ] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Chave definida na variável API_KEY do Render.",
    }
    for path, methods in schema.get("paths", {}).items():
        if path.startswith(API_PREFIX):
            for operation in methods.values():
                operation["security"] = [{"ApiKeyAuth": []}]

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    """Endpoint público para health check do Render."""
    return {
        "service": "poliedro-api",
        "status": "ok",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/health", tags=["meta"])
def public_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{API_PREFIX}/health", tags=["poliedro"])
def poliedro_health(
    _: None = Depends(verify_api_key),
) -> dict[str, Any]:
    """Verifica se a API está configurada e consegue acessar o Poliedro."""
    try:
        return _service().health_check()
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/grades", tags=["poliedro"])
def get_grades(_: None = Depends(verify_api_key)) -> Any:
    """Consulta o boletim/notas do aluno configurado no portal Poliedro/P+."""
    try:
        return _service().get_grades()
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/messages", tags=["poliedro"])
def get_messages(
    status_filter: str = Query(
        default="UNREAD",
        alias="status",
        description="Status das mensagens: UNREAD ou READ.",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    _: None = Depends(verify_api_key),
) -> Any:
    """Consulta mensagens/notificações do portal Poliedro/P+."""
    try:
        return _service().get_messages(status=status_filter, limit=limit, page=page)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/messages/unread", tags=["poliedro"])
def get_unread_messages(
    limit: int = Query(default=50, ge=1, le=100),
    _: None = Depends(verify_api_key),
) -> Any:
    """Consulta mensagens/notificações não lidas do portal Poliedro/P+."""
    try:
        return _service().get_messages(status="UNREAD", limit=limit)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/next", tags=["poliedro"])
def get_next_events(_: None = Depends(verify_api_key)) -> Any:
    """Consulta próximos eventos do calendário escolar Poliedro/P+."""
    try:
        return _service().get_next_events()
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/week", tags=["poliedro"])
def get_week_events(
    date: str | None = Query(
        default=None,
        description="Data de referência no formato YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    _: None = Depends(verify_api_key),
) -> Any:
    """Consulta eventos da semana. Se date omitido, usa a data atual."""
    try:
        return _service().get_week_events(date=date)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/month", tags=["poliedro"])
def get_month_events(
    date: str | None = Query(
        default=None,
        description="Data de referência no formato YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    _: None = Depends(verify_api_key),
) -> Any:
    """Consulta eventos do mês. Se date omitido, usa a data atual."""
    try:
        return _service().get_month_events(date=date)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/year", tags=["poliedro"])
def get_year_events(
    date: str | None = Query(
        default=None,
        description="Data de referência no formato YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    _: None = Depends(verify_api_key),
) -> Any:
    """Consulta eventos do ano. Se date omitido, usa o ano atual."""
    try:
        return _service().get_year_events(date=date)
    except Exception as exc:
        return _handle_service_error(exc)


def run() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("poliedro_mcp.api:app", host="0.0.0.0", port=port)
