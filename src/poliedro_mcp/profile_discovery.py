from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

import requests

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
        raise ProfileDiscoveryError("Token JWT inválido.")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _api_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Origin": "https://pmais.p4ed.com",
        "Referer": "https://pmais.p4ed.com/",
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
    return links


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
                    "name": (item.get("usuario") or {}).get("nome"),
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

    school_links = _list_school_links(base_url, access_token, int(user_id))
    school_link = _select_school_link(
        school_links,
        school_id=school_id,
        interactive=interactive,
    )

    school_id = int(school_link["idEscola"])
    profile_role_id = int(school_link["idPerfil"])

    student_owner_id = int(user_id)
    email_p4ed = claims.get("email")
    origin_id: str | int | None = None

    if profile_role_id == ROLE_RESPONSAVEL:
        dependents = _list_dependents(
            base_url, access_token, int(user_id), school_id
        )
        dependent = _select_dependent(
            dependents,
            dependent_id=dependent_id,
            interactive=interactive,
        )

        student_owner_id = int(dependent["id"])
        email_p4ed = dependent.get("emailP4ed") or dependent.get("email")
        origin_id = dependent.get("originId") or dependent.get("originID")
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
        },
        "calendar": {
            "owner_id": student_owner_id,
            "role_pmais_id": CALENDAR_ROLE_ALUNO,
            "time_zone": DEFAULT_TIMEZONE,
            "is_widget": False,
        },
    }
