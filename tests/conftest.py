from __future__ import annotations

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from app.config import Settings
from app.security.local_issuer import LocalIssuer
from app.store.schema import ensure_table
from app.store.table import Table

TEST_REGION = "us-east-1"
TEST_TABLE = "homekeep-unit"


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


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dummy credentials so boto3 never reaches a real account, even by accident."""
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": TEST_REGION,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def table(aws_credentials: None) -> Iterator[Table]:
    """An empty table built from the contract definition, inside moto."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name=TEST_REGION)
        ensure_table(client, TEST_TABLE)
        yield Table(client, TEST_TABLE)


@pytest.fixture(scope="session")
def issuer() -> LocalIssuer:
    """One RSA key for the whole run; generating keys per test is slow."""
    return LocalIssuer()
