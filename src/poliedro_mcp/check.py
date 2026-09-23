"""Checagem local de ChatGPT (OpenAPI/OAuth) e Claude (MCP). Sem rede do P+.

    python -m poliedro_mcp.check
"""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("OAUTH_CLIENT_SECRET", "check-secret")
os.environ.setdefault("API_BASE_URL", "https://poliedro-api.iden.is")

from fastapi.testclient import TestClient

from poliedro_mcp.api import app
from poliedro_mcp.api_base import api_base_url
from poliedro_mcp.mcp_oauth_tokens import mint_pending_token, mint_session_access_token, parse_session_context
from poliedro_mcp.mcp_tools import create_local_server
from poliedro_mcp.oauth_proxy import _verify_pkce
from poliedro_mcp.profile_discovery import ProfileChoiceRequired

API_PATHS = {
    "/api/v1/assessments/simulation",
    "/api/v1/assessments/simulation/list",
    "/api/v1/assessments/simulation/{assessment_id}/performance",
    "/api/v1/calendar/month",
    "/api/v1/calendar/next",
    "/api/v1/calendar/week",
    "/api/v1/calendar/year",
    "/api/v1/grades",
    "/api/v1/health",
    "/api/v1/messages",
    "/api/v1/messages/unread",
    "/api/v1/messages/{announcement_id}",
}

REMOTE_PROPS = {
    "poliedro_health_check": {"school_id", "dependent_id"},
    "get_grades": {"school_id", "dependent_id"},
    "get_simulation_grades": {"school_year", "school_id", "dependent_id"},
    "list_simulation_assessments": {"school_year", "school_id", "dependent_id"},
    "get_simulation_performance": {"assessment_id", "school_id", "dependent_id"},
    "get_unread_messages": {"limit", "school_id", "dependent_id"},
    "get_messages": {"status", "limit", "page", "school_id", "dependent_id"},
    "get_message_detail": {"announcement_id", "school_id", "dependent_id"},
    "get_next_events": {"school_id", "dependent_id"},
    "get_week_events": {"date", "school_id", "dependent_id"},
    "get_month_events": {"date", "school_id", "dependent_id"},
    "get_year_events": {"date", "school_id", "dependent_id"},
}
REQUIRED = {
    "get_simulation_performance": ["assessment_id"],
    "get_message_detail": ["announcement_id"],
}


def _props(mcp) -> dict[str, set[str]]:
    return {
        tool.name: set((tool.parameters.get("properties") or {}))
        for tool in mcp._tool_manager.list_tools()
    }


def _required(mcp) -> dict[str, list[str] | None]:
    return {
        tool.name: tool.parameters.get("required")
        for tool in mcp._tool_manager.list_tools()
    }


def check_tokens() -> None:
    ctx = parse_session_context(
        mint_session_access_token("jwt-pmais", expires_in=60, school_id=3, dependent_id=9)
    )
    assert ctx is not None and ctx.access_token == "jwt-pmais"
    assert ctx.school_id == 3 and ctx.dependent_id == 9

    verifier = "pkce-verifier"
    challenge = hashlib.sha256(verifier.encode()).digest()
    import base64

    encoded = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode()
    assert _verify_pkce(verifier, encoded, "S256")
    assert not _verify_pkce("other", encoded, "S256")


def check_tools() -> None:
    from poliedro_mcp.mcp_remote import create_mcp_server

    remote_props = _props(create_mcp_server())
    local_props = _props(create_local_server())
    assert remote_props == REMOTE_PROPS, remote_props
    assert local_props == {name: props | {"poliedro_token"} for name, props in REMOTE_PROPS.items()}
    remote = create_mcp_server()
    remote_required = _required(remote)
    for tool in remote._tool_manager.list_tools():
        assert remote_required[tool.name] == REQUIRED.get(tool.name)
        ann = tool.annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is False
        assert ann.destructiveHint is False


