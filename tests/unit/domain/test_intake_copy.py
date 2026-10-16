from __future__ import annotations

import re

from app.domain.observations import intake_definition

# elder-voice-copy: at most two sentences and one question; plain words; nothing unsafe.
FORBIDDEN = (
    "climb",
    "ladder",
    "open",
    "cover",
    "remove",
    "refrigerant",
    "wiring",
    "reset",
    "screw",
)


def test_intake_questions_follow_elder_voice_rules() -> None:
    intake = intake_definition("AC")
    assert intake is not None
    fields = [q["field"] for q in intake["questions"]]
    assert fields[:2] == ["onset", "airflow"]  # BRD §5.2 order: onset, then airflow
    assert len(fields) == len(set(fields))

    for question in intake["questions"]:
        text = question["question"]
        sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
        assert len(sentences) <= 2, text
        assert text.count("?") == 1, text
        assert not re.search(r"\d|https?://|_", text), text  # no codes, IDs or links
        assert not any(word in text.casefold() for word in FORBIDDEN), text
        assert len(text) <= 140, text
