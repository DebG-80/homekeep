from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import ConfigError, Settings
from app.main import create_app


def test_inv10_clock_override_rejected_in_demo_env(demo_env: dict[str, str]) -> None:
    # P1-3 (Slice 1): allowed in local and test; the judges' demo never runs on a fixed clock.
    with pytest.raises(ConfigError, match="CLOCK_OVERRIDE is not allowed when ENV=demo"):
        Settings.from_env({**demo_env, "CLOCK_OVERRIDE": "2026-10-20T18:29:00+00:00"})


def test_inv10_clock_override_accepted_in_local_env() -> None:
    # P1-3: clock-dependent E2E (AT-13 expiry, AT-34 rollover) runs against `make run`.
    settings = Settings.from_env(
        {
            "ENV": "local",
            "DYNAMODB_ENDPOINT_URL": "http://localhost:8001",
            "CLOCK_OVERRIDE": "2026-10-20T18:29:00+00:00",
        }
    )
    assert settings.clock_override == datetime(2026, 10, 20, 18, 29, tzinfo=UTC)


def test_inv10_clock_override_rejected_at_app_startup(
    monkeypatch: pytest.MonkeyPatch, demo_env: dict[str, str]
) -> None:
    # G-3: fail fast. The app refuses to start rather than silently ignoring the override.
    for name, value in {**demo_env, "CLOCK_OVERRIDE": "2026-10-20T18:29:00+00:00"}.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError), TestClient(create_app()):
        pass


def test_inv10_clock_override_accepted_in_test_env(demo_env: dict[str, str]) -> None:
    settings = Settings.from_env(
        {**demo_env, "ENV": "test", "CLOCK_OVERRIDE": "2026-10-21T00:00:00+05:30"}
    )
    # Stored in UTC: local midnight in Asia/Kolkata is 18:30 UTC the day before.
    assert settings.clock_override == datetime(2026, 10, 20, 18, 30, tzinfo=UTC)


def test_inv10_clock_override_must_carry_an_offset(demo_env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="explicit UTC offset"):
        Settings.from_env({**demo_env, "ENV": "test", "CLOCK_OVERRIDE": "2026-10-21T00:00:00"})


def test_dynamodb_endpoint_only_in_local_env(demo_env: dict[str, str]) -> None:
    endpoint = "http://localhost:8001"
    for env in ("test", "demo"):
        with pytest.raises(ConfigError, match="DYNAMODB_ENDPOINT_URL is allowed only"):
            Settings.from_env({**demo_env, "ENV": env, "DYNAMODB_ENDPOINT_URL": endpoint})

    local = Settings.from_env({"ENV": "local", "DYNAMODB_ENDPOINT_URL": endpoint})
    assert local.dynamodb_endpoint_url == endpoint
    # Local without an endpoint would silently talk to real DynamoDB, so it is required there.
    with pytest.raises(ConfigError, match="DYNAMODB_ENDPOINT_URL is required when ENV=local"):
        Settings.from_env({"ENV": "local"})


def test_fake_model_rejected_in_demo_env(demo_env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="MODEL_PROVIDER=fake is allowed only"):
        Settings.from_env({**demo_env, "MODEL_PROVIDER": "fake"})

    assert Settings.from_env(demo_env).model_provider == "bedrock"
    assert Settings.from_env({**demo_env, "ENV": "test", "MODEL_PROVIDER": "fake"}).model_provider
    local = Settings.from_env({"ENV": "local", "DYNAMODB_ENDPOINT_URL": "http://localhost:8001"})
    assert local.model_provider == "fake"


def test_nfr10_demo_env_requires_table_cognito_and_origin_vars(
    demo_env: dict[str, str],
) -> None:
    settings = Settings.from_env(demo_env)
    assert settings.cognito_issuer == (
        "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_placeholder"
    )
    assert settings.cognito_jwks_url == f"{settings.cognito_issuer}/.well-known/jwks.json"
    assert settings.allowed_origins == ("https://homekeep.example.com",)
    assert settings.model_id == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert settings.bedrock_region == "us-east-1"

    for name in (
        "TABLE_NAME",
        "COGNITO_USER_POOL_ID",
        "COGNITO_DOMAIN",
        "COGNITO_WEB_CLIENT_ID",
        "COGNITO_MCP_CLIENT_ID",
        "APP_BASE_URL",
        "ALLOWED_ORIGINS",
    ):
        for missing in ({k: v for k, v in demo_env.items() if k != name}, {**demo_env, name: " "}):
            with pytest.raises(ConfigError, match=f"{name} is required when ENV=demo"):
                Settings.from_env(missing)

    # Documents are deferred (P1-1), so there is no bucket to configure (deb-inputs 1a).
    assert "BUCKET_NAME" not in Settings.env_var_names()
    assert Settings.from_env({**demo_env, "BUCKET_NAME": "anything"}).table_name == "homekeep-demo"

    with pytest.raises(ConfigError, match="APP_BASE_URL must use https"):
        Settings.from_env({**demo_env, "APP_BASE_URL": "http://homekeep.example.com"})
    with pytest.raises(ConfigError):
        Settings.from_env({**demo_env, "ENV": "production"})
    with pytest.raises(ConfigError):
        Settings.from_env({k: v for k, v in demo_env.items() if k != "ENV"})


