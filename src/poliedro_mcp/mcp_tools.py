from __future__ import annotations

from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP

from .logger import logger
from .user_context import get_service


def _resolve_token(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    access = get_access_token()
    if access and access.token:
        return access.token
    return None


def _service(
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
):
    return get_service(
        _resolve_token(poliedro_token),
        school_id=school_id,
        dependent_id=dependent_id,
    )


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def poliedro_health_check(
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> dict[str, Any]:
        """Verifica se o MCP Poliedro está configurado e operacional."""
        return _service(school_id=school_id, dependent_id=dependent_id).health_check()

    @mcp.tool()
    def get_grades(
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        """Consulta o boletim/notas do aluno no portal Poliedro/P+."""
        logger.info("TOOL get_grades chamada")
        return _service(school_id=school_id, dependent_id=dependent_id).get_grades()

    @mcp.tool()
    def get_unread_messages(
        limit: int = 50,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        """Consulta mensagens/notificações não lidas do portal Poliedro/P+."""
        return _service(school_id=school_id, dependent_id=dependent_id).get_messages(
            status="UNREAD", limit=limit
        )

    @mcp.tool()
    def get_messages(
        status: str = "UNREAD",
        limit: int = 50,
        page: int = 1,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        """Consulta mensagens/notificações do portal Poliedro/P+."""
        return _service(school_id=school_id, dependent_id=dependent_id).get_messages(
            status=status, limit=limit, page=page
        )

    @mcp.tool()
    def get_next_events(
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        """Consulta próximos eventos do calendário escolar Poliedro/P+."""
        return _service(school_id=school_id, dependent_id=dependent_id).get_next_events()

    @mcp.tool()
    def get_week_events(
        date: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        """Consulta eventos da semana (date em YYYY-MM-DD)."""
        return _service(school_id=school_id, dependent_id=dependent_id).get_week_events(
            date=date
        )

    @mcp.tool()
    def get_month_events(
        date: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        """Consulta eventos do mês (date em YYYY-MM-DD)."""
        return _service(school_id=school_id, dependent_id=dependent_id).get_month_events(
            date=date
        )

    @mcp.tool()
    def get_year_events(
        date: str | None = None,
        school_id: int | None = None,
        dependent_id: int | None = None,
    ) -> Any:
        """Consulta eventos do ano (date em YYYY-MM-DD)."""
        return _service(school_id=school_id, dependent_id=dependent_id).get_year_events(
            date=date
        )
