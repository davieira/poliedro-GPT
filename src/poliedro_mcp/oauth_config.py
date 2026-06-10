"""Exibe configuração para ChatGPT Actions e Claude MCP remoto."""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import requests

from .config_loader import project_root

DEFAULT_CLIENT_ID = "poliedro-gpt"
DEFAULT_SCOPE = "openid profile email"
CHATGPT_METADATA_PATH = "/.well-known/oauth-authorization-server"
MCP_METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
MCP_OAUTH_METADATA_PATH = "/.well-known/oauth-authorization-server/mcp"


def _load_dotenv() -> None:
    env_path = project_root() / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _normalize_base_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL inválida: {url}")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _resolve_base_url(cli_url: str | None) -> str:
    if cli_url:
        return _normalize_base_url(cli_url)

    for key in ("API_BASE_URL", "RENDER_EXTERNAL_URL"):
        value = os.getenv(key, "").strip()
        if value:
            return _normalize_base_url(value)

    raise ValueError(
        "Informe a URL da API como argumento ou defina API_BASE_URL / RENDER_EXTERNAL_URL."
    )


def _fetch_json(url: str) -> dict:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"


def build_config(base_url: str) -> dict[str, object]:
    chatgpt_metadata: dict = {}
    try:
        chatgpt_metadata = _fetch_json(f"{base_url}{CHATGPT_METADATA_PATH}")
    except requests.RequestException as exc:
        print(f"Aviso: metadados ChatGPT indisponíveis ({exc}).", file=sys.stderr)

    client_id = os.getenv("OAUTH_CLIENT_ID", DEFAULT_CLIENT_ID).strip() or DEFAULT_CLIENT_ID
    client_secret = os.getenv("OAUTH_CLIENT_SECRET", "").strip()

    auth_url = chatgpt_metadata.get("authorization_endpoint") or f"{base_url}/oauth/authorize"
    token_url = chatgpt_metadata.get("token_endpoint") or f"{base_url}/oauth/token"

    mcp_connector_url = f"{base_url}/mcp"
    mcp_metadata_url = f"{base_url}{MCP_METADATA_PATH}"
    mcp_auth_metadata_url = f"{base_url}{MCP_OAUTH_METADATA_PATH}"

    return {
        "base_url": base_url,
        "chatgpt": {
            "client_id": client_id,
            "client_secret": client_secret,
            "authorization_url": auth_url,
            "token_url": token_url,
            "scope": DEFAULT_SCOPE,
            "openapi_url": f"{base_url}/openapi.json",
            "metadata_url": f"{base_url}{CHATGPT_METADATA_PATH}",
            "token_exchange_method": "Default (POST request)",
        },
        "claude": {
            "connector_url": mcp_connector_url,
            "metadata_url": mcp_metadata_url,
            "authorization_metadata_url": mcp_auth_metadata_url,
            "oauth_mode": "automatic (DCR)",
        },
    }


def print_human(config: dict[str, object]) -> None:
    chatgpt = config["chatgpt"]
    assert isinstance(chatgpt, dict)
    claude = config["claude"]
    assert isinstance(claude, dict)

    secret = str(chatgpt.get("client_secret") or "")
    secret_display = secret if secret else "(não definido — copie do Render → Environment)"

    print()
    print("=" * 50)
    print("  ChatGPT Actions")
    print("=" * 50)
    print()
    print(f"  Client ID          : {chatgpt['client_id']}")
    print(f"  Client Secret      : {secret_display}")
    print(f"  Authorization URL  : {chatgpt['authorization_url']}")
    print(f"  Token URL          : {chatgpt['token_url']}")
    print(f"  Scope              : {chatgpt['scope']}")
    print()
    print("  Extras")
    print(f"    OpenAPI (importar) : {chatgpt['openapi_url']}")
    print(f"    Metadados OAuth    : {chatgpt['metadata_url']}")
    print()
    print("  Como configurar")
    print("    1. Custom GPT → Actions → Create new action")
    print(f"    2. Schema → Import from URL: {chatgpt['openapi_url']}")
    print("    3. Authentication → OAuth → cole Client ID, Secret, URLs e Scope acima")
    print(f"    4. Token Exchange Method: {chatgpt['token_exchange_method']}")
    print()

    if not secret:
        print("  Client Secret ausente localmente:")
        print("    1. Render Dashboard → seu serviço → Environment")
        print("    2. Revele OAUTH_CLIENT_SECRET (ou gere: openssl rand -hex 32)")
        print("    3. Cole o mesmo valor no ChatGPT e no Render")
        print()
    elif sys.stdout.isatty():
        print(f"  (secret local detectado: {_mask_secret(secret)})")
        print()

    print("=" * 50)
    print("  Claude (MCP remoto)")
    print("=" * 50)
    print()
    print(f"  Connector URL      : {claude['connector_url']}")
    print(f"  Metadados MCP      : {claude['metadata_url']}")
    print(f"  OAuth MCP          : {claude['oauth_mode']}")
    print()
    print("  Como configurar")
    print("    1. Claude → Settings → Connectors → Add custom connector")
    print(f"    2. Cole a Connector URL: {claude['connector_url']}")
    print("    3. Conecte e faça login com sua conta P+ (pmais.p4ed.com)")
    print("    (Não precisa Client ID, Secret nem URLs de token — OAuth é automático.)")
    print()
    print(f"  Guia: docs/claude-remote-setup.md")
    print()


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Mostra configuração para ChatGPT Actions e Claude MCP remoto.",
    )
    parser.add_argument(
        "base_url",
        nargs="?",
        help="URL da API (ex.: https://api.iden.is)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Saída em JSON (client_secret omitido se vazio)",
    )
    args = parser.parse_args(argv)

    try:
        base_url = _resolve_base_url(args.base_url)
        config = build_config(base_url)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        payload: dict[str, object] = {
            "base_url": config["base_url"],
            "chatgpt": dict(config["chatgpt"]),  # type: ignore[arg-type]
            "claude": config["claude"],
        }
        chatgpt_json = payload["chatgpt"]
        assert isinstance(chatgpt_json, dict)
        if not chatgpt_json.get("client_secret"):
            chatgpt_json.pop("client_secret", None)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print_human(config)


if __name__ == "__main__":
    main()
