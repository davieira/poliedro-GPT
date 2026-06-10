from __future__ import annotations

import json
import os
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .auth import LoginError
from .logger import logger
from .api_base import api_base_url, bind_request_base_url_from_request, configured_api_base_url, reset_request_base_url
from .mcp_remote import get_mcp_session_manager, get_mcp_starlette_app, router as mcp_router
from .oauth_proxy import router as oauth_router
from .profile_discovery import ProfileChoiceRequired, ProfileDiscoveryError
from .privacy_policy import privacy_policy_html
from .user_context import get_service, login_and_build_profile

API_PREFIX = "/api/v1"
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_poliedro_bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(description="Usuário do P+ (sem @p4ed.com)")
    password: str = Field(description="Senha do portal P+")
    school_id: int | None = Field(
        default=None,
        description="ID da escola, quando a conta tem mais de uma.",
    )
    dependent_id: int | None = Field(
        default=None,
        description="ID do dependente, para contas de responsável com vários filhos.",
    )


class UserContext:
    def __init__(
        self,
        access_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> None:
        self.access_token = access_token
        self.school_id = school_id
        self.dependent_id = dependent_id


def _configured_api_key() -> str:
    return os.getenv("API_KEY", "").strip()


def verify_api_access(
    api_key_header: str | None = Security(_api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Depends(_poliedro_bearer),
) -> None:
    """
    Aceita Bearer token (OAuth ChatGPT / login) ou X-API-Key (modo legado).
    """
    if credentials and credentials.credentials:
        return

    expected = _configured_api_key()
    if expected and api_key_header and secrets.compare_digest(api_key_header, expected):
        return

    if expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Faça login via OAuth ou envie X-API-Key válida.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Faça login via OAuth para continuar.",
    )


def verify_api_key(api_key_header: str | None = Security(_api_key_header)) -> None:
    expected = _configured_api_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY não configurada no servidor.",
        )
    if not api_key_header or not secrets.compare_digest(api_key_header, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida ou ausente.",
        )


def resolve_user_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_poliedro_bearer),
    school_id: int | None = Query(
        default=None,
        description="ID da escola (quando a conta tem mais de uma).",
    ),
    dependent_id: int | None = Query(
        default=None,
        description="ID do dependente (contas de responsável).",
    ),
) -> UserContext:
    token = credentials.credentials if credentials else None
    return UserContext(
        access_token=token,
        school_id=school_id,
        dependent_id=dependent_id,
    )


def _service_for(ctx: UserContext):
    return get_service(
        ctx.access_token,
        school_id=ctx.school_id,
        dependent_id=ctx.dependent_id,
    )


def _handle_service_error(exc: Exception) -> JSONResponse:
    logger.exception("Erro ao executar operação Poliedro")

    if isinstance(exc, ProfileChoiceRequired):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "escolha_necessaria",
                "tipo": exc.choice_type,
                "opcoes": exc.options,
                "detail": str(exc),
            },
        )

    if isinstance(exc, ProfileDiscoveryError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(exc)},
        )

    if isinstance(exc, LoginError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": str(exc)},
        )

    if isinstance(exc, FileNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": str(exc),
                "hint": (
                    "Envie Authorization: Bearer <token_poliedro> ou "
                    "configure POLIEDRO_CONFIG_JSON / config.json."
                ),
            },
        )

    if isinstance(exc, json.JSONDecodeError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": (
                    "POLIEDRO_CONFIG_JSON inválido. "
                    "Cole o JSON em uma única linha, sem aspas extras."
                ),
                "detail": str(exc),
            },
        )

    if isinstance(exc, (RuntimeError, KeyError)):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": str(exc)},
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Erro interno ao consultar o Poliedro.", "detail": str(exc)},
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("API Poliedro iniciando (porta=%s)", os.getenv("PORT", "8000"))
    session_manager = get_mcp_session_manager()
    async with session_manager.run():
        yield
    logger.info("API Poliedro encerrando")


