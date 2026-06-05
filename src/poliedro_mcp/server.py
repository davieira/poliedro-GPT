from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .services import PoliedroService
from .logger import logger

mcp = FastMCP("poliedro-mcp")


@mcp.tool()
def poliedro_health_check() -> dict[str, Any]:
    """Verifica se o MCP Poliedro está configurado e operacional."""
    return PoliedroService().health_check()


@mcp.tool()
def get_grades() -> Any:
    """Consulta o boletim/notas do aluno configurado no portal Poliedro/P+."""
    logger.info("TOOL get_grades chamada")
    return PoliedroService().get_grades()


@mcp.tool()
def get_unread_messages(limit: int = 50) -> Any:
    """Consulta mensagens/notificações não lidas do portal Poliedro/P+."""
    logger.info("TOOL get_next_events chamada")
    return PoliedroService().get_messages(status="UNREAD", limit=limit)


@mcp.tool()
def get_messages(status: str = "UNREAD", limit: int = 50, page: int = 1) -> Any:
    """
    Consulta mensagens/notificações do portal Poliedro/P+.

    status normalmente pode ser UNREAD ou READ, conforme comportamento da API.
    """
    return PoliedroService().get_messages(status=status, limit=limit, page=page)


@mcp.tool()
def get_next_events() -> Any:
    """Consulta próximos eventos do calendário escolar Poliedro/P+."""
    return PoliedroService().get_next_events()


@mcp.tool()
def get_week_events(date: str | None = None) -> Any:
    """
    Consulta eventos da semana.

    date deve estar em YYYY-MM-DD. Se omitido, usa a data atual.
    """
    return PoliedroService().get_week_events(date=date)


@mcp.tool()
def get_month_events(date: str | None = None) -> Any:
    """
    Consulta eventos do mês.

    date deve estar em YYYY-MM-DD. Se omitido, usa a data atual.
    """
    return PoliedroService().get_month_events(date=date)


@mcp.tool()
def get_year_events(date: str | None = None) -> Any:
    """
    Consulta eventos do ano.

    date deve estar em YYYY-MM-DD. Se omitido, usa o ano atual.
    """
    return PoliedroService().get_year_events(date=date)


if __name__ == "__main__":
    mcp.run()
