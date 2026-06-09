from __future__ import annotations

import html
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .auth import LoginError, login_with_password, refresh_access_token
from .logger import logger
from .profile_discovery import ProfileChoiceRequired
from .user_context import get_base_config

router = APIRouter(tags=["oauth"])

AUTH_CODE_TTL_SECONDS = 120
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30

DEFAULT_REDIRECT_PREFIXES = (
    "https://chatgpt.com/aip/",
    "https://chat.openai.com/aip/",
)
GITHUB_REPO_URL = "https://github.com/davieira/poliedro-GPT"


@dataclass
class _TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_in: int
    redirect_uri: str
    client_id: str


_auth_codes: dict[str, tuple[float, _TokenBundle]] = {}
_refresh_tokens: dict[str, tuple[float, _TokenBundle]] = {}


def _oauth_client_id() -> str:
    return os.getenv("OAUTH_CLIENT_ID", "poliedro-gpt").strip()


def _oauth_client_secret() -> str:
    secret = os.getenv("OAUTH_CLIENT_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "OAUTH_CLIENT_SECRET não configurada. "
            "Defina no Render antes de usar OAuth com ChatGPT."
        )
    return secret


def _allowed_redirect_prefixes() -> tuple[str, ...]:
    raw = os.getenv("OAUTH_ALLOWED_REDIRECT_PREFIXES", "").strip()
    if not raw:
        return DEFAULT_REDIRECT_PREFIXES
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _purge_expired() -> None:
    now = time.time()
    for store, ttl in ((_auth_codes, AUTH_CODE_TTL_SECONDS), (_refresh_tokens, REFRESH_TOKEN_TTL_SECONDS)):
        expired = [key for key, (created, _) in store.items() if now - created > ttl]
        for key in expired:
            store.pop(key, None)


def _validate_redirect_uri(redirect_uri: str) -> None:
    prefixes = _allowed_redirect_prefixes()
    if not any(redirect_uri.startswith(prefix) for prefix in prefixes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "redirect_uri não permitido. "
                f"Use um callback do ChatGPT ({', '.join(prefixes)})."
            ),
        )


def _validate_client_id(client_id: str) -> None:
    if not secrets.compare_digest(client_id, _oauth_client_id()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="client_id inválido.",
        )


def _validate_client_secret(client_secret: str) -> None:
    expected = _oauth_client_secret()
    if not secrets.compare_digest(client_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="client_secret inválido.",
        )


