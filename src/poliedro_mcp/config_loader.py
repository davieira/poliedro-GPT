from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config_path() -> Path:
    env_path = os.getenv("POLIEDRO_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return project_root() / "config" / "config.json"


def load_config_from_env() -> dict[str, Any] | None:
    raw = os.getenv("POLIEDRO_CONFIG_JSON", "").strip()
    if not raw:
        return None
    return json.loads(raw)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    from_env = load_config_from_env()
    if from_env is not None:
        return from_env

    config_path = Path(path).expanduser().resolve() if path else default_config_path()

    if not config_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {config_path}. "
            "Copie config/config.example.json para config/config.json "
            "ou defina POLIEDRO_CONFIG_JSON."
        )

    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict[str, Any], path: str | Path | None = None) -> Path:
    config_path = Path(path).expanduser().resolve() if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return config_path


def merge_discovered_config(
    base_config: dict[str, Any],
    discovered: dict[str, Any],
) -> dict[str, Any]:
    """Preserva base_url e notifications; atualiza auth, student e calendar."""
    merged = json.loads(json.dumps(base_config))
    merged["auth"] = discovered["auth"]
    merged["student"] = discovered["student"]
    merged["calendar"] = discovered["calendar"]
    return merged
