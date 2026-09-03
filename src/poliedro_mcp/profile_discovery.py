from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

import requests

from .logger import logger

ROLE_ALUNO = 2
ROLE_RESPONSAVEL = 10
CALENDAR_ROLE_ALUNO = 2
DEFAULT_TIMEZONE = "America/Sao_Paulo"


class ProfileDiscoveryError(RuntimeError):
    pass


class ProfileChoiceRequired(ProfileDiscoveryError):
    """Perfil ambíguo: o cliente deve informar school_id ou dependent_id."""

    def __init__(self, choice_type: str, options: list[dict[str, Any]]) -> None:
        self.choice_type = choice_type
        self.options = options
        super().__init__(
            f"Múltiplas opções de {choice_type}. "
            f"Informe o parâmetro correspondente na requisição."
        )


def decode_jwt_claims(access_token: str) -> dict[str, Any]:
    parts = access_token.split(".")
    if len(parts) < 2:
        raise ProfileDiscoveryError(
            "Token JWT inválido. Faça login novamente no ChatGPT (Sign in)."
        )
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise ProfileDiscoveryError(
            "Token JWT inválido ou corrompido. Faça login novamente no ChatGPT (Sign in)."
        ) from exc


def _api_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://pmais.p4ed.com",
        "Referer": "https://pmais.p4ed.com/",
        "application-id": "1",
    }


