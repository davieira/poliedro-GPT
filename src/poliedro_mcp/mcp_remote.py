from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from mcp.server.auth.handlers.metadata import MetadataHandler, ProtectedResourceMetadataHandler
from mcp.server.auth.routes import build_metadata
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import ProtectedResourceMetadata
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from .api_base import api_base_url, mcp_base_url
from .auth import LoginError, login_with_password
from .mcp_auth_provider import get_mcp_auth_provider
from .mcp_tools import register_tools
from .oauth_proxy import GITHUB_REPO_URL, _login_html
from .profile_discovery import ProfileChoiceRequired, discover_profile_config
from .user_context import get_base_config

router = APIRouter(tags=["mcp"])

_mcp_server: FastMCP | None = None
_mcp_starlette: Starlette | None = None


def _parse_optional_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def create_mcp_server() -> FastMCP:
    global _mcp_server, _mcp_starlette
    if _mcp_server is not None:
        return _mcp_server

    provider = get_mcp_auth_provider()
    issuer = AnyHttpUrl(mcp_base_url())

    mcp = FastMCP(
        name="poliedro-mcp",
        instructions=(
            "Consulta notas, mensagens e calendário do portal Poliedro/P+. "
            "Requer login com conta do pmais.p4ed.com."
        ),
        website_url=GITHUB_REPO_URL,
        auth_server_provider=provider,
        stateless_http=True,
        streamable_http_path="/",
        auth=AuthSettings(
            issuer_url=issuer,
            resource_server_url=issuer,
            service_documentation_url=AnyHttpUrl(f"{api_base_url()}/docs"),
            required_scopes=["openid"],
            client_registration_options=_mcp_client_registration_options(),
        ),
    )
    register_tools(mcp)
    _mcp_server = mcp
    _mcp_starlette = mcp.streamable_http_app()
    return mcp


def get_mcp_starlette_app() -> Starlette:
    create_mcp_server()
    assert _mcp_starlette is not None
    return _mcp_starlette


def get_mcp_session_manager():
    return create_mcp_server().session_manager


def _mcp_client_registration_options() -> ClientRegistrationOptions:
    return ClientRegistrationOptions(
        enabled=True,
        default_scopes=["openid", "profile", "email"],
        valid_scopes=["openid", "profile", "email"],
    )


def _mcp_oauth_metadata_handler() -> MetadataHandler:
    """Metadados OAuth do MCP (RFC 8414 path-aware + registration_endpoint)."""
    issuer = AnyHttpUrl(mcp_base_url())
    metadata = build_metadata(
        issuer_url=issuer,
        service_documentation_url=AnyHttpUrl(f"{api_base_url()}/docs"),
        client_registration_options=_mcp_client_registration_options(),
        revocation_options=RevocationOptions(),
    )
    metadata = metadata.model_copy(
        update={
            "token_endpoint_auth_methods_supported": [
                "none",
                "client_secret_post",
                "client_secret_basic",
            ],
        }
    )
    return MetadataHandler(metadata)


@router.get("/.well-known/oauth-authorization-server/mcp")
async def mcp_oauth_metadata_rfc8414(request: Request) -> Response:
    """RFC 8414 — metadados do issuer /mcp na raiz do site (exigido pelo Claude)."""
    return await _mcp_oauth_metadata_handler().handle(request)


@router.get("/.well-known/openid-configuration/mcp")
async def mcp_openid_metadata_rfc8414(request: Request) -> Response:
    """Fallback OIDC discovery (RFC 8414 §5) para conectores MCP."""
    return await _mcp_oauth_metadata_handler().handle(request)


@router.api_route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS", "HEAD"])
async def mcp_entry_no_trailing_slash() -> RedirectResponse:
    """Evita 307 que quebra POST do Streamable HTTP em alguns clientes."""
    return RedirectResponse(url="/mcp/", status_code=308)


@router.get("/.well-known/oauth-protected-resource/mcp")
async def mcp_protected_resource_metadata(request: Request) -> Response:
    """RFC 9728 — metadados na raiz do site (exigido por conectores Claude)."""
    resource_url = AnyHttpUrl(mcp_base_url())
    handler = ProtectedResourceMetadataHandler(
        ProtectedResourceMetadata(
            resource=resource_url,
            authorization_servers=[resource_url],
            scopes_supported=["openid"],
            resource_documentation=AnyHttpUrl(f"{api_base_url()}/docs"),
        )
    )
    return await handler.handle(request)


