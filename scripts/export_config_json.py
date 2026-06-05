#!/usr/bin/env python3
"""Exporta config/config.json como linha única para POLIEDRO_CONFIG_JSON no Render."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.json"


def main() -> None:
    if not CONFIG_PATH.exists():
        print(
            f"Arquivo não encontrado: {CONFIG_PATH}\n"
            "Rode primeiro: python -m poliedro_mcp.setup_login",
            file=sys.stderr,
        )
        sys.exit(1)

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
