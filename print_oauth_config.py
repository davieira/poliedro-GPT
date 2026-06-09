#!/usr/bin/env python3
"""Atalho na raiz do repo. Uso: python print_oauth_config.py [URL_DA_API]"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from poliedro_mcp.oauth_config import main

if __name__ == "__main__":
    main()
