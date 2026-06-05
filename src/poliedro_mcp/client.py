from __future__ import annotations

from typing import Any

import requests

from .auth import get_manual_token, get_password, login_with_password
from .config_loader import load_config


class PoliedroClient:
    def __init__(self) -> None:
        self.config = load_config()
        self.base_url = self.config["base_url"].rstrip("/")
        self.session = requests.Session()
        self._access_token: str | None = None
        self.authenticate()

    def authenticate(self) -> None:
        manual_token = get_manual_token()

        if manual_token:
            access_token = manual_token
        else:
            username = self.config.get("auth", {}).get("username")
            if not username:
                raise RuntimeError(
                    "Informe auth.username em config/config.json ou use POLIEDRO_TOKEN."
                )

            password = get_password(username)
            if not password:
                raise RuntimeError(
                    "Senha não encontrada no Keychain. Rode: python -m poliedro_mcp.setup_login"
                )

            tokens = login_with_password(self.base_url, username, password)
            access_token = tokens["access_token"]

        self._access_token = access_token
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://pmais.p4ed.com",
            "Referer": "https://pmais.p4ed.com/",
            "User-Agent": "Poliedro-MCP/0.1",
        })

    def get(self, path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
        url = f"{self.base_url}{path}"

        response = self.session.get(url, params=params, timeout=timeout)

        if response.status_code == 401:
            self.authenticate()
            response = self.session.get(url, params=params, timeout=timeout)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Erro Poliedro API HTTP {response.status_code} em {response.url}: "
                f"{response.text}"
            )

        return response.json()
