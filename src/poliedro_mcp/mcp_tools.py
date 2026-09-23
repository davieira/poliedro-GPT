"""Ferramentas MCP. Um spec serve o conector remoto e o stdio local.

FastMCP monta o schema a partir de inspect.signature (usa __signature__).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .logger import logger
from .user_context import get_service

_MISSING = inspect.Parameter.empty


def _resolve_token(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    access = get_access_token()
    if access and access.token:
        return access.token
    return None


def _service(token: str | None, school_id: int | None, dependent_id: int | None):
    return get_service(
        _resolve_token(token),
        school_id=school_id,
        dependent_id=dependent_id,
    )


@dataclass(frozen=True)
class _Spec:
    name: str
    doc: str
    params: tuple[tuple[str, Any, Any], ...]
    call: Callable[[Any, dict[str, Any]], Any]
    returns: Any = Any


def _p(name: str, ann: Any, default: Any = None) -> tuple[str, Any, Any]:
    return (name, ann, default)


_TOOLS: tuple[_Spec, ...] = (
    _Spec(
        "poliedro_health_check",
        "Verifica se o MCP Poliedro está configurado e operacional.",
        (),
        lambda svc, args: svc.health_check(),
        dict[str, Any],
    ),
    _Spec(
        "get_grades",
        "Consulta o boletim/notas do aluno no portal Poliedro/P+.",
        (),
        lambda svc, args: svc.get_grades(),
    ),
    _Spec(
        "get_simulation_grades",
        "Consulta notas do simulado / prova trimestral do Poliedro/P+.",
        (_p("school_year", int | None),),
        lambda svc, args: svc.get_simulation_grades(school_year=args.get("school_year")),
    ),
    _Spec(
        "list_simulation_assessments",
        "Lista simulados com UUID, status, datas e nota geral.",
        (_p("school_year", int | None),),
        lambda svc, args: svc.list_simulation_assessments(school_year=args.get("school_year")),
    ),
    _Spec(
        "get_simulation_performance",
        "Consulta detalhe do simulado por matéria.\n\n"
        "Use assessment_id retornado por list_simulation_assessments.",
        (_p("assessment_id", str, _MISSING),),
        lambda svc, args: svc.get_simulation_performance(args["assessment_id"]),
    ),
    _Spec(
        "get_unread_messages",
        "Consulta mensagens/notificações não lidas do portal Poliedro/P+.",
        (_p("limit", int, 50),),
        lambda svc, args: svc.get_messages(status="UNREAD", limit=args.get("limit", 50)),
    ),
    _Spec(
        "get_messages",
        "Lista mensagens/comunicados com preview. Use announcement_id em get_message_detail.",
        (_p("status", str, "UNREAD"), _p("limit", int, 50), _p("page", int, 1)),
        lambda svc, args: svc.get_messages(
            status=args.get("status", "UNREAD"),
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        ),
    ),
    _Spec(
        "get_message_detail",
        "Consulta conteúdo completo de um comunicado. Use announcement_id de get_messages.",
        (_p("announcement_id", int, _MISSING),),
        lambda svc, args: svc.get_message_detail(args["announcement_id"]),
    ),
    _Spec(
        "get_next_events",
        "Consulta próximos eventos do calendário escolar Poliedro/P+.",
        (),
        lambda svc, args: svc.get_next_events(),
    ),
    _Spec(
        "get_week_events",
        "Consulta eventos da semana (date em YYYY-MM-DD).",
        (_p("date", str | None),),
        lambda svc, args: svc.get_week_events(date=args.get("date")),
    ),
    _Spec(
        "get_month_events",
        "Consulta eventos do mês (date em YYYY-MM-DD).",
        (_p("date", str | None),),
        lambda svc, args: svc.get_month_events(date=args.get("date")),
    ),
    _Spec(
        "get_year_events",
        "Consulta eventos do ano (date em YYYY-MM-DD).",
        (_p("date", str | None),),
        lambda svc, args: svc.get_year_events(date=args.get("date")),
    ),
)

_CONTEXT = (
    _p("school_id", int | None),
    _p("dependent_id", int | None),
)


def _bind(spec: _Spec, *, local: bool):
    def fn(**kwargs: Any) -> Any:
        token = kwargs.pop("poliedro_token", None)
        school_id = kwargs.pop("school_id", None)
        dependent_id = kwargs.pop("dependent_id", None)
        if spec.name == "get_grades" and not local:
            logger.info("TOOL get_grades chamada")
        return spec.call(_service(token, school_id, dependent_id), kwargs)

    params = list(spec.params)
    if local:
        params.append(_p("poliedro_token", str | None))
    params.extend(_CONTEXT)

    signature: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {"return": spec.returns}
    for name, ann, default in params:
        signature.append(
            inspect.Parameter(
                name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=_MISSING if default is _MISSING else default,
                annotation=ann,
            )
        )
        annotations[name] = ann

    fn.__name__ = spec.name
    fn.__doc__ = spec.doc
    fn.__signature__ = inspect.Signature(signature, return_annotation=spec.returns)  # type: ignore[attr-defined]
    fn.__annotations__ = annotations
    return fn


# Todas as tools só leem a conta P+ logada. O portal do ChatGPT exige os três hints.
_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    openWorldHint=False,
    destructiveHint=False,
    idempotentHint=True,
)


def register_tools(mcp: FastMCP, *, local: bool = False) -> None:
    for spec in _TOOLS:
        mcp.add_tool(_bind(spec, local=local), annotations=_READ_ONLY)


def create_local_server() -> FastMCP:
    """MCP local (stdio) sem OAuth — usa config/Keychain, com poliedro_token opcional."""
    mcp = FastMCP(
        name="poliedro-mcp",
        instructions="Consulta notas, mensagens e calendário do Poliedro P+.",
    )
    register_tools(mcp, local=True)
    return mcp
