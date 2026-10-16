"""Hazard lexicon matching (TDD §4.3): case- and inflection-insensitive, deterministic."""

from __future__ import annotations

import re
from functools import cache

from app.catalog.loader import Hazard, load_catalog

GENERAL = "GENERAL"


@cache
def _compiled() -> tuple[tuple[Hazard, tuple[re.Pattern[str], ...]], ...]:
    return tuple(
        (h, tuple(re.compile(rf"\b{p}\b", re.IGNORECASE) for p in h.patterns))
        for h in load_catalog().hazards
    )


def match_hazard(text: str) -> Hazard | None:
    """The first lexicon hazard named in `text`, or None."""
    for hazard, patterns in _compiled():
        if any(p.search(text) for p in patterns):
            return hazard
    return None


def hazard_for(reason: str) -> Hazard:
    return next(h for h, _ in _compiled() if h.reason == reason)


def classify(text: str) -> Hazard:
    """For a reported warning sign: the matching hazard, else the approved GENERAL escalation."""
    return match_hazard(text) or hazard_for(GENERAL)
