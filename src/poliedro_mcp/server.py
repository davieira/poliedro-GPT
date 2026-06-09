from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .logger import logger
from .user_context import get_service

mcp = FastMCP("poliedro-mcp")


def _service(
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
):
    return get_service(
        poliedro_token,
        school_id=school_id,
        dependent_id=dependent_id,
    )


@mcp.tool()
def poliedro_health_check(
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> dict[str, Any]:
    """
    Verifica se o MCP Poliedro está configurado e operacional.

    poliedro_token: JWT do P+ (opcional; sem ele usa config local).
    school_id / dependent_id: quando a conta tem múltiplas escolas ou dependentes.
    """
    return _service(poliedro_token, school_id, dependent_id).health_check()


@mcp.tool()
def get_grades(
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> Any:
    """Consulta o boletim/notas do aluno no portal Poliedro/P+."""
    logger.info("TOOL get_grades chamada")
    return _service(poliedro_token, school_id, dependent_id).get_grades()


@mcp.tool()
def get_unread_messages(
    limit: int = 50,
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> Any:
    """Consulta mensagens/notificações não lidas do portal Poliedro/P+."""
    return _service(poliedro_token, school_id, dependent_id).get_messages(
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
    """
    Consulta mensagens/notificações do portal Poliedro/P+.

    status normalmente pode ser UNREAD ou READ, conforme comportamento da API.
    """
    return _service(poliedro_token, school_id, dependent_id).get_messages(
        status=status, limit=limit, page=page
    )


@mcp.tool()
def get_next_events(
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> Any:
    """Consulta próximos eventos do calendário escolar Poliedro/P+."""
    return _service(poliedro_token, school_id, dependent_id).get_next_events()


@mcp.tool()
def get_week_events(
    date: str | None = None,
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> Any:
    """
    Consulta eventos da semana.

    date deve estar em YYYY-MM-DD. Se omitido, usa a data atual.
    """
    return _service(poliedro_token, school_id, dependent_id).get_week_events(
        date=date
    )


@mcp.tool()
def get_month_events(
    date: str | None = None,
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> Any:
    """
    Consulta eventos do mês.

    date deve estar em YYYY-MM-DD. Se omitido, usa a data atual.
    """
    return _service(poliedro_token, school_id, dependent_id).get_month_events(
        date=date
    )


@mcp.tool()
def get_year_events(
    date: str | None = None,
    poliedro_token: str | None = None,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> Any:
    """
    Consulta eventos do ano.

    date deve estar em YYYY-MM-DD. Se omitido, usa o ano atual.
    """
    return _service(poliedro_token, school_id, dependent_id).get_year_events(
        date=date
    )


if __name__ == "__main__":
    mcp.run()
