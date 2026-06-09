from __future__ import annotations

from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


def privacy_policy_html() -> str:
    """HTML público da política de privacidade (Custom GPT / Claude)."""
    return (_DOCS_DIR / "privacy-policy.html").read_text(encoding="utf-8")


__all__ = ["privacy_policy_html"]
