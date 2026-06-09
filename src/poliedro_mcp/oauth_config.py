"""Exibe configuração OAuth para ChatGPT Actions."""

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
METADATA_PATH = "/.well-known/oauth-authorization-server"


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


def _fetch_metadata(base_url: str) -> dict:
    url = f"{base_url}{METADATA_PATH}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"


def build_config(base_url: str, metadata: dict | None = None) -> dict[str, str]:
    if metadata is None:
        try:
            metadata = _fetch_metadata(base_url)
        except requests.RequestException as exc:
            print(f"Aviso: não foi possível buscar metadados ({exc}).", file=sys.stderr)
            metadata = {}

    client_id = os.getenv("OAUTH_CLIENT_ID", DEFAULT_CLIENT_ID).strip() or DEFAULT_CLIENT_ID
    client_secret = os.getenv("OAUTH_CLIENT_SECRET", "").strip()

    auth_url = metadata.get("authorization_endpoint") or f"{base_url}/oauth/authorize"
    token_url = metadata.get("token_endpoint") or f"{base_url}/oauth/token"

    return {
        "base_url": base_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "authorization_url": auth_url,
        "token_url": token_url,
        "scope": DEFAULT_SCOPE,
        "openapi_url": f"{base_url}/openapi.json",
        "metadata_url": f"{base_url}{METADATA_PATH}",
        "mcp_connector_url": f"{base_url}/mcp",
        "mcp_metadata_url": f"{base_url}/.well-known/oauth-protected-resource/mcp",
    }


def print_human(config: dict[str, str]) -> None:
    secret = config["client_secret"]
    secret_display = secret if secret else "(não definido — copie do Render → Environment)"

    print()
    print("=== OAuth para ChatGPT Actions ===")
    print()
    print(f"  Client ID          : {config['client_id']}")
    print(f"  Client Secret      : {secret_display}")
    print(f"  Authorization URL  : {config['authorization_url']}")
    print(f"  Token URL          : {config['token_url']}")
    print(f"  Scope              : {config['scope']}")
    print()
    print("--- Extras ---")
    print(f"  OpenAPI (importar) : {config['openapi_url']}")
    print(f"  Metadados OAuth    : {config['metadata_url']}")
    print()
    print("=== MCP remoto (Claude Connectors) ===")
    print()
    print(f"  Connector URL      : {config['mcp_connector_url']}")
    print(f"  Metadados MCP      : {config['mcp_metadata_url']}")
    print()
    print("No Claude: Settings → Connectors → Add custom connector → cole a Connector URL.")
    print("OAuth é automático (DCR); não precisa Client ID/Secret manual.")
    print()
    print("No ChatGPT: Actions → Authentication → OAuth → cole os valores acima.")
    print("Token Exchange Method: Default (POST request)")
    print()

    if not secret:
        print("Como obter o Client Secret:")
        print("  1. Render Dashboard → seu serviço → Environment")
        print("  2. Revele OAUTH_CLIENT_SECRET (ou gere: openssl rand -hex 32)")
        print("  3. Cole o mesmo valor no ChatGPT e no Render")
        print()
    elif sys.stdout.isatty():
        print(f"  (secret local detectado: {_mask_secret(secret)})")
        print()


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Mostra configuração OAuth para ChatGPT Actions.",
    )
    parser.add_argument(
        "base_url",
        nargs="?",
        help="URL da API (ex.: https://poliedro-api.onrender.com)",
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
        payload = {**config}
        if not payload["client_secret"]:
            payload.pop("client_secret")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print_human(config)


if __name__ == "__main__":
    main()
