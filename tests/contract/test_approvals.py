from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.channel import templates
from app.domain.clock import FixedClock
from app.orchestrator.fake_model import TurnScripts, call, say
from app.security.local_issuer import LocalIssuer
from app.store import keys
from app.store.table import Table
from scripts import seed
from tests.contract.live import LiveServer, new_session, serve, spoken, turn

START = datetime(2026, 10, 16, 4, 30, tzinfo=UTC)  # 10:00 in Kolkata
SLOT = "2026-10-17#AM"


@pytest.fixture
def booking_server(table: Table, issuer: LocalIssuer) -> Any:
    seed.seed_local(table)

    @contextmanager
    def start() -> Iterator[tuple[LiveServer, TurnScripts, FixedClock]]:
        scripts, clock = TurnScripts(), FixedClock(START)
        with serve(table, issuer, scripts, clock=clock) as live:
            yield live, scripts, clock

    return start


def _items(live: LiveServer, prefix: str, household: str = "qa-a") -> list[dict[str, Any]]:
    return live.table.query(keys.household_pk(household), prefix)


def _prepared(live: LiveServer, scripts: TurnScripts) -> tuple[str, dict[str, Any]]:
    """Report a problem, draft a request (Household A's address is on file), hear the read-back."""
    session_id = new_session(live)
    scripts.queue(
        [
            call(
                "report_issue",
                appliance_id="qa-a-ac-bedroom",
                symptom_text="Not cooling",
                symptom_category="NOT_COOLING",
            ),
            say("Noted."),
        ]
    )
    turn(live, session_id, "My bedroom AC is not cooling")
    issue_id = next(
        i["issue_id"] for i in _items(live, keys.ISSUE_PREFIX) if i.get("kind") == "ISSUE"
    )
    scripts.queue([call("draft_service_request", issue_id=issue_id), say("Okay.")])
    turn(live, session_id, "Please send someone")
    request_id = next(
        i["request_id"] for i in _items(live, keys.REQUEST_PREFIX) if i.get("kind") == "SR"
    )
    scripts.queue(
        [
            call("list_slots", request_id=request_id),
            call("prepare_action", kind="SUBMIT", request_id=request_id, slot_id=SLOT),
            say("Shall I?"),
        ]
    )
    readback = turn(live, session_id, "Tomorrow morning please")
    return session_id, readback


def _voice_yes(clock: FixedClock, **overrides: Any) -> dict[str, Any]:
    finished = clock.now()
    fields = {
        "channel": "voice",
        "client_state": "LISTENING",
        "playback_ended_at": finished.isoformat(),
        "speech_started_at": (finished + timedelta(seconds=1)).isoformat(),
    }
    fields.update(overrides)
    return fields


def test_at13_silence_background_yes_playback_expired_and_corrected_date_cannot_submit(
    booking_server: Any,
) -> None:
    with booking_server() as (live, scripts, clock):
        session_id, readback = _prepared(live, scripts)
        assert readback["awaiting_approval"]["pending_ref"]
        assert spoken(readback).endswith("Shall I book it?")

        # Silence: no turn arrives, so nothing happens. A "yes" heard while HomeKeep was speaking:
        background = turn(live, session_id, "yes", **_voice_yes(clock, client_state="SPEAKING"))
        # A "yes" that began before the read-back finished playing:
        early = turn(
            live,
            session_id,
            "yes",
            **_voice_yes(clock, speech_started_at=(clock.now() - timedelta(seconds=5)).isoformat()),
        )
        for response in (background, early):
            assert response["handled_by"] != "APPROVAL"
        assert _items(live, keys.REQUEST_PREFIX)[0]["state"] == "DRAFT"

        # A corrected date: the model prepares again; the first read-back is superseded.
        scripts.queue(
            [
                call(
                    "prepare_action",
                    kind="SUBMIT",
                    request_id=readback_request(live),
                    slot_id="2026-10-18#AM",
                ),
                say("Okay."),
            ]
        )
        corrected = turn(live, session_id, "Saturday, no, Sunday morning")
        assert (
            corrected["awaiting_approval"]["pending_ref"]
            != readback["awaiting_approval"]["pending_ref"]
        )
        # An expired approval: five minutes pass.
        clock.advance(timedelta(minutes=6))
        expired = turn(live, session_id, "yes", **_voice_yes(clock))
    assert expired["handled_by"] == "APPROVAL"
    assert spoken(expired) == templates.APPROVAL_EXPIRED
    assert [a for a in _items(live, "SR#") if a.get("kind") == "APPOINTMENT"] == []
    assert _items(live, keys.REQUEST_PREFIX)[0]["state"] == "DRAFT"


def readback_request(live: LiveServer) -> str:
    return next(i["request_id"] for i in _items(live, keys.REQUEST_PREFIX) if i.get("kind") == "SR")


def test_at13_fresh_explicit_yes_books_once(booking_server: Any) -> None:
    with booking_server() as (live, scripts, clock):
        session_id, _ = _prepared(live, scripts)
        models_before = len(scripts.models)
        booked = turn(live, session_id, "Yes, book it", turn_id="turn-yes", **_voice_yes(clock))
        replay = turn(live, session_id, "Yes, book it", turn_id="turn-yes", **_voice_yes(clock))
        scripts.queue([say("Is there anything else?")])
        again = turn(live, session_id, "yes", **_voice_yes(clock))
    assert booked["handled_by"] == "APPROVAL"
    assert len(scripts.models) == models_before + 1  # the approval never went through the model
    text = spoken(booked).casefold()
    assert "demo booking is confirmed" in text
    assert "saturday, 17 october" in text
    assert "no real technician will visit" in text
    assert replay == booked
    assert again["handled_by"] != "APPROVAL"  # the approval was used once
    appointments = [a for a in _items(live, "SR#") if a.get("kind") == "APPOINTMENT"]
    assert len(appointments) == 1
    approval = _items(live, keys.APPROVAL_PREFIX)[-1]
    assert (approval["state"], approval["channel"]) == ("EXECUTED", "voice")


def test_g3_6_consent_by_voice_unlocks_persistence(booking_server: Any) -> None:
    with booking_server() as (live, scripts, _):
        session_id = new_session(live, "j1_owner")
        scripts.queue([call("prepare_action", kind="CONSENT_STORAGE"), say("May I?")])
        asked = turn(live, session_id, "Hello", identity="j1_owner")
        assert spoken(asked) == " ".join(
            templates.render_readback({"kind": "CONSENT_STORAGE", "purpose": "STORAGE"})
        )
        granted = turn(live, session_id, "yes", identity="j1_owner", channel="text")
        assert spoken(granted) == " ".join(
            templates.render_outcome({"outcome": "CONSENT_RECORDED"})
        )
        scripts.queue(
            [call("register_appliance", category="AC", nickname="Bedroom AC"), say("Saved.")]
        )
        turn(live, session_id, "I have an AC in the bedroom", identity="j1_owner")
    assert live.table.get(keys.household_pk("judge-1"), keys.META)["storage_consent"] == "GRANTED"
    assert len(_items(live, keys.APPLIANCE_PREFIX, "judge-1")) == 1
