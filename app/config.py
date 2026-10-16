"""Runtime settings, loaded from environment variables.

The variable set is the contract in docs/infra-contract.md §9; `.env.example` lists the same
names, and tests/unit/test_env_contract.py keeps the three in step. Each field is the
lower-case form of its variable name.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

# Invariant 3: there is no live provider adapter in H. This is a code constant, never a setting.
SIMULATION_MODE: Final = "DEMO"

DEFAULT_MODEL_ID: Final = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

Env = Literal["local", "test", "demo"]

# Variables that must be set (non-empty) in each environment.
_REQUIRED_IN: Final[dict[str, tuple[str, ...]]] = {
    "local": ("dynamodb_endpoint_url",),
    "test": (
        "table_name",
        "bucket_name",
        "cognito_user_pool_id",
        "cognito_domain",
        "cognito_web_client_id",
        "cognito_mcp_client_id",
        "app_base_url",
        "allowed_origins",
    ),
}
_REQUIRED_IN["demo"] = _REQUIRED_IN["test"]


class ConfigError(ValueError):
    """The environment does not satisfy the infrastructure contract; the app must not start."""


_DEFAULT_PORTS: Final = {"http": 80, "https": 443}


def _origin(value: str, name: str) -> str:
    """Normalise a URL to the origin a browser sends (scheme://host[:port]), or raise ValueError.

    A trailing slash and a default port are dropped; a path, query, fragment or credentials are
    rejected, because a browser Origin header never carries them.
    """
    parts = urlsplit(value.strip())
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"{name} has an invalid port: {value!r}") from exc
    if parts.scheme not in _DEFAULT_PORTS or not parts.hostname:
        raise ValueError(f"{name} must be an http(s) origin like https://example.com: {value!r}")
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username:
        raise ValueError(f"{name} must be an origin with no path, query or credentials: {value!r}")
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    suffix = f":{port}" if port is not None and port != _DEFAULT_PORTS[parts.scheme] else ""
    return f"{parts.scheme}://{host}{suffix}"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    env: Env
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    port: int = Field(default=8000, ge=1, le=65535)
    aws_region: str = "us-east-1"
    table_name: str | None = None
    bucket_name: str | None = None
    dynamodb_endpoint_url: str | None = None
    cognito_user_pool_id: str | None = None
    cognito_domain: str | None = None
    cognito_web_client_id: str | None = None
    cognito_mcp_client_id: str | None = None
    model_id: str = DEFAULT_MODEL_ID
    bedrock_region: str | None = None
    model_provider: Literal["bedrock", "fake"] | None = None
    app_base_url: str | None = None
    allowed_origins: tuple[str, ...] = ()
    mcp_loopback_url: str = "http://127.0.0.1:8000/mcp"
    faults_enabled: bool = False
    clock_override: datetime | None = None
    daily_turn_cap: int = Field(default=300, gt=0)
    max_tool_cycles: int = Field(default=12, gt=0)
    turn_budget_seconds: int = Field(default=20, gt=0)
    bedrock_price_input_per_mtok_usd: float | None = Field(default=None, ge=0)
    bedrock_price_output_per_mtok_usd: float | None = Field(default=None, ge=0)

    @classmethod
    def env_var_names(cls) -> frozenset[str]:
        return frozenset(name.upper() for name in cls.model_fields)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Build settings from the environment, or raise ConfigError naming every problem."""
        environ = os.environ if environ is None else environ
        if "SIMULATION_MODE" in environ:
            raise ConfigError(
                "SIMULATION_MODE is not configurable: H has no live provider adapter "
                "(docs/infra-contract.md §10). Unset it."
            )
        values = {
            name.lower(): environ[name]
            for name in cls.env_var_names()
            if environ.get(name, "").strip() != ""
        }
        try:
            return cls.model_validate(values)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("allowed_origins")
    @classmethod
    def _normalise_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_origin(origin, "ALLOWED_ORIGINS") for origin in value))

    @field_validator("app_base_url", "cognito_domain")
    @classmethod
    def _normalise_base_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _origin(value, info.field_name.upper()) if value else value

    @field_validator("clock_override")
    @classmethod
    def _aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("CLOCK_OVERRIDE needs an explicit UTC offset, e.g. +00:00")
        return value.astimezone(UTC)

    @model_validator(mode="before")
    @classmethod
    def _env_dependent_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if data.get("env") == "local":
            data.setdefault("table_name", "homekeep-local")
            data.setdefault("app_base_url", "http://localhost:8000")
            data.setdefault("allowed_origins", data["app_base_url"])
            data.setdefault("model_provider", "fake")
        else:
            data.setdefault("model_provider", "bedrock")
        data.setdefault("bedrock_region", data.get("aws_region", "us-east-1"))
        data.setdefault("mcp_loopback_url", f"http://127.0.0.1:{data.get('port', 8000)}/mcp")
        return data

    @model_validator(mode="after")
    def _env_rules(self) -> Self:
        problems = [
            f"{name.upper()} is required when ENV={self.env}"
            for name in _REQUIRED_IN[self.env]
            if not getattr(self, name)
        ]
        if self.env != "local" and self.dynamodb_endpoint_url:
            problems.append("DYNAMODB_ENDPOINT_URL is allowed only when ENV=local")
        if self.env == "demo" and self.clock_override is not None:
            # P1-3: allowed in local and test (clock-dependent E2E); never in the judges' demo.
            problems.append("CLOCK_OVERRIDE is not allowed when ENV=demo")
        if self.env == "demo" and self.model_provider == "fake":
            problems.append("MODEL_PROVIDER=fake is allowed only when ENV is local or test")
        if (
            self.env == "demo"
            and self.app_base_url
            and not self.app_base_url.startswith("https://")
        ):
            problems.append("APP_BASE_URL must use https when ENV=demo")
        if self.env == "demo" and any(not o.startswith("https://") for o in self.allowed_origins):
            problems.append("ALLOWED_ORIGINS must all use https when ENV=demo")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def cognito_issuer(self) -> str | None:
        if not self.cognito_user_pool_id:
            return None
        return f"https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}"

    @property
    def cognito_jwks_url(self) -> str | None:
        issuer = self.cognito_issuer
        return f"{issuer}/.well-known/jwks.json" if issuer else None
