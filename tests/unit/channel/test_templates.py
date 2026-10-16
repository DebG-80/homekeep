from __future__ import annotations

import re

from app.channel import templates


def test_templates_follow_elder_voice_rules() -> None:
    texts = [
        *templates.COMMANDS.values(),
        templates.OUTPUT_GUARD_FALLBACK,
        templates.CYCLE_CAP,
        templates.DAILY_CAP,
        templates.TURN_ERROR,
        templates.GUIDANCE_FOLLOW_UP,
        templates.DEMO_DISCLOSURE,
    ]
    for text in texts:
        sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
        assert len(sentences) <= 2, text
        assert text.count("?") <= 1, text
        assert not re.search(r"\d|https?://|_", text), text
        assert "free" not in text.casefold(), text
        for claim in ("booked", "confirmed", "scheduled"):
            assert claim not in text.casefold(), text
        if "technician" in text.casefold():
            assert "demo" in text.casefold(), text
    assert "No real technician will visit" in templates.DEMO_DISCLOSURE
