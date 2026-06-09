from __future__ import annotations

import os


def api_base_url() -> str:
    for key in ("API_BASE_URL", "RENDER_EXTERNAL_URL"):
        url = os.getenv(key, "").strip().rstrip("/")
        if url:
            return url
    return "https://poliedro-api.onrender.com"


def mcp_base_url() -> str:
    return f"{api_base_url()}/mcp"
