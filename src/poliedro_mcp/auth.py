from __future__ import annotations

import os
from typing import Any

import keyring
import requests

SERVICE = "poliedro-pmais"


class LoginError(RuntimeError):
    """Falha de autenticação no SSO do Poliedro."""


def save_credentials(username: str, password: str) -> None:
    keyring.set_password(SERVICE, username, password)


def get_password(username: str) -> str | None:
    return keyring.get_password(SERVICE, username)


def login_with_password(base_url: str, username: str, password: str) -> dict[str, Any]:
    """
    Tenta login via Resource Owner Password Flow do Keycloak.

    Observação: alguns ambientes Keycloak bloqueiam esse grant.
    Se falhar com 400/401, será necessário implementar login via browser/OAuth.
    """
    url = f"{base_url}/sso/auth/realms/poliedro/protocol/openid-connect/token"

    data = {
        "grant_type": "password",
        "client_id": "pmais",
        "username": username,
        "password": password,
        "scope": "openid profile email",
    }

    response = requests.post(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )

    if response.status_code >= 400:
        body = response.text
        if response.status_code == 401 and "invalid_grant" in body:
            raise LoginError(
                "Usuário ou senha incorretos. Use as mesmas credenciais do "
                "https://pmais.p4ed.com/ (usuário sem @p4ed.com)."
            )
        raise LoginError(
            f"Falha no login Poliedro. HTTP {response.status_code}: {body}"
        )

    return response.json()


def get_manual_token() -> str | None:
    token = os.getenv("POLIEDRO_TOKEN")
    if not token:
        return None
    if token.lower().startswith("bearer "):
        token = token[7:]
    return token.strip().replace("\n", "").replace("\r", "")
