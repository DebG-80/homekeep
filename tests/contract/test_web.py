"""The browser client is served by the app itself (plan G4-1)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.security.local_issuer import LocalIssuer
from app.store.table import Table
from app.web import client_config
from scripts import seed
from tests.contract.live import LiveServer, serve


@pytest.fixture
def site(table: Table, issuer: LocalIssuer, tmp_path: Path) -> Iterator[LiveServer]:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        '<!doctype html><title>HomeKeep</title><script type="module" src="/assets/app.js">'
        "</script>",
        encoding="utf-8",
    )
    (tmp_path / "assets" / "app.js").write_text("console.log('hk')", encoding="utf-8")
    seed.seed_local(table)
    with serve(table, issuer, web_dist=tmp_path) as server:
        yield server


def test_index_and_assets_served_with_csp_and_config_has_no_secrets(site: LiveServer) -> None:
    index = httpx.get(f"{site.base_url}/", timeout=10)
    assert index.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
    csp = index.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp
    assert index.headers["x-content-type-options"] == "nosniff"
    asset = httpx.get(f"{site.base_url}/assets/app.js", timeout=10)
    assert (asset.status_code, asset.text) == (200, "console.log('hk')")
    assert httpx.get(f"{site.base_url}/assets/missing.js", timeout=10).status_code == 404
    # Cognito returns to the callback fixed in infra-contract §5.3: the same page, same policy.
    callback = httpx.get(f"{site.base_url}/auth/callback?code=x&state=y", timeout=10)
    assert callback.status_code == 200
    assert callback.text == index.text
    assert callback.headers["content-security-policy"] == csp
    # The MCP endpoint and its metadata are unaffected by the client at "/".
    metadata = httpx.get(f"{site.base_url}/.well-known/oauth-protected-resource", timeout=10)
    assert metadata.status_code == 200

    config = httpx.get(f"{site.base_url}/api/config", timeout=10).json()
    assert config == {"env": "local", "local_sign_in": True, "cognito": None}


def test_client_config_on_aws_names_only_public_cognito_settings(site: LiveServer) -> None:
    settings = site.settings.model_copy(
        update={
            "env": "test",
            "cognito_user_pool_id": "us-east-1_EXAMPLE",
            "cognito_domain": "https://homekeep-test.auth.us-east-1.amazoncognito.com",
            "cognito_web_client_id": "exampleclientid",
        }
    )
    config = client_config(settings, local_sign_in=False)
    assert config["local_sign_in"] is False
    assert config["cognito"] == {
        "authority": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EXAMPLE",
        "domain": "https://homekeep-test.auth.us-east-1.amazoncognito.com",
        "client_id": "exampleclientid",
        "redirect_uri": f"{settings.app_base_url}/auth/callback",  # infra-contract §5.3
        "post_logout_redirect_uri": f"{settings.app_base_url}/",
        "scope": "openid homekeep/api homekeep/mcp",
    }
