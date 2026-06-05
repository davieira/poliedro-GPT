from __future__ import annotations

import getpass
import sys

from .auth import LoginError, login_with_password, save_credentials
from .config_loader import (
    default_config_path,
    load_config,
    merge_discovered_config,
    save_config,
)
from .profile_discovery import ProfileDiscoveryError, discover_profile_config

PLACEHOLDER_USERNAMES = {"", "SEU_USUARIO_PMAIS", "SEU_USUARIO"}


def _resolve_username(cfg: dict) -> str:
    username = (cfg.get("auth") or {}).get("username", "").strip()
    if username and username not in PLACEHOLDER_USERNAMES:
        return username

    typed = input("Usuário P+/Poliedro: ").strip()
    if not typed:
        raise RuntimeError("Usuário é obrigatório.")
    return typed


def main() -> None:
    config_path = default_config_path()

    try:
        cfg = load_config()
    except FileNotFoundError:
        raise RuntimeError(
            f"Crie {config_path} a partir de config/config.example.json antes do setup."
        ) from None

    base_url = cfg["base_url"].rstrip("/")
    username = _resolve_username(cfg)

    tokens: dict | None = None
    while tokens is None:
        password = getpass.getpass("Senha do P+/Poliedro: ")
        try:
            tokens = login_with_password(base_url, username, password)
        except LoginError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            retry = input("Tentar novamente? [S/n]: ").strip().lower()
            if retry in ("n", "no", "nao", "não"):
                raise SystemExit(1) from exc

    if "access_token" not in tokens:
        raise RuntimeError(f"Login retornou resposta inesperada: {tokens}")

    access_token = tokens["access_token"]
    save_credentials(username, password)

    try:
        discovered = discover_profile_config(base_url, access_token, interactive=True)
    except ProfileDiscoveryError as exc:
        print(f"Login OK, mas falha ao montar config: {exc}", file=sys.stderr)
        print("Credenciais salvas no Keychain. Ajuste config/config.json manualmente.")
        raise SystemExit(1) from exc

    updated = merge_discovered_config(cfg, discovered)
    saved_path = save_config(updated)

    student = updated["student"]
    calendar = updated["calendar"]

    print("Login OK. Credenciais salvas no Keychain.")
    print(f"Config atualizado: {saved_path}")
    print(f"  username: {updated['auth']['username']}")
    print(f"  school_id: {student['school_id']}, school_year: {student['school_year']}")
    print(f"  email_p4ed: {student['email_p4ed']}")
    print(f"  enrollment_id: {student['enrollment_id']}, origin_id: {student['origin_id']}")
    print(f"  calendar owner_id: {calendar['owner_id']}, role_pmais_id: {calendar['role_pmais_id']}")


if __name__ == "__main__":
    main()