app = FastAPI(
    title="Poliedro API",
    description=(
        "API REST não oficial para consultar boletim, mensagens e calendário "
        "do portal Poliedro/P+. Suporta múltiplos usuários via token JWT do P+."
    ),
    version="0.5.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


def _chatgpt_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """ChatGPT Actions exige type=object com properties explícitas."""
    if "$ref" in schema:
        return schema
    if schema.get("type") == "object":
        fixed = dict(schema)
        fixed.setdefault("properties", {})
        fixed.pop("additionalProperties", None)
        return fixed
    return {"type": "object", "properties": {}}


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
    base = configured_api_base_url()
    schema["servers"] = [{"url": base}]
    schema["paths"] = {
        path: methods
        for path, methods in schema.get("paths", {}).items()
        if path.startswith(API_PREFIX) and path != f"{API_PREFIX}/auth/login"
    }

    oauth2 = {
        "type": "oauth2",
        "flows": {
            "authorizationCode": {
                "authorizationUrl": f"{base}/oauth/authorize",
                "tokenUrl": f"{base}/oauth/token",
                "scopes": {
                    "openid": "Identificação do usuário P+",
                    "profile": "Perfil do aluno/responsável",
                    "email": "E-mail P4ED",
                },
            }
        },
    }
    schema.setdefault("components", {})["securitySchemes"] = {"OAuth2": oauth2}
    schema["security"] = [{"OAuth2": ["openid", "profile", "email"]}]

    for methods in schema.get("paths", {}).values():
        for operation in methods.values():
            operation["security"] = [{"OAuth2": ["openid", "profile", "email"]}]
            for response in operation.get("responses", {}).values():
                json_content = response.get("content", {}).get("application/json")
                if json_content and "schema" in json_content:
                    json_content["schema"] = _chatgpt_json_schema(json_content["schema"])

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]
app.include_router(oauth_router)
app.include_router(mcp_router)
app.mount("/mcp", get_mcp_starlette_app())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def use_request_public_base_url(request: Request, call_next):
    """Metadados OAuth/MCP usam o Host da requisição (ex.: domínio customizado)."""
    token = bind_request_base_url_from_request(request)
    try:
        return await call_next(request)
    finally:
        reset_request_base_url(token)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    """Endpoint público para health check do Render."""
    return {
        "service": "poliedro-api",
        "status": "ok",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "privacy": "/privacy",
    }


@app.get("/privacy", tags=["meta"], response_class=HTMLResponse)
@app.get("/privacy-policy", tags=["meta"], response_class=HTMLResponse, include_in_schema=False)
def privacy_policy() -> HTMLResponse:
    """Política de privacidade pública (exigida para publicar Custom GPT no ChatGPT)."""
    return HTMLResponse(privacy_policy_html())


@app.get("/health", tags=["meta"])
def public_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(f"{API_PREFIX}/auth/login", tags=["auth"], include_in_schema=False)
def auth_login(
    body: LoginRequest,
    _: None = Depends(verify_api_key),
) -> Any:
    """
    Autentica um usuário do P+ e retorna o token JWT + perfil do aluno.

    Use o access_token retornado no header Authorization: Bearer <token>
    nas demais requisições.
    """
    try:
        return login_and_build_profile(
            body.username,
            body.password,
            school_id=body.school_id,
            dependent_id=body.dependent_id,
        )
    except ProfileChoiceRequired as exc:
        return _handle_service_error(exc)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/health", tags=["poliedro"])
def poliedro_health(
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> dict[str, Any]:
    """Verifica se a API está configurada e consegue acessar o Poliedro."""
    try:
        return _service_for(ctx).health_check()
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/grades", tags=["poliedro"])
def get_grades(
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> Any:
    """Consulta o boletim/notas do aluno no portal Poliedro/P+."""
    try:
        return _service_for(ctx).get_grades()
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
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> Any:
    """Consulta mensagens/notificações do portal Poliedro/P+."""
    try:
        return _service_for(ctx).get_messages(
            status=status_filter, limit=limit, page=page
        )
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/messages/unread", tags=["poliedro"])
def get_unread_messages(
    limit: int = Query(default=50, ge=1, le=100),
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> Any:
    """Consulta mensagens/notificações não lidas do portal Poliedro/P+."""
    try:
        return _service_for(ctx).get_messages(status="UNREAD", limit=limit)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/next", tags=["poliedro"])
def get_next_events(
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> Any:
    """Consulta próximos eventos do calendário escolar Poliedro/P+."""
    try:
        return _service_for(ctx).get_next_events()
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/week", tags=["poliedro"])
def get_week_events(
    date: str | None = Query(
        default=None,
        description="Data de referência no formato YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> Any:
    """Consulta eventos da semana. Se date omitido, usa a data atual."""
    try:
        return _service_for(ctx).get_week_events(date=date)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/month", tags=["poliedro"])
def get_month_events(
    date: str | None = Query(
        default=None,
        description="Data de referência no formato YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> Any:
    """Consulta eventos do mês. Se date omitido, usa a data atual."""
    try:
        return _service_for(ctx).get_month_events(date=date)
    except Exception as exc:
        return _handle_service_error(exc)


@app.get(f"{API_PREFIX}/calendar/year", tags=["poliedro"])
def get_year_events(
    date: str | None = Query(
        default=None,
        description="Data de referência no formato YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    _: None = Depends(verify_api_access),
    ctx: UserContext = Depends(resolve_user_context),
) -> Any:
    """Consulta eventos do ano. Se date omitido, usa o ano atual."""
    try:
        return _service_for(ctx).get_year_events(date=date)
    except Exception as exc:
        return _handle_service_error(exc)


def run() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("poliedro_mcp.api:app", host="0.0.0.0", port=port)
