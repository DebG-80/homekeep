"""Loads and validates `catalog_data/` once per process (TDD §4.7).

Lookup is by exact model and symptom key, never a search. Where several published sources cover
the same model and disagree on a key, that key is conflicting and gets no model-specific step.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalog_data"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Step(_Frozen):
    step_id: str
    speech: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    helper_only: bool = False


class CatalogItem(_Frozen):
    item_id: str
    version: str
    status: Literal["PUBLISHED", "WITHDRAWN", "DRAFT"]
    brand: str
    model: str
    category: str
    document_id: str
    source: str
    reviewer: str
    review_date: str
    withdrawal_reason: str | None = None
    steps: dict[str, tuple[Step, ...]] = Field(default_factory=dict)
    error_codes: dict[str, Step] = Field(default_factory=dict)

    def all_steps(self) -> list[Step]:
        return [s for steps in self.steps.values() for s in steps] + list(self.error_codes.values())

    def steps_for(self, key: str) -> tuple[Step, ...]:
        """`key` is a symptom category, or `E:<code>` for a displayed error code."""
        if key.startswith("E:"):
            step = self.error_codes.get(key[2:])
            return (step,) if step else ()
        return self.steps.get(key, ())


class Hazard(_Frozen):
    reason: str
    patterns: tuple[str, ...]
    speech: str = Field(min_length=1)


class GenericPrompts(_Frozen):
    prompts: dict[str, tuple[str, ...]]
    scope_limit: dict[str, str]


def model_key(model: str) -> str:
    """'FL-18i', 'fl 18i' and 'FL18I' are the same model."""
    return re.sub(r"[^a-z0-9]", "", model.casefold())


class Catalog(_Frozen):
    items: tuple[CatalogItem, ...]
    hazards: tuple[Hazard, ...]
    generic_prompts: GenericPrompts
    intake_version: str = ""

    def items_for_model(self, model: str) -> list[CatalogItem]:
        wanted = model_key(model)
        return [item for item in self.items if model_key(item.model) == wanted]

    def conflicting_keys(self, model: str, published_only: bool = True) -> set[str]:
        """Keys whose content differs between this model's sources."""
        items = [
            i for i in self.items_for_model(model) if not published_only or i.status == "PUBLISHED"
        ]
        keys = {k for i in items for k in i.steps} | {
            f"E:{c}" for i in items for c in i.error_codes
        }
        conflicts = set()
        for key in keys:
            variants = {tuple(s.model_dump_json() for s in i.steps_for(key)) for i in items}
            variants.discard(())
            if len(variants) > 1:
                conflicts.add(key)
        return conflicts


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def load_catalog(directory: Path = CATALOG_DIR) -> Catalog:
    items = tuple(
        CatalogItem.model_validate({k: v for k, v in _read(path).items() if k not in ("notes",)})
        for path in sorted((directory / "models").glob("*.json"))
    )
    step_ids: dict[str, str] = {}
    for item in items:
        for step in item.all_steps():
            content = step.model_dump_json()
            if step_ids.setdefault(step.step_id, content) != content:
                raise ValueError(f"step id {step.step_id} is reused for different content")
    hazards = tuple(Hazard.model_validate(h) for h in _read(directory / "hazards.json")["hazards"])
    generic = _read(directory / "generic_prompts.json")
    return Catalog(
        items=items,
        hazards=hazards,
        generic_prompts=GenericPrompts(
            prompts=generic["prompts"], scope_limit=generic["scope_limit"]
        ),
    )