def test_nfr10_origins_normalised_to_what_browsers_send(demo_env: dict[str, str]) -> None:
    # A browser Origin header has no trailing slash, path or default port; a pasted address-bar
    # URL must still match it, or every API and /mcp request would be rejected.
    settings = Settings.from_env(
        {
            **demo_env,
            "APP_BASE_URL": "https://Homekeep.Example.com/",
            "ALLOWED_ORIGINS": "https://homekeep.example.com:443/, https://other.example.com:8443",
            "COGNITO_DOMAIN": "https://placeholder.auth.us-east-1.amazoncognito.com/",
        }
    )
    assert settings.app_base_url == "https://homekeep.example.com"
    assert settings.allowed_origins == (
        "https://homekeep.example.com",
        "https://other.example.com:8443",
    )
    assert settings.cognito_domain == "https://placeholder.auth.us-east-1.amazoncognito.com"

    local = Settings.from_env(
        {
            "ENV": "local",
            "DYNAMODB_ENDPOINT_URL": "http://localhost:8001",
            "APP_BASE_URL": "http://localhost:9000/",
        }
    )
    assert local.allowed_origins == ("http://localhost:9000",)


def test_nfr10_origins_with_paths_or_plain_http_rejected(demo_env: dict[str, str]) -> None:
    for name, value, message in (
        ("APP_BASE_URL", "https://homekeep.example.com/app/", "no path"),
        ("APP_BASE_URL", "https://homekeep.example.com/?x=1", "no path, query"),
        ("APP_BASE_URL", "homekeep.example.com", "http\\(s\\) origin"),
        ("ALLOWED_ORIGINS", "https://homekeep.example.com/mcp", "no path"),
        ("ALLOWED_ORIGINS", "https://user@homekeep.example.com", "credentials"),
        ("ALLOWED_ORIGINS", "https://homekeep.example.com:99999", "invalid port"),
        (
            "ALLOWED_ORIGINS",
            "https://homekeep.example.com, http://homekeep.example.com",
            "must all use https",
        ),
    ):
        with pytest.raises(ConfigError, match=f"{name}.*{message}"):
            Settings.from_env({**demo_env, name: value})


def test_mcp_loopback_url_follows_port(demo_env: dict[str, str]) -> None:
    assert Settings.from_env(demo_env).mcp_loopback_url == "http://127.0.0.1:8000/mcp"
    assert (
        Settings.from_env({**demo_env, "PORT": "9000"}).mcp_loopback_url
        == "http://127.0.0.1:9000/mcp"
    )
    explicit = "http://127.0.0.1:7000/mcp"
    settings = Settings.from_env({**demo_env, "PORT": "9000", "MCP_LOOPBACK_URL": explicit})
    assert settings.mcp_loopback_url == explicit


def test_inv3_simulation_mode_is_not_an_env_setting(demo_env: dict[str, str]) -> None:
    assert config.SIMULATION_MODE == "DEMO"
    assert "SIMULATION_MODE" not in Settings.env_var_names()
    with pytest.raises(ConfigError, match="SIMULATION_MODE is not configurable"):
        Settings.from_env({**demo_env, "SIMULATION_MODE": "LIVE"})


def test_inv10_clock_override_must_be_an_iso_timestamp_with_offset() -> None:
    # A bare epoch number is ambiguous to a reader of the environment; ISO 8601 only.
    with pytest.raises(ConfigError, match="CLOCK_OVERRIDE"):
        Settings.from_env(
            {
                "ENV": "local",
                "DYNAMODB_ENDPOINT_URL": "http://localhost:8001",
                "CLOCK_OVERRIDE": "1792531740",
            }
        )
