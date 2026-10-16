from __future__ import annotations

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's shell (or CI) environment out of every test."""
    for name in (*Settings.env_var_names(), "SIMULATION_MODE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def demo_env() -> dict[str, str]:
    """A complete ENV=demo environment made of placeholders only (invariant 9)."""
    return {
        "ENV": "demo",
        "TABLE_NAME": "homekeep-demo",
        "BUCKET_NAME": "homekeep-demo-docs-placeholder",
        "COGNITO_USER_POOL_ID": "us-east-1_placeholder",
        "COGNITO_DOMAIN": "https://placeholder.auth.us-east-1.amazoncognito.com",
        "COGNITO_WEB_CLIENT_ID": "placeholder-web-client",
        "COGNITO_MCP_CLIENT_ID": "placeholder-mcp-client",
        "APP_BASE_URL": "https://homekeep.example.com",
        "ALLOWED_ORIGINS": "https://homekeep.example.com",
    }
