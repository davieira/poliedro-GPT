from __future__ import annotations

import base64
import hashlib
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
from .mcp_oauth_tokens import mint_login_choice_token, mint_session_access_token, parse_login_choice_token
from .profile_discovery import ProfileChoiceRequired
from .user_context import get_base_config

router = APIRouter(tags=["oauth"])

AUTH_CODE_TTL_SECONDS = 120
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30

DEFAULT_REDIRECT_PREFIXES = (
    "https://chatgpt.com/aip/",
    "https://chat.openai.com/aip/",
)
DEFAULT_REDIRECT_HOSTS = (
    "chatgpt.com",
    "www.chatgpt.com",
    "chat.openai.com",
    "platform.openai.com",
)
GITHUB_REPO_URL = "https://github.com/davieira/poliedro-GPT"


@dataclass
class _TokenBundle:
    access_token: str
    refresh_token: str | None
    expires_in: int
    redirect_uri: str
    client_id: str
    code_challenge: str | None = None
    code_challenge_method: str | None = None


_auth_codes: dict[str, tuple[float, _TokenBundle]] = {}
_refresh_tokens: dict[str, tuple[float, _TokenBundle]] = {}


def _oauth_client_id() -> str:
    return os.getenv("OAUTH_CLIENT_ID", "poliedro-gpt").strip()


def _effective_client_id(client_id: str | None) -> str:
    """ChatGPT às vezes omite client_id na URL de authorize — usa o padrão do servidor."""
    if client_id and client_id.strip():
        return client_id.strip()
    return _oauth_client_id()


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
    parsed = urlparse(redirect_uri)
    host = (parsed.hostname or "").lower()
    prefixes = _allowed_redirect_prefixes()
    if any(redirect_uri.startswith(prefix) for prefix in prefixes):
        return
    if parsed.scheme == "https" and (
        host in DEFAULT_REDIRECT_HOSTS
        or host.endswith(".chatgpt.com")
        or host.endswith(".openai.com")
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "redirect_uri não permitido. "
            f"Use um callback do ChatGPT ({', '.join(prefixes)})."
        ),
    )


def _verify_pkce(code_verifier: str, challenge: str, method: str) -> bool:
    method = (method or "S256").strip()
    if method == "plain":
        return secrets.compare_digest(code_verifier, challenge)
    if method.upper() != "S256":
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, challenge)


def _validate_client_id(client_id: str | None) -> str:
    effective = _effective_client_id(client_id)
    if not secrets.compare_digest(effective, _oauth_client_id()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="client_id inválido.",
        )
    return effective


def _validate_client_secret(client_secret: str) -> None:
    expected = _oauth_client_secret()
    if not secrets.compare_digest(client_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="client_secret inválido.",
        )


def _extract_client_credentials(request: Request, body: dict[str, Any]) -> tuple[str, str]:
    """
    Lê client_id/client_secret do body (client_secret_post) ou Authorization: Basic.

    O ChatGPT Actions costuma usar client_secret_basic mesmo quando o schema declara post.
    """
    client_id = str(body.get("client_id", "")).strip()
    client_secret = str(body.get("client_secret", "")).strip()

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth_header[6:].strip(), validate=True).decode("utf-8")
            basic_id, _, basic_secret = decoded.partition(":")
            if not client_id:
                client_id = basic_id.strip()
            if not client_secret:
                client_secret = basic_secret.strip()
        except (ValueError, UnicodeDecodeError):
            logger.warning("OAuth token: Authorization Basic inválido")

    return client_id, client_secret


