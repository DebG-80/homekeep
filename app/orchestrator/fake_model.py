"""A scripted Strands model for tests and `make run` (MODEL_PROVIDER=fake).

It emits Converse-shaped stream events, so the real Strands agent loop, the real MCP client and
the real tools run; only the language model is replaced. A script is a list of steps for one turn:
`call(tool, **input)` asks for a tool, `say(text)` ends the turn.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any

from strands.models.model import Model


@dataclass(frozen=True)
class Call:
    tool: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Wait:
    seconds: float


Step = Call | Say | Wait


def wait(seconds: float) -> Wait:
    """A slow model: sleep, then continue with the next step (budget tests)."""
    return Wait(seconds)


def call(tool: str, **tool_input: Any) -> Call:
    return Call(tool, tool_input)


def say(text: str) -> Say:
    return Say(text)


def _envelope(block: dict[str, Any]) -> Any:
    for content in block.get("content", []):
        if "json" in content:
            return content["json"]
        if "text" in content:
            try:
                return json.loads(content["text"])
            except json.JSONDecodeError:
                return {"text": content["text"]}
    return None


class ScriptedModel(Model):
    def __init__(self, script: Iterable[Step]) -> None:
        self._script: deque[Step] = deque(script)
        self.tools_offered: list[str] = []
        self.system_prompt: str | None = None  # the last one received, for tests
        self.observed: list[tuple[str, Any]] = []  # (tool name, envelope) as the model saw them
        self._names: dict[str, str] = {}
        self._counter = 0

    # --- Model interface ------------------------------------------------------------------

    def update_config(self, **model_config: Any) -> None:
        return None

    def get_config(self) -> dict[str, Any]:
        return {"model_id": "scripted"}

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        raise NotImplementedError("the scripted model has no structured output")
        yield  # pragma: no cover

    async def stream(
        self,
        messages: Any,
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        self.tools_offered = [spec["name"] for spec in (tool_specs or [])]
        self.system_prompt = system_prompt
        self._observe(messages)
        step = self._script.popleft() if self._script else Say("")
        while isinstance(step, Wait):
            await asyncio.sleep(step.seconds)
            step = self._script.popleft() if self._script else Say("")
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(step, Call):
            self._counter += 1
            tool_use_id = f"scripted-{self._counter}"
            self._names[tool_use_id] = step.tool
            yield {
                "contentBlockStart": {
                    "start": {"toolUse": {"toolUseId": tool_use_id, "name": step.tool}}
                }
            }
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(step.input)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": step.text}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}

    # --- test helpers ---------------------------------------------------------------------

    def _observe(self, messages: Any) -> None:
        seen = {tool_use_id for tool_use_id, _ in getattr(self, "_seen_ids", [])}
        self._seen_ids: list[tuple[str, Any]] = getattr(self, "_seen_ids", [])
        for message in messages:
            for content in message.get("content", []):
                block = content.get("toolResult")
                if block and block["toolUseId"] in self._names and block["toolUseId"] not in seen:
                    seen.add(block["toolUseId"])
                    self._seen_ids.append((block["toolUseId"], None))
                    self.observed.append((self._names[block["toolUseId"]], _envelope(block)))

    def results(self, tool: str) -> list[Any]:
        """Envelopes this model received from `tool`, in order."""
        return [envelope for name, envelope in self.observed if name == tool]


@dataclass
class TurnScripts:
    """A model factory for the orchestrator: each turn gets a fresh model with the next queued
    script, and every model is kept for inspection."""

    pending: deque[list[Step]] = field(default_factory=deque)
    models: list[ScriptedModel] = field(default_factory=list)

    def queue(self, steps: list[Step]) -> None:
        self.pending.append(steps)

    def __call__(self) -> ScriptedModel:
        model = ScriptedModel(self.pending.popleft() if self.pending else [Say("")])
        self.models.append(model)
        return model


def default_local_model() -> ScriptedModel:
    """`make run` with MODEL_PROVIDER=fake: look at the household, then reply briefly."""
    return ScriptedModel(
        [
            call("get_context"),
            say("This is the local test model. Your household context is loaded."),
        ]
    )


@dataclass
class LocalScripts:
    """`make run` with the fake model: turns queued through `POST /local/fake-model/script` (plan
    G4-7), so E2E tests can drive a whole journey. With nothing queued, the default local model
    answers. Mounted only when ENV=local and MODEL_PROVIDER=fake; never on AWS."""

    pending: deque[list[Step]] = field(default_factory=deque)

    def queue(self, turns: list[list[Step]]) -> None:
        self.pending.extend(turns)

    def __call__(self) -> ScriptedModel:
        return ScriptedModel(self.pending.popleft()) if self.pending else default_local_model()