def _login_html(
    *,
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    response_type: str = "code",
    scope: str | None = None,
    form_action: str = "/oauth/authorize",
    pending: str | None = None,
    error: str | None = None,
    choice_error: dict[str, Any] | None = None,
) -> str:
    oauth_hidden = ""
    if pending:
        oauth_hidden += f'<input type="hidden" name="pending" value="{html.escape(pending)}">'
    if client_id:
        oauth_hidden += f'<input type="hidden" name="client_id" value="{html.escape(client_id)}">'
    if redirect_uri:
        oauth_hidden += f'<input type="hidden" name="redirect_uri" value="{html.escape(redirect_uri)}">'
    if state:
        oauth_hidden += f'<input type="hidden" name="state" value="{html.escape(state)}">'
    if response_type:
        oauth_hidden += (
            f'<input type="hidden" name="response_type" value="{html.escape(response_type)}">'
        )
    if scope:
        oauth_hidden += f'<input type="hidden" name="scope" value="{html.escape(scope)}">'
    error_block = ""
    if error:
        error_block = f'<p class="error">{html.escape(error)}</p>'
    if choice_error:
        options = choice_error.get("opcoes") or []
        tipo = choice_error.get("tipo", "opção")
        lines = "".join(
            f"<li><code>{html.escape(str(item))}</code></li>" for item in options
        )
        error_block += (
            f'<p class="error">Escolha necessária ({html.escape(tipo)}). '
            "Informe o ID correspondente abaixo.</p>"
            f"<ul>{lines}</ul>"
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Entrar no Poliedro P+</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #f4f6f8; margin: 0; }}
    main {{ max-width: 420px; margin: 48px auto; background: #fff; padding: 28px; border-radius: 12px;
             box-shadow: 0 8px 24px rgba(0,0,0,.08); }}
    h1 {{ font-size: 1.25rem; margin: 0 0 8px; }}
    p {{ color: #555; margin: 0 0 20px; line-height: 1.4; }}
    label {{ display: block; font-size: .9rem; margin-bottom: 6px; color: #333; }}
    input {{ width: 100%; box-sizing: border-box; padding: 10px 12px; margin-bottom: 14px;
             border: 1px solid #ccd3db; border-radius: 8px; font-size: 1rem; }}
    button {{ width: 100%; padding: 12px; border: 0; border-radius: 8px; background: #1a5fb4;
              color: #fff; font-size: 1rem; cursor: pointer; }}
    .error {{ color: #b00020; }}
    .hint {{ font-size: .85rem; color: #666; }}
    .notice {{ font-size: .85rem; color: #333; background: #eef4fc; border: 1px solid #c5d9f0;
               border-radius: 8px; padding: 12px 14px; margin-bottom: 20px; line-height: 1.45; }}
    .notice strong {{ color: #1a5fb4; }}
    footer {{ max-width: 420px; margin: 16px auto 48px; text-align: center; font-size: .8rem; color: #666; }}
    footer a {{ color: #1a5fb4; }}
    ul {{ font-size: .85rem; }}
  </style>
</head>
<body>
  <main>
    <h1>Poliedro P+</h1>
    <p>Use o mesmo usuário e senha do portal <strong>pmais.p4ed.com</strong>.</p>
    <div class="notice" role="note">
      <strong>Privacidade:</strong> suas credenciais são usadas apenas para autenticar
      diretamente nos servidores do Poliedro (P+). Elas <strong>não são armazenadas</strong>
      neste serviço — nem em disco, banco de dados ou logs — em hipótese alguma.
      <a href="/privacy">Política de privacidade</a>
    </div>
    {error_block}
    <form method="post" action="{html.escape(form_action)}">
      {oauth_hidden}
      <label for="username">Usuário</label>
      <input id="username" name="username" autocomplete="username" required>
      <label for="password">Senha</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <label for="school_id">ID da escola (opcional)</label>
      <input id="school_id" name="school_id" inputmode="numeric" placeholder="Somente se solicitado">
      <label for="dependent_id">ID do dependente (opcional)</label>
      <input id="dependent_id" name="dependent_id" inputmode="numeric" placeholder="Contas de responsável">
      <p class="hint">Usuário sem @p4ed.com.</p>
      <button type="submit">Entrar</button>
    </form>
  </main>
  <footer>Projeto open source não oficial </footer>
</body>
</html>"""


def _redirect_with_code(redirect_uri: str, code: str, state: str) -> RedirectResponse:
    params = {"code": code, "state": state}
    separator = "&" if urlparse(redirect_uri).query else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{urlencode(params)}", status_code=302)


def _issue_tokens(
    *,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
    redirect_uri: str,
    client_id: str,
) -> str:
    _purge_expired()
    code = secrets.token_urlsafe(32)
    bundle = _TokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        redirect_uri=redirect_uri,
        client_id=client_id,
    )
    _auth_codes[code] = (time.time(), bundle)
    return code


def _store_refresh_bundle(refresh_key: str, bundle: _TokenBundle) -> None:
    _purge_expired()
    _refresh_tokens[refresh_key] = (time.time(), bundle)


def _parse_optional_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


@router.get("/oauth/authorize")
def oauth_authorize_get(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: str = Query(...),
    response_type: str = Query(default="code"),
    scope: str | None = Query(default=None),
) -> HTMLResponse:
    """Inicia o fluxo OAuth (ChatGPT) e exibe o formulário de login P+."""
    if response_type != "code":
        raise HTTPException(status_code=400, detail="response_type deve ser code.")
    if not state:
        raise HTTPException(status_code=400, detail="state é obrigatório.")

    _validate_client_id(client_id)
    _validate_redirect_uri(redirect_uri)

    return HTMLResponse(
        _login_html(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            response_type=response_type,
            scope=scope,
        )
    )


@router.post("/oauth/authorize", response_model=None)
def oauth_authorize_post(
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(...),
    response_type: str = Form(default="code"),
    scope: str | None = Form(default=None),
    username: str = Form(...),
    password: str = Form(...),
    school_id: str | None = Form(default=None),
    dependent_id: str | None = Form(default=None),
) -> Response:
    """Valida credenciais P+ e redireciona de volta ao ChatGPT com authorization code."""
    _validate_client_id(client_id)
    _validate_redirect_uri(redirect_uri)

    if response_type != "code":
        raise HTTPException(status_code=400, detail="response_type deve ser code.")

    base = get_base_config()
    base_url = base["base_url"].rstrip("/")
    parsed_school_id = _parse_optional_int(school_id)
    parsed_dependent_id = _parse_optional_int(dependent_id)

    try:
        tokens = login_with_password(base_url, username.strip(), password)
    except LoginError as exc:
        return HTMLResponse(
            _login_html(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state,
                response_type=response_type,
                scope=scope,
                error=str(exc),
            ),
            status_code=401,
        )

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = int(tokens.get("expires_in") or 300)

    try:
        from .profile_discovery import discover_profile_config

        discover_profile_config(
            base_url,
            access_token,
            interactive=False,
            school_id=parsed_school_id,
            dependent_id=parsed_dependent_id,
        )
    except ProfileChoiceRequired as exc:
        return HTMLResponse(
            _login_html(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state,
                response_type=response_type,
                scope=scope,
                choice_error={"tipo": exc.choice_type, "opcoes": exc.options},
            ),
            status_code=409,
        )
    except Exception as exc:
        return HTMLResponse(
            _login_html(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state,
                response_type=response_type,
                scope=scope,
                error=f"Não foi possível carregar o perfil: {exc}",
            ),
            status_code=400,
        )

    code = _issue_tokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        redirect_uri=redirect_uri,
        client_id=client_id,
    )

    logger.info("OAuth login concluído para usuário=%s", username.strip())
    return _redirect_with_code(redirect_uri, code, state)


@router.post("/oauth/token")
async def oauth_token(request: Request) -> JSONResponse:
    """Troca authorization code (ou refresh_token) por access_token para o ChatGPT."""
    _purge_expired()

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
    else:
        body = dict(await request.form())

    grant_type = str(body.get("grant_type", "")).strip()
    client_id = str(body.get("client_id", "")).strip()
    client_secret = str(body.get("client_secret", "")).strip()

    _validate_client_id(client_id)
    _validate_client_secret(client_secret)

    if grant_type == "authorization_code":
        code = str(body.get("code", "")).strip()
        redirect_uri = str(body.get("redirect_uri", "")).strip()
        if not code or not redirect_uri:
            raise HTTPException(status_code=400, detail="code e redirect_uri são obrigatórios.")

        entry = _auth_codes.pop(code, None)
        if entry is None:
            raise HTTPException(status_code=400, detail="code inválido ou expirado.")

        created, bundle = entry
        if time.time() - created > AUTH_CODE_TTL_SECONDS:
            raise HTTPException(status_code=400, detail="code expirado.")

        if bundle.redirect_uri != redirect_uri:
            raise HTTPException(status_code=400, detail="redirect_uri não confere.")

        refresh_key = secrets.token_urlsafe(32) if bundle.refresh_token else None
        if refresh_key and bundle.refresh_token:
            _store_refresh_bundle(refresh_key, bundle)

        return JSONResponse({
            "access_token": bundle.access_token,
            "token_type": "bearer",
            "expires_in": bundle.expires_in,
            **({"refresh_token": refresh_key} if refresh_key else {}),
        })

    if grant_type == "refresh_token":
        refresh_key = str(body.get("refresh_token", "")).strip()
        entry = _refresh_tokens.get(refresh_key)
        if entry is None:
            raise HTTPException(status_code=400, detail="refresh_token inválido.")

        created, bundle = entry
        if time.time() - created > REFRESH_TOKEN_TTL_SECONDS:
            _refresh_tokens.pop(refresh_key, None)
            raise HTTPException(status_code=400, detail="refresh_token expirado.")

        if not bundle.refresh_token:
            raise HTTPException(status_code=400, detail="refresh_token indisponível.")

        base = get_base_config()
        try:
            tokens = refresh_access_token(base["base_url"], bundle.refresh_token)
        except LoginError as exc:
            _refresh_tokens.pop(refresh_key, None)
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        new_bundle = _TokenBundle(
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token") or bundle.refresh_token,
            expires_in=int(tokens.get("expires_in") or bundle.expires_in),
            redirect_uri=bundle.redirect_uri,
            client_id=bundle.client_id,
        )
        new_refresh_key = secrets.token_urlsafe(32)
        _refresh_tokens.pop(refresh_key, None)
        _store_refresh_bundle(new_refresh_key, new_bundle)

        return JSONResponse({
            "access_token": new_bundle.access_token,
            "token_type": "bearer",
            "expires_in": new_bundle.expires_in,
            "refresh_token": new_refresh_key,
        })

    raise HTTPException(status_code=400, detail="grant_type não suportado.")


@router.get("/.well-known/oauth-authorization-server")
def oauth_metadata(request: Request) -> dict[str, Any]:
    """Metadados OAuth (útil para integrações que descobrem endpoints automaticamente)."""
    base = str(request.base_url).rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
    }
