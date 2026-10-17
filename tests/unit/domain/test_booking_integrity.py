"""Slice 3 review fixes: retries, races, lost dispatches, offers and read-back timing."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from app.domain import approvals, booking, requests, service
from app.provider.simulator import DemoProvider
from app.provider.sweep import sweep_once
from app.store import keys
from tests.unit.domain.booking_helpers import approve, book, first_slot, ready_request, set_fault
from tests.unit.domain.world import HH_A, OWNER_A, World


def _appointments(world: World, request_id: str) -> list[dict[str, Any]]:
    return world.table.query(keys.household_pk(HH_A), f"SR#{request_id}#APPT#")


def _slot_taken(world: World, slot_id: str) -> int:
    return (world.table.get(keys.PROVIDER_PK, f"SLOT#{slot_id}") or {}).get("taken", 0)


def _unexecute(world: World, approval_id: str) -> None:
    """The booking write committed but marking the approval EXECUTED did not (a crash)."""
    item = world.table.get(keys.household_pk(HH_A), keys.approval_sk(approval_id))
    world.table.put({**{k: v for k, v in item.items() if k != "result"}, "state": "APPROVED"})


def test_i1_reschedule_retried_after_success_supersedes_exactly_once(world: World) -> None:
    request = ready_request(world)
    first = first_slot(world, request["request_id"])
    book(world, request["request_id"], first)
    second = first_slot(world, request["request_id"], skip=1)
    approval_id = approve(world, "RESCHEDULE", request["request_id"], second)
    assert approvals.execute_action(world.ctx(OWNER_A), approval_id)["outcome"] == "CHANGED"

    _unexecute(world, approval_id)
    retried = approvals.execute_action(world.ctx(OWNER_A), approval_id)
    assert retried["outcome"] == "CHANGED"
    statuses = sorted(
        (a["slot_id"], a["status"]) for a in _appointments(world, request["request_id"])
    )
    assert statuses == [(first, "SUPERSEDED"), (second, "CONFIRMED")]  # FR-14-AC1
    assert (_slot_taken(world, first), _slot_taken(world, second)) == (0, 1)


def test_i1_cancel_retried_after_refusal_does_not_cancel_again(world: World) -> None:
    request = ready_request(world)
    book(world, request["request_id"], first_slot(world, request["request_id"]))
    set_fault(world, HH_A, "CANCEL_REFUSE")
    approval_id = approve(world, "CANCEL", request["request_id"])
    assert approvals.execute_action(world.ctx(OWNER_A), approval_id)["outcome"] == "CANCEL_REFUSED"

    _unexecute(world, approval_id)
    retried = approvals.execute_action(world.ctx(OWNER_A), approval_id)
    assert (retried["outcome"], retried["request"]["state"]) == ("CANCEL_REFUSED", "CONFIRMED")


def test_i3_reconcile_that_loses_a_race_rereads_instead_of_failing(world: World) -> None:
    request = ready_request(world)
    set_fault(world, HH_A, "TIMEOUT_AFTER_SUCCESS")
    approval_id = approve(
        world, "SUBMIT", request["request_id"], first_slot(world, request["request_id"])
    )
    assert approvals.execute_action(world.ctx(OWNER_A), approval_id)["outcome"] == "PENDING"
    stale = requests.load(world.ctx(OWNER_A), request["request_id"])

    assert sweep_once(world.table, world.clock, faults_enabled=True) == 1  # the sweep wins
    assert booking.reconcile(world.ctx(OWNER_A), stale) == "CONFIRMED"  # the loser re-reads
    retried = approvals.execute_action(world.ctx(OWNER_A), approval_id)
    assert retried["outcome"] == "CONFIRMED"
    assert len(_appointments(world, request["request_id"])) == 1


def test_i4c_slot_place_and_provider_record_are_written_together(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = DemoProvider(world.table, world.clock, faults_enabled=False)
    slot = provider.list_slots(world.clock.now().date() + timedelta(days=1), 1)[0].slot_id
    first = provider.submit(HH_A, "op-1", slot)
    # A concurrent duplicate that also saw "no record yet" must not take a second place.
    monkeypatch.setattr(DemoProvider, "status", lambda self, key: None)
    again = provider.submit(HH_A, "op-1", slot)
    assert again["provider_ref"] == first["provider_ref"]
    assert _slot_taken(world, slot) == 1


def test_i5_lost_dispatch_is_redispatched_and_a_stuck_one_raises_manual_review(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = ready_request(world)
    approval_id = approve(
        world, "SUBMIT", request["request_id"], first_slot(world, request["request_id"])
    )
    real_submit = DemoProvider.submit

    def crash(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("process died after persisting, before the provider heard")

    monkeypatch.setattr(DemoProvider, "submit", crash)
    with pytest.raises(RuntimeError):
        approvals.execute_action(world.ctx(OWNER_A), approval_id)
    assert requests.load(world.ctx(OWNER_A), request["request_id"])["state"] == "SUBMISSION_PENDING"

    # Still crashing well past the deadline: one manual-review item, however many sweeps run.
    world.clock.advance(timedelta(minutes=16))
    sweep_once(world.table, world.clock, faults_enabled=True)
    sweep_once(world.table, world.clock, faults_enabled=True)
    manual = world.table.query(keys.OPS_PK, "MANUAL#")
    assert [(m["case_id"], m["reason"]) for m in manual] == [
        (request["request_id"], "DISPATCH_UNKNOWN")
    ]

    monkeypatch.setattr(DemoProvider, "submit", real_submit)  # the provider is reachable again
    assert sweep_once(world.table, world.clock, faults_enabled=True) == 1
    status = service.get_service_status(world.ctx(OWNER_A), request_id=request["request_id"])
    assert status["request"]["state"] == "CONFIRMED"


def test_i5_fresh_pending_request_is_not_redispatched(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = ready_request(world)
    approval_id = approve(
        world, "SUBMIT", request["request_id"], first_slot(world, request["request_id"])
    )
    calls: list[str] = []

    def down(*args: Any, **kwargs: Any) -> Any:
        calls.append("submit")
        raise RuntimeError("down")

    monkeypatch.setattr(DemoProvider, "submit", down)
    with pytest.raises(RuntimeError):
        approvals.execute_action(world.ctx(OWNER_A), approval_id)
    sweep_once(world.table, world.clock, faults_enabled=True)  # within a minute: leave it
    assert calls == ["submit"]


def test_i15_one_open_request_per_issue_even_when_drafts_race(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = ready_request(world)
    # Both the elder and a helper read "no open request" at the same moment.
    monkeypatch.setattr(requests, "open_request_for_issue", lambda ctx, issue_id: None)
    raced = service.draft_service_request(
        world.ctx(OWNER_A, turn_id="turn-race"), request["issue_id"]
    )
    assert raced["outcome"] == "EXISTING"
    assert raced["request"]["request_id"] == request["request_id"]
    drafts = [i for i in world.items(HH_A, keys.REQUEST_PREFIX) if i.get("kind") == "SR"]
    assert len(drafts) == 1


def test_i7_approval_needs_a_listed_slot_and_expires_with_the_offer(
    world: World, expect_error
) -> None:
    request = ready_request(world)
    unlisted = (
        DemoProvider(world.table, world.clock, False)
        .list_slots(world.clock.now().date() + timedelta(days=2), 1)[0]
        .slot_id
    )
    expect_error(
        "INVALID_INPUT",
        "SLOT_NOT_OFFERED",
        approvals.prepare_action,
        world.ctx(OWNER_A),
        "SUBMIT",
        request["request_id"],
        unlisted,
    )
    offered = service.list_slots(world.ctx(OWNER_A), request["request_id"])
    slot = next(s["slot_id"] for s in offered["slots"] if s["available"])
    world.clock.advance(timedelta(minutes=8))
    pending = approvals.prepare_action(world.ctx(OWNER_A), "SUBMIT", request["request_id"], slot)
    assert pending["expires_at"] == offered["offer_expires_at"]  # earlier than 5 minutes
    world.clock.advance(timedelta(minutes=3))
    expect_error(
        "APPROVAL_EXPIRED",
        None,
        approvals.confirm_action,
        world.ctx(OWNER_A),
        pending["pending_ref"],
        channel="text",
    )
    world.clock.advance(timedelta(minutes=1))
    expect_error(  # the offer itself has lapsed: list again
        "INVALID_INPUT",
        "SLOT_NOT_OFFERED",
        approvals.prepare_action,
        world.ctx(OWNER_A),
        "SUBMIT",
        request["request_id"],
        slot,
    )


def test_i8_voice_times_must_fall_after_the_readback_was_prepared(
    world: World, expect_error
) -> None:
    request = ready_request(world)
    slot = first_slot(world, request["request_id"])
    pending = approvals.prepare_action(world.ctx(OWNER_A), "SUBMIT", request["request_id"], slot)
    now = world.clock.now()
    earlier = (now - timedelta(minutes=1)).isoformat()  # the playback of the previous reply
    expect_error(
        "AUTH_DENIED",
        "READBACK_NOT_FINISHED",
        approvals.confirm_action,
        world.ctx(OWNER_A),
        pending["pending_ref"],
        readback_completed_at=earlier,
        speech_started_at=(now + timedelta(seconds=1)).isoformat(),
        channel="voice",
    )
    world.clock.advance(timedelta(seconds=20))
    expect_error(
        "AUTH_DENIED",
        "SPEECH_TIME_INVALID",
        approvals.confirm_action,
        world.ctx(OWNER_A),
        pending["pending_ref"],
        readback_completed_at=(now + timedelta(seconds=10)).isoformat(),
        speech_started_at=(now + timedelta(minutes=5)).isoformat(),  # in the future
        channel="voice",
    )


def test_i2_outcome_after_a_failed_execute_is_read_from_the_records(world: World) -> None:
    request = ready_request(world)
    approval_id = approve(
        world, "SUBMIT", request["request_id"], first_slot(world, request["request_id"])
    )
    # Nothing was dispatched: never "sent" or "pending".
    assert approvals.outcome_after_failure(world.ctx(OWNER_A), approval_id)["outcome"] == "NOT_SENT"

    set_fault(world, HH_A, "TIMEOUT_AFTER_SUCCESS")
    assert approvals.execute_action(world.ctx(OWNER_A), approval_id)["outcome"] == "PENDING"
    after = approvals.outcome_after_failure(world.ctx(OWNER_A), approval_id)
    assert after["outcome"] == "CONFIRMED"  # reconciled first: the provider did record it


def test_i2_consent_outcome_after_failure_is_not_sent(world: World) -> None:
    approval_id = approve(world, "CONSENT_SHARING")
    assert approvals.outcome_after_failure(world.ctx(OWNER_A), approval_id)["outcome"] == "NOT_SENT"
