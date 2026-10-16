"""One conversation turn with the Strands agent (TDD §4.4).

A fresh MCP client is built per turn so its headers carry this turn's token, turn ID, session ID
and correlation ID. The agent sees only CUSTOMER_TOOLS (invariant 2). A hook enforces the
tool-cycle cap and the turn's wall-clock budget, and records every tool result so the channel can
speak approved wording instead of the model's (TDD §4.2 T8).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from strands import Agent
from strands.hooks import (
    AfterToolCallEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)
from strands.models.model import Model
from strands.tools.mcp import MCPClient

from app.config import Settings
from app.mcp_server.names import CUSTOMER_TOOLS
from app.orchestrator.fake_model import default_local_model

ModelFactory = Callable[[], Model]


def agent_tool_filters() -> dict[str, list[str]]:
    return {"allowed": list(CUSTOMER_TOOLS)}


def build_model(settings: Settings) -> Model:
    if settings.model_provider == "fake":
        return default_local_model()
    from botocore.config import Config
    from strands.models.bedrock import BedrockModel

    # Bounded so one slow call cannot outlast the turn (botocore defaults: 60 s and 4 retries).
    client_config = Config(
        connect_timeout=3,
        read_timeout=settings.turn_budget_seconds,
        retries={"total_max_attempts": 2, "mode": "standard"},  # one try plus one retry
    )
    return BedrockModel(
        model_id=settings.model_id,
        region_name=settings.bedrock_region,
        boto_client_config=client_config,
        temperature=0.2,
        max_tokens=350,
    )


@dataclass(frozen=True)
class ToolCall:
    name: str
    input: dict[str, Any]
    envelope: dict[str, Any] | None


@dataclass
class TurnOutcome:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop: str = "END"  # END, CYCLE_CAP or BUDGET


def _envelope(result: Any) -> dict[str, Any] | None:
    for content in (result or {}).get("content", []):
        if "json" in content and isinstance(content["json"], dict):
            return content["json"]
        if "text" in content:
            try:
                parsed = json.loads(content["text"])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


class _TurnGuard(HookProvider):
    def __init__(self, max_cycles: int, budget_seconds: float) -> None:
        self.max_cycles = max_cycles
        self.deadline = time.monotonic() + budget_seconds
        self.cycles = 0
        self.stop = "END"
        self.calls: list[ToolCall] = []

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before_tool)
        registry.add_callback(AfterToolCallEvent, self._after_tool)
        registry.add_callback(BeforeModelCallEvent, self._before_model)

    def _before_tool(self, event: BeforeToolCallEvent) -> None:
        self.cycles += 1
        if self.cycles > self.max_cycles:
            self.stop = "CYCLE_CAP"
            event.cancel_tool = "tool-cycle cap reached"

    def _after_tool(self, event: AfterToolCallEvent) -> None:
        if event.cancel_message:
            return
        self.calls.append(
            ToolCall(
                event.tool_use["name"],
                dict(event.tool_use.get("input") or {}),
                _envelope(event.result),
            )
        )

    def _before_model(self, event: BeforeModelCallEvent) -> None:
        if self.stop == "END" and time.monotonic() > self.deadline:
            self.stop = "BUDGET"
        if self.stop != "END":
            event.cancel = self.stop


def run_turn(
    *,
    settings: Settings,
    model_factory: ModelFactory,
    token: str,
    turn_id: str,
    session_id: str,
    correlation_id: str,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> TurnOutcome:
    """Synchronous: the channel runs it in a worker thread so the event loop stays free to serve
    the loopback MCP requests this turn makes (one Uvicorn worker)."""
    client = MCPClient(
        url=settings.mcp_loopback_url,
        headers={
            "Authorization": f"Bearer {token}",
            "X-HK-Turn-Id": turn_id,
            "X-HK-Session-Id": session_id,
            "X-Correlation-Id": correlation_id,
        },
        tool_filters=agent_tool_filters(),  # type: ignore[arg-type]
        startup_timeout=10,
    )
    guard = _TurnGuard(settings.max_tool_cycles, settings.turn_budget_seconds)
    with client:
        tools = client.list_tools_sync()  # already narrowed to CUSTOMER_TOOLS by tool_filters
        agent = Agent(
            model=model_factory(),
            tools=tools,
            system_prompt=system_prompt,
            messages=history,
            callback_handler=None,
            hooks=[guard],
        )
        result = agent(user_text)
    text = "" if guard.stop != "END" else str(result).strip()
    return TurnOutcome(text=text, tool_calls=guard.calls, stop=guard.stop)
