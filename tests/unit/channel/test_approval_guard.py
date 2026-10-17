from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.channel.approval_guard import Pending, accept_playback_end, decide

T0 = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
PENDING = Pending(
    pending_ref="ap-1", expires_at=T0 + timedelta(minutes=5), readback_completed_at=T0
)
READBACK = "Here is the booking to check. Shall I book it?"


def _voice(text: str, **overrides: object) -> str:
    kwargs: dict[str, object] = {
        "pending": PENDING,
        "channel": "voice",
        "client_state": "LISTENING",
        "speech_started_at": T0 + timedelta(seconds=2),
        "now": T0 + timedelta(seconds=3),
        "last_spoken": READBACK,
    }
    kwargs.update(overrides)
    return decide(text, **kwargs).kind  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "text",
    ["yes", "Yes please", "yes, book it", "confirm", "go ahead", "OK, go ahead.", "yes do it"],
)
def test_at13_whole_affirmative_utterances_approve(text: str) -> None:
    assert _voice(text) == "APPROVE"


@pytest.mark.parametrize(
    "text", ["yes but change the date", "I said yes yesterday", "maybe", "what time is it", "yes?"]
)
def test_at13_affirmatives_inside_other_speech_do_not_approve(text: str) -> None:
    assert _voice(text) == "NONE"


@pytest.mark.parametrize("text", ["no", "No thanks", "don't", "not now", "no, don't book it"])
def test_negatives_decline(text: str) -> None:
    assert _voice(text) == "DECLINE"


def test_at13_voice_timing_state_and_echo_rules() -> None:
    assert _voice("yes", pending=None) == "NONE"  # nothing pending
    assert _voice("yes", now=T0 + timedelta(minutes=6)) == "NONE"  # expired
    late = Pending(pending_ref="ap-1", expires_at=PENDING.expires_at, readback_completed_at=None)
    assert _voice("yes", pending=late) == "NONE"  # the read-back never finished playing
    assert (
        _voice("yes", speech_started_at=T0 - timedelta(seconds=1)) == "NONE"
    )  # said during playback
    assert _voice("yes", client_state="SPEAKING") == "NONE"  # background "yes" while HomeKeep spoke
    assert (
        _voice("shall I book it", last_spoken="Shall I book it?") == "NONE"
    )  # an echo of our own words


def test_text_channel_applies_rules_1_4_and_6_only() -> None:
    text = Pending(pending_ref="ap-1", expires_at=PENDING.expires_at, readback_completed_at=None)
    decision = decide(
        "yes",
        pending=text,
        channel="text",
        client_state=None,
        speech_started_at=None,
        now=T0,
        last_spoken=READBACK,
    )
    assert decision.kind == "APPROVE"
    assert (
        decide(
            "yes but later",
            pending=text,
            channel="text",
            client_state=None,
            speech_started_at=None,
            now=T0,
            last_spoken=READBACK,
        ).kind
        == "NONE"
    )


@pytest.mark.parametrize("text", ["yes call it off", "call it off", "yes change it", "yes move it"])
def test_n1_answers_to_cancel_and_change_readbacks_approve(text: str) -> None:
    assert _voice(text) == "APPROVE"


def test_i8_speech_start_in_the_future_is_refused() -> None:
    assert _voice("yes", speech_started_at=T0 + timedelta(minutes=2)) == "NONE"


def test_i8_playback_end_is_accepted_only_after_the_readback_and_while_not_speaking() -> None:
    prepared = T0 - timedelta(seconds=30)
    assert accept_playback_end(prepared, T0, "LISTENING", T0 + timedelta(seconds=1)) == T0
    assert accept_playback_end(prepared, T0, "SPEAKING", T0) is None  # still talking
    assert accept_playback_end(prepared, prepared - timedelta(seconds=1), None, T0) is None
    assert accept_playback_end(prepared, T0 + timedelta(minutes=1), None, T0) is None  # future
    assert accept_playback_end(None, T0, "LISTENING", T0) is None  # nothing was read back
