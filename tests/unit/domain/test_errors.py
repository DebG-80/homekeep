from __future__ import annotations

import re

from app.domain.errors import CUSTOMER_MESSAGES, REASON_MESSAGES, DomainError, ErrorCode


def _spoken_rules(text: str) -> None:
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
    assert len(sentences) <= 2, text
    assert text.count("?") <= 1, text
    assert not re.search(r"\d|https?://|_", text), text
    assert "free" not in text.casefold(), text
    if "technician" in text.casefold():
        assert "demo" in text.casefold(), text  # never implies a real visit (invariant 3)


def test_customer_messages_follow_elder_voice_rules() -> None:
    for text in [*CUSTOMER_MESSAGES.values(), *REASON_MESSAGES.values()]:
        _spoken_rules(text)
    assert set(CUSTOMER_MESSAGES) == set(ErrorCode)
    # Nothing was misheard in these cases, so they must not ask the elder to rephrase.
    for reason in (
        "DUPLICATE_NICKNAME",
        "NOT_FOUND",
        "UNDEFINED_TRANSITION",
        "NOT_AN_ACTIVE_ISSUE",
        "NO_INTAKE_FOR_CATEGORY",
        "TURN_ID_REQUIRED",
    ):
        message = DomainError(ErrorCode.INVALID_INPUT, reason).message
        assert "another way" not in message, reason