@router.get("/mcp/login")
def mcp_login_get(pending: str = Query(...)) -> HTMLResponse:
    """Tela de login do MCP remoto (Claude / conectores OAuth)."""
    provider = get_mcp_auth_provider()
    if provider.get_pending(pending) is None:
        raise HTTPException(status_code=400, detail="Sessão de login inválida ou expirada.")

    return HTMLResponse(
        _mcp_login_html(pending=pending),
    )


@router.post("/mcp/login", response_model=None)
def mcp_login_post(
    pending: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    school_id: str | None = Form(default=None),
    dependent_id: str | None = Form(default=None),
) -> Response:
    provider = get_mcp_auth_provider()
    if provider.get_pending(pending) is None:
        raise HTTPException(status_code=400, detail="Sessão de login inválida ou expirada.")

    base = get_base_config()
    base_url = base["base_url"].rstrip("/")

    try:
        tokens = login_with_password(base_url, username.strip(), password)
    except LoginError as exc:
        return HTMLResponse(_mcp_login_html(pending=pending, error=str(exc)), status_code=401)

    access_token = tokens["access_token"]
    parsed_school_id = _parse_optional_int(school_id)
    parsed_dependent_id = _parse_optional_int(dependent_id)

    if parsed_school_id is not None or parsed_dependent_id is not None:
        try:
            discover_profile_config(
                base_url,
                access_token,
                interactive=False,
                school_id=parsed_school_id,
                dependent_id=parsed_dependent_id,
            )
        except ProfileChoiceRequired as exc:
            return HTMLResponse(
                _mcp_login_html(
                    pending=pending,
                    choice_error={"tipo": exc.choice_type, "opcoes": exc.options},
                ),
                status_code=409,
            )
        except Exception as exc:
            return HTMLResponse(
                _mcp_login_html(
                    pending=pending,
                    error=f"Não foi possível carregar o perfil: {exc}",
                ),
                status_code=400,
            )

    try:
        redirect_url = provider.complete_login(
            pending,
            poliedro_access_token=access_token,
            poliedro_refresh_token=tokens.get("refresh_token"),
            expires_in=int(tokens.get("expires_in") or 3600),
        )
    except ValueError as exc:
        return HTMLResponse(
            _mcp_login_html(pending=pending, error=str(exc)),
            status_code=400,
        )
    return RedirectResponse(redirect_url, status_code=302)


def _mcp_login_html(
    *,
    pending: str,
    error: str | None = None,
    choice_error: dict[str, Any] | None = None,
) -> str:
    return _login_html(
        form_action="/mcp/login",
        pending=pending,
        error=error,
        choice_error=choice_error,
    )


def create_stdio_server() -> FastMCP:
    """MCP local (stdio) sem OAuth — usa config/Keychain."""
    mcp = FastMCP(
        name="poliedro-mcp",
        instructions="Consulta notas, mensagens e calendário do Poliedro P+.",
    )

    from .user_context import get_service

    @mcp.tool()
    def poliedro_health_check(
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> dict[str, Any]:
        return get_service(poliedro_token, school_id=school_id, dependent_id=dependent_id).health_check()

    # Re-register stdio tools with optional poliedro_token via wrapper
    _register_stdio_tools(mcp)
    return mcp


def _register_stdio_tools(mcp: FastMCP) -> None:
    from .user_context import get_service

    def svc(token=None, school_id=None, dependent_id=None):
        return get_service(token, school_id=school_id, dependent_id=dependent_id)

    @mcp.tool()
    def get_grades(
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        return svc(poliedro_token, school_id, dependent_id).get_grades()

    @mcp.tool()
    def get_unread_messages(
        limit: int = 50,
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        return svc(poliedro_token, school_id, dependent_id).get_messages(
            status="UNREAD", limit=limit
        )

    @mcp.tool()
    def get_messages(
        status: str = "UNREAD",
        limit: int = 50,
        page: int = 1,
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        return svc(poliedro_token, school_id, dependent_id).get_messages(
            status=status, limit=limit, page=page
        )

    @mcp.tool()
    def get_next_events(
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        return svc(poliedro_token, school_id, dependent_id).get_next_events()

    @mcp.tool()
    def get_week_events(
        date: str | None = None,
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        return svc(poliedro_token, school_id, dependent_id).get_week_events(date=date)

    @mcp.tool()
    def get_month_events(
        date: str | None = None,
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        return svc(poliedro_token, school_id, dependent_id).get_month_events(date=date)

    @mcp.tool()
    def get_year_events(
        date: str | None = None,
        poliedro_token: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        return svc(poliedro_token, school_id, dependent_id).get_year_events(date=date)
