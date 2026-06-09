from __future__ import annotations

import hashlib
import time
from typing import Any

from .auth import login_with_password, normalize_token
from .config_loader import load_config, load_config_from_env, merge_discovered_config
from .profile_discovery import (
    ProfileChoiceRequired,
    ProfileDiscoveryError,
    discover_profile_config,
)
from .services import PoliedroService

DEFAULT_BASE_URL = "https://poliedro-api.p4ed.com"
DEFAULT_NOTIFICATIONS = {
    "page": 1,
    "limit": 50,
    "notification_type": "JUST_IN_APP",
    "status": "UNREAD",
}

_PROFILE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 1800


def get_base_config() -> dict[str, Any]:
    from_env = load_config_from_env()
    if from_env is not None:
        return from_env

    try:
        return load_config()
    except FileNotFoundError:
        return {
            "base_url": DEFAULT_BASE_URL,
            "auth": {"username": ""},
            "student": {},
            "calendar": {
                "time_zone": "America/Sao_Paulo",
                "is_widget": False,
            },
            "notifications": DEFAULT_NOTIFICATIONS,
        }


def _cache_key(
    access_token: str,
    *,
    school_id: int | None,
    dependent_id: int | None,
) -> str:
    raw = f"{access_token}:{school_id}:{dependent_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def build_config_for_token(
    access_token: str,
    *,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> dict[str, Any]:
    """Monta config completo a partir do JWT do Poliedro (com cache em memória)."""
    key = _cache_key(access_token, school_id=school_id, dependent_id=dependent_id)
    now = time.time()
    cached = _PROFILE_CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    base = get_base_config()
    discovered = discover_profile_config(
        base["base_url"],
        access_token,
        interactive=False,
        school_id=school_id,
        dependent_id=dependent_id,
    )
    merged = merge_discovered_config(base, discovered)
    merged.setdefault("notifications", DEFAULT_NOTIFICATIONS)
    _PROFILE_CACHE[key] = (now, merged)
    return merged


def login_and_build_profile(
    username: str,
    password: str,
    *,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> dict[str, Any]:
    """Autentica no P+ e retorna token + perfil descoberto."""
    base = get_base_config()
    base_url = base["base_url"].rstrip("/")

    tokens = login_with_password(base_url, username, password)
    access_token = tokens["access_token"]
    discovered = discover_profile_config(
        base_url,
        access_token,
        interactive=False,
        school_id=school_id,
        dependent_id=dependent_id,
    )
    config = merge_discovered_config(base, discovered)
    config.setdefault("notifications", DEFAULT_NOTIFICATIONS)

    return {
        "access_token": access_token,
        "expires_in": tokens.get("expires_in"),
        "token_type": tokens.get("token_type", "Bearer"),
        "profile": {
            "username": config["auth"]["username"],
            "school_id": config["student"]["school_id"],
            "school_year": config["student"]["school_year"],
            "email_p4ed": config["student"]["email_p4ed"],
            "enrollment_id": config["student"]["enrollment_id"],
            "origin_id": config["student"]["origin_id"],
            "role_id": config["student"]["role_id"],
            "calendar_owner_id": config["calendar"]["owner_id"],
        },
    }


def get_service(
    access_token: str | None = None,
    *,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> PoliedroService:
    """
    Retorna serviço para o usuário da requisição.

    Com access_token: usa o JWT do Poliedro enviado pelo cliente.
    Sem access_token: usa config global (POLIEDRO_CONFIG_JSON, config.json ou Keychain).
    """
    if access_token:
        token = normalize_token(access_token)
        config = build_config_for_token(
            token,
            school_id=school_id,
            dependent_id=dependent_id,
        )
        return PoliedroService(config, access_token=token)
    return PoliedroService()


__all__ = [
    "ProfileChoiceRequired",
    "ProfileDiscoveryError",
    "build_config_for_token",
    "get_service",
    "login_and_build_profile",
]
