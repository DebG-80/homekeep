from __future__ import annotations

from datetime import UTC, datetime

from app.channel.pipeline import local_prompt_time
from app.orchestrator.prompt import build_system_prompt


def test_inv10_prompt_uses_household_local_date_and_time() -> None:
    # 20:00 UTC is 01:30 the next day in Asia/Kolkata: date and time must agree.
    local_date, local_time = local_prompt_time(datetime(2026, 10, 20, 20, 0, tzinfo=UTC))
    assert (local_date, local_time) == ("2026-10-21", "01:30")
    assert "2026-10-21 01:30 (Asia/Kolkata)" in build_system_prompt(local_date, local_time)


def test_prompt_routes_consent_required_to_prepare_action_and_answers_greetings() -> None:
    # Nova 2 Lite on AWS (23 Oct) answered CONSENT_REQUIRED by asking for "yes" itself, so no
    # consent action was pending and every "yes" went back to the model (invariant 2 held, but the
    # user was stuck). The prompt must send that error straight to prepare_action.
    prompt = build_system_prompt("2026-10-23", "10:00")
    assert "If a tool answers CONSENT_REQUIRED, call prepare_action with CONSENT_STORAGE" in prompt
    assert "Never ask for a yes yourself" in prompt
    # A bare greeting gets a short welcome that says what HomeKeep helps with, not a re-ask.
    assert 'If the user only greets you ("hi", "hello", "namaste"' in prompt
