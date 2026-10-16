from __future__ import annotations

import re

from app.catalog.loader import load_catalog

FORBIDDEN = (
    "climb",
    "ladder",
    "stool",
    "open the",
    "remove",
    "cover",
    "panel",
    "refrigerant",
    "gas",
    "wiring",
    "wire",
    "screw",
    "capacitor",
    "fuse",
    "breaker",
    "mcb",
    "unplug and plug",
)


def _spoken_rules(text: str) -> None:
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
    assert len(sentences) <= 2, text
    assert text.count("?") <= 1, text
    assert not re.search(r"https?://|FL-\d|\b[a-z]+-[a-z0-9-]+\b", text), (
        text
    )  # no links, codes, IDs
    assert "free" not in text.casefold(), text
    assert len(text) <= 200, text


def test_catalog_speech_and_hazard_text_follow_elder_voice_rules() -> None:
    catalog = load_catalog()
    for item in catalog.items:
        for step in item.all_steps():
            _spoken_rules(step.speech)
    for hazard in catalog.hazards:
        _spoken_rules(hazard.speech)
        # The lexicon applies to every appliance, so the advice must not name one.
        assert not re.search(r"\b(AC|fridge|TV)\b", hazard.speech), hazard.speech
        assert "emergency" not in hazard.speech.casefold() or "call" not in hazard.speech.casefold()
    for prompts in catalog.generic_prompts.prompts.values():
        for prompt in prompts:
            _spoken_rules(prompt)
    for text in catalog.generic_prompts.scope_limit.values():
        _spoken_rules(text)
    assert {h.reason for h in catalog.hazards} >= {
        "BURNING_SMELL",
        "SMOKE",
        "FIRE",
        "SPARKS",
        "SHOCK",
        "REPEATED_TRIPPING",
        "GENERAL",
    }


def test_no_step_requires_forbidden_actions() -> None:
    catalog = load_catalog()
    statuses = {(i.item_id, i.version): i.status for i in catalog.items}
    assert statuses[("frostline-fl-18i", "v2")] == "PUBLISHED"
    assert statuses[("frostline-fl-18i", "v1")] == "WITHDRAWN"
    assert catalog.conflicting_keys("FL-24x") == {"E:E4"}
    for item in catalog.items:
        for step in item.all_steps():
            spoken = step.speech.casefold()
            assert not any(word in spoken for word in FORBIDDEN), (step.step_id, step.speech)
            assert step.locator, step.step_id  # every step cites its source
            assert step.evidence, step.step_id