def _get(
    base_url: str,
    access_token: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    response = requests.get(
        url,
        headers=_api_headers(access_token),
        params=params,
        timeout=20,
    )
    if response.status_code >= 400:
        raise ProfileDiscoveryError(
            f"Falha ao consultar {path}: HTTP {response.status_code} — {response.text}"
        )
    return response.json()


def _post_json(
    base_url: str,
    access_token: str,
    path: str,
    payload: dict[str, Any],
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    response = requests.post(
        url,
        headers={**_api_headers(access_token), "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        raise ProfileDiscoveryError(
            f"Falha ao consultar {path}: HTTP {response.status_code} — {response.text}"
        )
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _user_uuid(claims: dict[str, Any]) -> str | None:
    sub = claims.get("sub")
    if isinstance(sub, str) and "-" in sub:
        return sub
    for key in ("userId", "userid"):
        value = claims.get(key)
        if isinstance(value, str) and "-" in value:
            return value
    return None


def _unwrap_me_payload(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    if "escolas" in data or "perfis_escola" in data or "dependentes" in data:
        return data
    nested = data.get("data")
    if isinstance(nested, dict):
        return nested
    return data


def _try_fetch_perfil(
    base_url: str,
    access_token: str,
    claims: dict[str, Any],
) -> dict[str, Any] | None:
    uuid = _user_uuid(claims)
    if not uuid:
        return None
    try:
        data = _get(base_url, access_token, f"/pmais/api/v2/perfil/get/user/{uuid}")
    except ProfileDiscoveryError:
        logger.info("GET /pmais/api/v2/perfil/get/user/{id} falhou")
        return None
    if not isinstance(data, dict):
        return None
    logger.info("Perfil v2 get/user: escolas=%s", len(data.get("escolas") or []))
    return data


def _set_selected_profile(
    base_url: str,
    access_token: str,
    *,
    profile_id: int,
    school_id: int,
) -> None:
    """Espelha o POST que o P+ faz após o login para fixar escola/perfil na sessão."""
    try:
        _post_json(
            base_url,
            access_token,
            "/pmais/api/v1/user/setSelectedProfile",
            {"profileId": profile_id, "schoolId": school_id},
        )
        logger.info(
            "setSelectedProfile ok profileId=%s schoolId=%s",
            profile_id,
            school_id,
        )
    except ProfileDiscoveryError as exc:
        logger.warning("setSelectedProfile falhou: %s", exc)


def _school_links_from_perfil(perfil: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for item in perfil.get("escolas") or []:
        if not isinstance(item, dict) or item.get("idEscola") is None:
            continue
        roles = item.get("perfil") or []
        if isinstance(roles, dict):
            roles = [roles]
        role_id = ROLE_ALUNO
        if roles and isinstance(roles[0], dict) and roles[0].get("id") is not None:
            role_id = int(roles[0]["id"])
        nome = item.get("nome")
        links.append(
            {
                "idEscola": int(item["idEscola"]),
                "idPerfil": role_id,
                "nome": nome,
                "usuario": {"nome": nome},
            }
        )
    return _normalize_school_links(links)


def _try_fetch_me(
    base_url: str,
    access_token: str,
    claims: dict[str, Any],
) -> dict[str, Any] | None:
    uuid = _user_uuid(claims)
    if not uuid:
        return None
    try:
        data = _get(base_url, access_token, f"/pmais/api/v2/usuario/{uuid}/me")
    except ProfileDiscoveryError:
        logger.info("GET /pmais/api/v2/usuario/{id}/me falhou; usando escolausuario/all")
        return None
    payload = _unwrap_me_payload(data)
    if payload:
        logger.info(
            "Perfil v2 /me: escolas=%s dependentes=%s",
            len(payload.get("escolas") or []),
            len(payload.get("dependentes") or []),
        )
    return payload


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_school_vinculo(item: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza vínculo de /me (idEscola) ou do POST /login (id da escola)."""
    nested = item.get("escola") if isinstance(item.get("escola"), dict) else {}
    perfil = item.get("perfil") if isinstance(item.get("perfil"), dict) else {}

    if item.get("idEscola") is not None:
        school_id = int(item["idEscola"])
        link_id = item.get("id")
    elif nested.get("id") is not None and item.get("idPerfil") is None and item.get("statusEscola") is not None:
        school_id = int(item.get("id") or nested["id"])
        link_id = item.get("idEscolaUsuario")
    elif item.get("idEscolaUsuario") is not None:
        school_id = int(item.get("id") or nested.get("id"))
        link_id = item.get("idEscolaUsuario")
    else:
        school_id = int(item.get("idEscola") or nested.get("id") or item.get("id"))
        link_id = item.get("idEscolaUsuario") or item.get("id")

    role = item.get("idPerfil") or perfil.get("id")
    if role is None:
        role = ROLE_ALUNO
    nome = (
        nested.get("nomeConta")
        or nested.get("nome")
        or item.get("nome")
    )
    return {
        "idEscola": school_id,
        "idPerfil": int(role),
        "idEscolaUsuario": link_id,
        "nome": nome,
        "ativo": item.get("ativo"),
        "excluido": item.get("excluido"),
        "statusEscola": item.get("statusEscola") or nested.get("ativo"),
        "escola": nested,
        "usuario": {"nome": nome},
    }


def _school_links_from_me(me: dict[str, Any]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for item in me.get("escolas") or []:
        if not isinstance(item, dict):
            continue
        parsed = _parse_school_vinculo(item)
        if parsed:
            links.append(parsed)
    return _normalize_school_links(links)


def _enrollment_from_dep_escolas(escolas: Any) -> tuple[int | None, int | None]:
    if not isinstance(escolas, list):
        return None, None
    for vinculo in escolas:
        if not isinstance(vinculo, dict) or vinculo.get("excluido") is True:
            continue
        turma = vinculo.get("turma") if isinstance(vinculo.get("turma"), dict) else {}
        enrollment = _as_optional_int(turma.get("idOrigem") or vinculo.get("matricula"))
        year = _as_optional_int(turma.get("anoLetivo"))
        if enrollment is not None or year is not None:
            return enrollment, year
    return None, None


def _dependents_from_me(me: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in me.get("dependentes") or []:
        if not isinstance(item, dict):
            continue
        dep = item.get("dep") if isinstance(item.get("dep"), dict) else item
        dependent_id = _as_optional_int(dep.get("id") or dep.get("idUsuario"))
        if dependent_id is None:
            continue
        enrollment_id, school_year = _enrollment_from_dep_escolas(dep.get("escola"))
        normalized.append(
            {
                "id": dependent_id,
                "name": dep.get("nome") or dep.get("name"),
                "emailP4ed": dep.get("emailp4ed") or dep.get("emailP4ed") or dep.get("email"),
                "originId": dep.get("idOrigem") or dep.get("originId") or dep.get("originID"),
                "enrollmentId": enrollment_id,
                "schoolYear": school_year,
            }
        )
    return normalized


def _is_active_school(item: dict[str, Any]) -> bool:
    if item.get("excluido") is True:
        return False
    ativo = item.get("ativo")
    if ativo is not None:
        return str(ativo).lower() in {"1", "true"}
    status = item.get("statusEscola")
    nested = item.get("escola")
    if status is None and isinstance(nested, dict):
        status = nested.get("statusEscola") or nested.get("ativo") or nested.get("status")
    if status is None:
        status = item.get("status")
    if status is None:
        return True
    try:
        return int(status) == 1
    except (TypeError, ValueError):
        return str(status).lower() in {"1", "true"}


def _school_id_of(item: dict[str, Any]) -> int:
    if item.get("idEscola") is not None:
        return int(item["idEscola"])
    return int(item["id"])


def _link_recency(item: dict[str, Any]) -> int:
    for key in ("idEscolaUsuario", "id"):
        value = item.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _normalize_school_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Uma linha por escola, só vínculos ativos — como o POST /login do P+."""
    active = [item for item in links if _is_active_school(item)]
    if not active:
        active = list(links)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in active:
        grouped.setdefault(_school_id_of(item), []).append(item)
    return [max(group, key=_link_recency) for group in grouped.values()]


def _school_display_name(item: dict[str, Any]) -> str | None:
    nested = item.get("escola") if isinstance(item.get("escola"), dict) else {}
    return (
        item.get("nome")
        or nested.get("nomeConta")
        or nested.get("nome")
        or (item.get("usuario") or {}).get("nome")
    )


def _pick_item(
    items: list[dict[str, Any]],
    label: str,
    describe: Any,
) -> dict[str, Any]:
    if not items:
        raise ProfileDiscoveryError(f"Nenhum {label} encontrado na conta.")
    if len(items) == 1:
        return items[0]

    print(f"\nEncontrados {len(items)} {label}s:")
    for index, item in enumerate(items, start=1):
        print(f"  [{index}] {describe(item)}")

    while True:
        choice = input(f"Escolha o {label} (1-{len(items)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            return items[int(choice) - 1]
        print("Opção inválida.")


def _list_school_links(base_url: str, access_token: str, user_id: int) -> list[dict[str, Any]]:
    data = _get(
        base_url,
        access_token,
        "/pmais/api/v1/escolausuario/all",
        params={"idUsuario": user_id, "page": 1, "limit": 50},
    )
    links = data.get("escolausuarios") or []
    if not links:
        raise ProfileDiscoveryError(
            "Nenhuma escola vinculada à conta. Verifique o acesso no portal P+."
        )
    return _normalize_school_links(links)


def _list_dependents(
    base_url: str,
    access_token: str,
    user_id: int,
    school_id: int,
) -> list[dict[str, Any]]:
    data = _get(
        base_url,
        access_token,
        "/pmais/api/v1/user/dependents",
        params={"userId": user_id, "schoolId": school_id, "page": 1, "limit": 50},
    )
    return data.get("dependents") or []


def _grade_years(
    base_url: str,
    access_token: str,
    *,
    email_p4ed: str,
    origin_id: str | int | None = None,
    school_id: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"emailP4ed": email_p4ed}
    if origin_id is not None:
        params["originId"] = str(origin_id)
    if school_id is not None:
        params["schoolId"] = school_id
    return _get(base_url, access_token, "/pmais/api/v1/gradeStudentReport/years", params=params)


def _resolve_school_year(years_payload: dict[str, Any]) -> tuple[int, int]:
    years = years_payload.get("years") or []
    classes = years_payload.get("classes") or []
    if not years:
        raise ProfileDiscoveryError("Não foi possível obter anos letivos do aluno.")

    current_year = datetime.now().year
    if current_year in years:
        school_year = current_year
    else:
        school_year = max(years)

    enrollment_id: int | None = None
    for item in classes:
        if item.get("year") == school_year:
            enrollment_id = item.get("enrollmentId")
            break

    if enrollment_id is None:
        raise ProfileDiscoveryError(
            f"Matrícula (enrollmentId) não encontrada para o ano letivo {school_year}."
        )

    return school_year, int(enrollment_id)


def _select_school_link(
    school_links: list[dict[str, Any]],
    *,
    school_id: int | None,
    interactive: bool,
) -> dict[str, Any]:
    if school_id is not None:
        for link in school_links:
            if int(link["idEscola"]) == school_id:
                return link
        raise ProfileDiscoveryError(
            f"Escola {school_id} não vinculada à conta. "
            f"Opções: {[int(item['idEscola']) for item in school_links]}"
        )

    if interactive and len(school_links) > 1:
        return _pick_item(
            school_links,
            "escola",
            lambda item: (
                f"idEscola={item.get('idEscola')} "
                f"perfil={item.get('idPerfil')} "
                f"({(item.get('usuario') or {}).get('nome', '')})"
            ),
        )

    if len(school_links) > 1:
        raise ProfileChoiceRequired(
            "escola",
            [
                {
                    "school_id": int(item["idEscola"]),
                    "role_id": int(item["idPerfil"]),
                    "name": _school_display_name(item),
                }
                for item in school_links
            ],
        )

    return school_links[0]


def _select_dependent(
    dependents: list[dict[str, Any]],
    *,
    dependent_id: int | None,
    interactive: bool,
) -> dict[str, Any]:
    if not dependents:
        raise ProfileDiscoveryError(
            "Conta de responsável sem dependentes vinculados à escola."
        )

    if dependent_id is not None:
        for dependent in dependents:
            if int(dependent["id"]) == dependent_id:
                return dependent
        raise ProfileDiscoveryError(
            f"Dependente {dependent_id} não encontrado. "
            f"Opções: {[int(item['id']) for item in dependents]}"
        )

    if interactive and len(dependents) > 1:
        return _pick_item(
            dependents,
            "dependente",
            lambda item: f"{item.get('name')} — {item.get('emailP4ed')}",
        )

    if len(dependents) > 1:
        raise ProfileChoiceRequired(
            "dependente",
            [
                {
                    "dependent_id": int(item["id"]),
                    "name": item.get("name"),
                    "email_p4ed": item.get("emailP4ed") or item.get("email"),
                }
                for item in dependents
            ],
        )

    return dependents[0]


def discover_profile_config(
    base_url: str,
    access_token: str,
    *,
    interactive: bool = True,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> dict[str, Any]:
    """
    Monta auth, student e calendar a partir do token e das APIs do P+.
    """
    claims = decode_jwt_claims(access_token)
    username = claims.get("preferred_username")
    user_id = claims.get("idUsuario")

    if not username:
        raise ProfileDiscoveryError("Token sem preferred_username.")
    if not user_id:
        raise ProfileDiscoveryError("Token sem idUsuario.")

    me = _try_fetch_me(base_url, access_token, claims)
    perfil = _try_fetch_perfil(base_url, access_token, claims)

    school_links = _school_links_from_perfil(perfil) if perfil else []
    if not school_links and me:
        school_links = _school_links_from_me(me)
    if not school_links:
        school_links = _list_school_links(base_url, access_token, int(user_id))

    school_link = _select_school_link(
        school_links,
        school_id=school_id,
        interactive=interactive,
    )

    school_id = int(school_link["idEscola"])
    profile_role_id = int(school_link["idPerfil"])
    _set_selected_profile(
        base_url,
        access_token,
        profile_id=profile_role_id,
        school_id=school_id,
    )

    student_owner_id = int(user_id)
    selected_dependent_id: int | None = None
    email_p4ed = claims.get("email")
    origin_id: str | int | None = None
    enrollment_id: int | None = None
    school_year: int | None = None
    dependent: dict[str, Any] | None = None

    if profile_role_id == ROLE_RESPONSAVEL:
        dependents = _dependents_from_me(me) if me else []
        if not dependents:
            dependents = _list_dependents(
                base_url, access_token, int(user_id), school_id
            )
        dependent = _select_dependent(
            dependents,
            dependent_id=dependent_id,
            interactive=interactive,
        )

        student_owner_id = int(dependent["id"])
        selected_dependent_id = student_owner_id
        email_p4ed = dependent.get("emailP4ed") or dependent.get("email") or email_p4ed
        origin_id = dependent.get("originId") or dependent.get("originID")
        enrollment_id = _as_optional_int(dependent.get("enrollmentId"))
        school_year = _as_optional_int(dependent.get("schoolYear"))
    else:
        if me:
            email_p4ed = me.get("emailp4ed") or me.get("emailP4ed") or email_p4ed
            origin_id = me.get("idOrigem") or me.get("originId") or origin_id
        else:
            user_data = _get(
                base_url,
                access_token,
                "/pmais/api/v1/user/bySchool/",
                params={"userId": int(user_id), "schoolId": school_id},
            )
            email_p4ed = user_data.get("emailp4ed") or user_data.get("emailP4ed") or email_p4ed
            origin_id = user_data.get("originId") or user_data.get("originID")

    if not email_p4ed:
        raise ProfileDiscoveryError("Não foi possível determinar o email P4ED do aluno.")

    if enrollment_id is None or school_year is None:
        years_payload = _grade_years(
            base_url,
            access_token,
            email_p4ed=str(email_p4ed),
            origin_id=origin_id,
            school_id=school_id,
        )
        school_year, enrollment_id = _resolve_school_year(years_payload)

    return {
        "auth": {"username": str(username)},
        "student": {
            "school_id": school_id,
            "school_year": school_year,
            "origin_id": int(origin_id) if origin_id is not None else None,
            "enrollment_id": enrollment_id,
            "email_p4ed": str(email_p4ed),
            "role_id": profile_role_id,
            "dependent_id": selected_dependent_id,
        },
        "calendar": {
            "owner_id": student_owner_id,
            "role_pmais_id": CALENDAR_ROLE_ALUNO,
            "time_zone": DEFAULT_TIMEZONE,
            "is_widget": False,
        },
    }