def _choice_options_html(choice_error: dict[str, Any]) -> str:
    options = choice_error.get("opcoes") or []
    tipo = str(choice_error.get("tipo") or "opção")
    field = "school_id" if tipo == "escola" else "dependent_id"
    radios = []
    for item in options:
        value = item.get("school_id") if field == "school_id" else item.get("dependent_id")
        if value is None:
            continue
        name = html.escape(str(item.get("name") or f"ID {value}"))
        extra = item.get("email_p4ed") or item.get("role_id")
        hint = f" <span class='hint'>({html.escape(str(extra))})</span>" if extra else ""
        radios.append(
            "<label class='choice'>"
            f"<input type='radio' name='{field}' value='{html.escape(str(value))}' required>"
            f"<span>{name}{hint}</span>"
            "</label>"
        )
    if not radios:
        return (
            f'<p class="error">Escolha necessária ({html.escape(tipo)}), '
            "mas nenhuma opção válida foi retornada.</p>"
        )
    heading = "Escola" if field == "school_id" else "Dependente"
    article = "uma" if field == "school_id" else "um"
    return (
        f'<p class="error">Há mais de {article} {html.escape(heading.lower())} nesta conta. '
        "Selecione a opção abaixo.</p>"
        f'<fieldset class="choices"><legend>{html.escape(heading)}</legend>'
        f"{''.join(radios)}</fieldset>"
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
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> str:
    oauth_hidden = ""
    if pending:
        oauth_hidden += f'<input type="hidden" name="pending" value="{html.escape(pending)}">'
    if login_choice:
        oauth_hidden += (
            f'<input type="hidden" name="login_choice" value="{html.escape(login_choice)}">'
        )
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
    if code_challenge:
        oauth_hidden += (
            f'<input type="hidden" name="code_challenge" value="{html.escape(code_challenge)}">'
        )
    if code_challenge_method:
        oauth_hidden += (
            '<input type="hidden" name="code_challenge_method" '
            f'value="{html.escape(code_challenge_method)}">'
        )
    error_block = ""
    if error:
        error_block = f'<p class="error">{html.escape(error)}</p>'
    if choice_error:
        error_block += _choice_options_html(choice_error)

    authenticated = bool(login_choice)
    credentials_block = ""
    if authenticated:
        credentials_block = (
            f'<input type="hidden" name="username" value="{html.escape(username)}">'
            f'<p class="hint">Conta autenticada: <strong>{html.escape(username)}</strong>. '
            "Escolha a opção abaixo — não é preciso informar a senha de novo.</p>"
        )
    else:
        credentials_block = f"""
      <label for="username">Usuário</label>
      <input id="username" name="username" autocomplete="username" required
             value="{html.escape(username)}">
      <label for="password">Senha</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
"""

    show_manual_ids = choice_error is None and not authenticated
    manual_ids = ""
    if show_manual_ids:
        manual_ids = """
      <label for="school_id">ID da escola (opcional)</label>
      <input id="school_id" name="school_id" inputmode="numeric" placeholder="Somente se solicitado">
      <label for="dependent_id">ID do dependente (opcional)</label>
      <input id="dependent_id" name="dependent_id" inputmode="numeric" placeholder="Contas de responsável">
"""

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
    fieldset.choices {{ border: 1px solid #c5d9f0; border-radius: 8px; margin: 0 0 16px; padding: 10px 12px; }}
    fieldset.choices legend {{ color: #1a5fb4; font-weight: 600; }}
    label.choice {{ display: flex; gap: 10px; align-items: flex-start; margin: 8px 0; font-size: .95rem; }}
    label.choice input {{ width: auto; margin: 4px 0 0; }}
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
      {credentials_block}
      {manual_ids}
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
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
) -> str:
    _purge_expired()
    code = secrets.token_urlsafe(32)
    bundle = _TokenBundle(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        redirect_uri=redirect_uri,
        client_id=client_id,
        code_challenge=code_challenge or None,
        code_challenge_method=code_challenge_method or None,
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


def resolve_form_tokens(
    *,
    base_url: str,
    username: str,
    password: str | None,
    login_choice: str | None,
) -> tuple[dict[str, Any], str, int | None, int | None]:
    """Autentica com senha ou retoma a sessão após escolha de escola/dependente."""
    if login_choice:
        choice = parse_login_choice_token(login_choice)
        if choice is None:
            raise LoginError("Sessão de escolha expirada. Faça login novamente.")
        return (
            {
                "access_token": choice.access_token,
                "refresh_token": choice.refresh_token,
                "expires_in": choice.expires_in,
            },
            choice.username,
            choice.school_id,
            choice.dependent_id,
        )

    if not username.strip() or not (password or "").strip():
        raise LoginError("Usuário e senha são obrigatórios.")

    tokens = login_with_password(base_url, username.strip(), password or "")
    return tokens, username.strip(), None, None


def mint_choice_token(
    tokens: dict[str, Any],
    username: str,
    *,
    school_id: int | None = None,
    dependent_id: int | None = None,
) -> str:
    return mint_login_choice_token(
        access_token=str(tokens["access_token"]),
        refresh_token=tokens.get("refresh_token"),
        expires_in=int(tokens.get("expires_in") or 3600),
        username=username,
        school_id=school_id,
        dependent_id=dependent_id,
    )


def _session_access_token(bundle: _TokenBundle) -> str:
    return mint_session_access_token(
        bundle.access_token,
        expires_in=bundle.expires_in,
        school_id=bundle.school_id,
        dependent_id=bundle.dependent_id,
    )


@router.get("/oauth/authorize")
def oauth_authorize_get(
    request: Request,
    redirect_uri: str | None = Query(default=None),
    state: str | None = Query(default=None),
    response_type: str = Query(default="code"),
    client_id: str = Query(default=""),
    scope: str | None = Query(default=None),
    code_challenge: str | None = Query(default=None),
    code_challenge_method: str | None = Query(default=None),
) -> HTMLResponse:
    """Inicia o fluxo OAuth (ChatGPT) e exibe o formulário de login P+."""
    # ChatGPT (oauth_redirect) às vezes sonda este URL sem query string.
    # 422 aqui derruba o botão "Sign in" antes do redirect.
    if not redirect_uri or not state:
        return HTMLResponse(
            _login_html(
                error="Abra esta tela pelo botão Entrar / Sign in no ChatGPT.",
                form_action="/oauth/authorize",
            )
        )

    if response_type != "code":
        raise HTTPException(status_code=400, detail="response_type deve ser code.")

    effective_client_id = _validate_client_id(client_id)
    _validate_redirect_uri(redirect_uri)
    form_action = str(request.base_url).rstrip("/") + "/oauth/authorize"

    return HTMLResponse(
        _login_html(
            client_id=effective_client_id,
            redirect_uri=redirect_uri,
            state=state,
            response_type=response_type,
            scope=scope,
            form_action=form_action,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
    )


@router.post("/oauth/authorize", response_model=None)
def oauth_authorize_post(
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(...),
    response_type: str = Form(default="code"),
    scope: str | None = Form(default=None),
    username: str = Form(default=""),
    password: str | None = Form(default=None),
    school_id: str | None = Form(default=None),
    dependent_id: str | None = Form(default=None),
    code_challenge: str | None = Form(default=None),
    code_challenge_method: str | None = Form(default=None),
) -> Response:
    """Valida credenciais P+ e redireciona de volta ao ChatGPT com authorization code."""
    effective_client_id = _validate_client_id(client_id)
    _validate_redirect_uri(redirect_uri)

    if response_type != "code":
        raise HTTPException(status_code=400, detail="response_type deve ser code.")

    base = get_base_config()
    base_url = base["base_url"].rstrip("/")
    parsed_school_id = _parse_optional_int(school_id)
    parsed_dependent_id = _parse_optional_int(dependent_id)

    def _form(**kwargs: Any) -> str:
        return _login_html(
            client_id=effective_client_id,
            redirect_uri=redirect_uri,
            state=state,
            response_type=response_type,
            scope=scope,
            **kwargs,
        )

    try:
        tokens, resolved_username, choice_school_id, choice_dependent_id = resolve_form_tokens(
            base_url=base_url,
            username=username,
            password=password,
            login_choice=login_choice,
        )
    except LoginError as exc:
        return HTMLResponse(
            _login_html(
                client_id=effective_client_id,
                redirect_uri=redirect_uri,
                state=state,
                response_type=response_type,
                scope=scope,
                error=str(exc),
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            ),
            status_code=401,
        )

    if parsed_school_id is None:
        parsed_school_id = choice_school_id
    if parsed_dependent_id is None:
        parsed_dependent_id = choice_dependent_id

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")
    expires_in = int(tokens.get("expires_in") or 300)

    try:
        from .profile_discovery import discover_profile_config

        discovered = discover_profile_config(
            base_url,
            access_token,
            interactive=False,
            school_id=parsed_school_id,
            dependent_id=parsed_dependent_id,
        )
    except ProfileChoiceRequired as exc:
        try:
            retry_token = mint_choice_token(
                tokens,
                resolved_username,
                school_id=parsed_school_id,
                dependent_id=parsed_dependent_id,
            )
        except RuntimeError:
            retry_token = None
        return HTMLResponse(
            _form(
                username=resolved_username,
                login_choice=retry_token,
                choice_error={"tipo": exc.choice_type, "opcoes": exc.options},
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            ),
            status_code=409,
        )
    except Exception as exc:
        return HTMLResponse(
            _form(
                username=resolved_username,
                error=f"Não foi possível carregar o perfil: {exc}",
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
            ),
            status_code=400,
        )

    selected_school_id = int(discovered["student"]["school_id"])
    selected_dependent_id = discovered["student"].get("dependent_id")
    if selected_dependent_id is not None:
        selected_dependent_id = int(selected_dependent_id)

    code = _issue_tokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        redirect_uri=redirect_uri,
        client_id=effective_client_id,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    logger.info(
        "OAuth login concluído para usuário=%s school_id=%s dependent_id=%s",
        resolved_username,
        selected_school_id,
        selected_dependent_id,
    )
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
    client_id, client_secret = _extract_client_credentials(request, body)

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

        if bundle.code_challenge:
            code_verifier = str(body.get("code_verifier", "")).strip()
            if not code_verifier or not _verify_pkce(
                code_verifier,
                bundle.code_challenge,
                bundle.code_challenge_method or "S256",
            ):
                raise HTTPException(status_code=400, detail="code_verifier inválido.")

        refresh_key = secrets.token_urlsafe(32) if bundle.refresh_token else None
        if refresh_key and bundle.refresh_token:
            _store_refresh_bundle(refresh_key, bundle)

        return JSONResponse({
            "access_token": _session_access_token(bundle),
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
            school_id=bundle.school_id,
            dependent_id=bundle.dependent_id,
        )
        new_refresh_key = secrets.token_urlsafe(32)
        _refresh_tokens.pop(refresh_key, None)
        _store_refresh_bundle(new_refresh_key, new_bundle)

        return JSONResponse({
            "access_token": _session_access_token(new_bundle),
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
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid", "profile", "email"],
        "service_documentation": f"{base}/docs",
    }
