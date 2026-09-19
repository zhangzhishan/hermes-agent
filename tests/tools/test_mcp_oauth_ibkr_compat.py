"""Local IBKR OAuth compatibility contract carried across Hermes upgrades."""

from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock

import pytest

pytest.importorskip("mcp.client.auth.oauth2")


def _interactive(monkeypatch):
    stdin = MagicMock()
    stdin.isatty.return_value = True
    monkeypatch.setattr("tools.mcp_oauth.sys.stdin", stdin)


def _provider(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _interactive(monkeypatch)
    from tools.mcp_oauth_manager import MCPOAuthManager, reset_manager_for_tests

    reset_manager_for_tests()
    return MCPOAuthManager().get_or_build_provider(
        "ibkr",
        "https://api.ibkr.com/v1/api/mcp-public",
        {"client_id": "configured-client", "redirect_port": 49199},
    )


def test_ibkr_defaults_pin_read_only_oauth_shape():
    from tools.mcp_oauth import apply_oauth_provider_defaults

    cfg = {}
    apply_oauth_provider_defaults(
        cfg,
        server_name="ibkr",
        server_url="https://api.ibkr.com/v1/api/mcp-public",
    )

    assert cfg["scope"] == "mcp.read"
    assert cfg["authorization_endpoint"] == "https://api.ibkr.com/oauth2/authorize"
    assert cfg["token_endpoint"] == "https://api.ibkr.com/oauth2/api/v1/token"
    assert cfg["issuer"] == "https://api.ibkr.com"
    assert cfg["pkce_verifier_bytes"] == 48
    assert cfg["include_scope_in_token_request"] is True
    assert "client_name" not in cfg


@pytest.mark.asyncio
async def test_ibkr_provider_uses_pinned_metadata_and_scope(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    await provider._initialize()

    assert str(provider.context.oauth_metadata.authorization_endpoint) == (
        "https://api.ibkr.com/oauth2/authorize"
    )
    assert str(provider.context.oauth_metadata.token_endpoint) == (
        "https://api.ibkr.com/oauth2/api/v1/token"
    )
    from mcp.shared.auth import OAuthMetadata

    # Simulate the SDK's 401 discovery replacing the configured metadata with
    # a different authorization server. The final authorization boundary must
    # restore the pinned operator/provider endpoints.
    provider.context.oauth_metadata = OAuthMetadata.model_validate(
        {
            "issuer": "https://discovered.example",
            "authorization_endpoint": "https://discovered.example/authorize",
            "token_endpoint": "https://discovered.example/token",
        }
    )
    provider.context.client_metadata.scope = "mcp.read mcp.write"

    captured = {}

    async def fake_grant():
        captured["scope"] = provider.context.client_metadata.scope
        captured["authorization_endpoint"] = str(
            provider.context.oauth_metadata.authorization_endpoint
        )
        return "code", "verifier"

    async def fake_exchange(code, verifier):
        return code, verifier

    monkeypatch.setattr(provider, "_perform_authorization_code_grant", fake_grant)
    monkeypatch.setattr(provider, "_exchange_token_authorization_code", fake_exchange)
    assert await provider._perform_authorization() == ("code", "verifier")
    assert captured["scope"] == "mcp.read"
    assert captured["authorization_endpoint"] == (
        "https://api.ibkr.com/oauth2/authorize"
    )


@pytest.mark.asyncio
async def test_ibkr_pkce_verifier_is_64_char_base64url(tmp_path, monkeypatch):
    from mcp.shared.auth import AuthorizationCodeResult

    provider = _provider(tmp_path, monkeypatch)
    await provider._initialize()
    captured = {}

    async def redirect(url):
        captured["url"] = url

    async def callback():
        state = parse_qs(urlsplit(captured["url"]).query)["state"][0]
        return AuthorizationCodeResult(code="code", state=state)

    provider.context.redirect_handler = redirect
    provider.context.callback_handler = callback
    _, verifier = await provider._perform_authorization_code_grant()

    assert len(verifier) == 64
    assert set(verifier) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )
    query = parse_qs(urlsplit(captured["url"]).query)
    assert len(query["code_challenge"][0]) == 43
    assert query["scope"] == ["mcp.read"]


@pytest.mark.asyncio
async def test_ibkr_token_exchange_repeats_scope_and_recomputes_length(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    await provider._initialize()
    request = await provider._exchange_token_authorization_code("code", "verifier")
    content = await request.aread()
    form = parse_qs(content.decode())

    assert form["scope"] == ["mcp.read"]
    assert form["code"] == ["code"]
    assert form["code_verifier"] == ["verifier"]
    assert int(request.headers["content-length"]) == len(content)


@pytest.mark.asyncio
async def test_scope_rewrite_preserves_confidential_client_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _interactive(monkeypatch)
    from tools.mcp_oauth_manager import MCPOAuthManager, reset_manager_for_tests

    reset_manager_for_tests()
    provider = MCPOAuthManager().get_or_build_provider(
        "confidential",
        "https://mcp.example/resource",
        {
            "client_id": "client",
            "client_secret": "secret",
            "scope": "read",
            "authorization_endpoint": "https://idp.example/authorize",
            "token_endpoint": "https://idp.example/token",
            "token_endpoint_auth_method": "client_secret_basic",
            "include_scope_in_token_request": True,
            "redirect_port": 49200,
        },
    )
    await provider._initialize()
    request = await provider._exchange_token_authorization_code("code", "verifier")
    content = await request.aread()
    form = parse_qs(content.decode())

    assert request.headers["authorization"].startswith("Basic ")
    assert form["scope"] == ["read"]
    assert int(request.headers["content-length"]) == len(content)