def check_http() -> None:
    base = api_base_url()
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        chatgpt = client.get("/.well-known/oauth-authorization-server").json()
        assert chatgpt["authorization_endpoint"].endswith("/oauth/authorize")
        assert chatgpt["token_endpoint"].endswith("/oauth/token")
        assert "S256" in chatgpt["code_challenge_methods_supported"]

        mcp = client.get("/.well-known/oauth-authorization-server/mcp").json()
        assert mcp["issuer"] == f"{base}/mcp"
        assert mcp["registration_endpoint"] == f"{base}/mcp/register"
        assert mcp["authorization_endpoint"] == f"{base}/mcp/authorize"
        assert "none" in mcp["token_endpoint_auth_methods_supported"]

        protected = client.get("/.well-known/oauth-protected-resource/mcp").json()
        assert protected["resource"] == f"{base}/mcp"
        assert protected["authorization_servers"] == [f"{base}/mcp"]

        schema = client.get("/openapi.json").json()
        assert set(schema["paths"]) == API_PATHS
        assert schema["components"]["securitySchemes"]["OAuth2"]["flows"]["authorizationCode"]
        grades = schema["paths"]["/api/v1/grades"]["get"]
        assert [p["name"] for p in grades["parameters"]] == ["school_id", "dependent_id"]
        assert grades["security"] == [{"OAuth2": ["openid", "profile", "email"]}]

        login = client.get(
            "/oauth/authorize",
            params={
                "redirect_uri": "https://chatgpt.com/aip/g-test/oauth/callback",
                "state": "abc",
                "client_id": "poliedro-gpt",
            },
        )
        assert login.status_code == 200 and "Poliedro" in login.text
        assert client.get("/mcp/login").status_code == 422

        bad = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "x",
                "redirect_uri": "https://chatgpt.com/aip/x",
                "client_id": "poliedro-gpt",
                "client_secret": "nope",
            },
        )
        assert bad.status_code == 401

        import poliedro_mcp.oauth_proxy as oauth

        calls = {"login": 0}

        def fake_login(base_url: str, username: str, password: str) -> dict:
            calls["login"] += 1
            return {"access_token": "atk", "refresh_token": "rtk", "expires_in": 99}

        def fake_discover(base_url: str, token: str, **kwargs):
            if kwargs.get("school_id") is None:
                raise ProfileChoiceRequired(
                    "escola",
                    [{"school_id": 7, "name": "Escola", "role_id": 2}],
                )
            return {"student": {"school_id": kwargs["school_id"], "dependent_id": 4}}

        oauth.login_with_password = fake_login
        oauth.discover_profile_config = fake_discover

        redirect = "https://chatgpt.com/aip/g-test/oauth/callback"
        form = {
            "client_id": "poliedro-gpt",
            "redirect_uri": redirect,
            "state": "st",
            "username": "aluno",
            "password": "secret",
        }
        choice = client.post("/oauth/authorize", data=form)
        assert choice.status_code == 409 and "value='7'" in choice.text

        ok = client.post("/oauth/authorize", data={**form, "school_id": "7"}, follow_redirects=False)
        assert ok.status_code == 302 and ok.headers["location"].startswith(redirect)
        assert "code=" in ok.headers["location"]

        pending = mint_pending_token(
            {
                "client_id": "claude",
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            },
            {
                "state": "st",
                "scopes": ["openid"],
                "code_challenge": "abc",
                "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
                "redirect_uri_provided_explicitly": True,
                "resource": None,
            },
        )
        mcp = client.post(
            "/mcp/login",
            data={"pending": pending, "username": "aluno", "password": "secret", "school_id": "7"},
            follow_redirects=False,
        )
        assert mcp.status_code == 302, mcp.text
        assert mcp.headers["location"].startswith("https://claude.ai/api/mcp/auth_callback")
        assert calls["login"] == 3


def main() -> None:
    check_tokens()
    check_tools()
    check_http()
    print("ok")


if __name__ == "__main__":
    main()
