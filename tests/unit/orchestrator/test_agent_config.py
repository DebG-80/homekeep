from __future__ import annotations

from strands.models.bedrock import BedrockModel

from app.config import Settings
from app.mcp_server.names import CUSTOMER_TOOLS, TRUSTED_TOOLS
from app.orchestrator.agent import agent_tool_filters, build_model
from app.orchestrator.fake_model import ScriptedModel


def test_g2_8_bedrock_model_built_from_settings_without_network(
    demo_env: dict[str, str], aws_credentials: None
) -> None:
    settings = Settings.from_env({**demo_env, "BEDROCK_REGION": "us-west-2"})
    model = build_model(settings)
    assert isinstance(model, BedrockModel)
    config = model.get_config()
    assert config["model_id"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert config["temperature"] == 0.2
    assert config["max_tokens"] == 350
    assert model.client.meta.region_name == "us-west-2"

    local = Settings.from_env({"ENV": "local", "DYNAMODB_ENDPOINT_URL": "http://localhost:8001"})
    assert isinstance(build_model(local), ScriptedModel)  # MODEL_PROVIDER defaults to fake locally


def test_inv2_agent_tool_filter_excludes_trusted_tools() -> None:
    filters = agent_tool_filters()
    assert filters == {"allowed": list(CUSTOMER_TOOLS)}
    assert not set(filters["allowed"]) & set(TRUSTED_TOOLS)


def test_nfr01_bedrock_client_timeouts_fit_the_turn_budget(
    demo_env: dict[str, str], aws_credentials: None
) -> None:
    model = build_model(Settings.from_env({**demo_env, "TURN_BUDGET_SECONDS": "20"}))
    config = model.client.meta.config
    assert config.connect_timeout <= 3
    assert config.read_timeout <= 20
    assert config.retries["total_max_attempts"] <= 2  # botocore's normalised key
