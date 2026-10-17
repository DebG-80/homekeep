from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain import approvals, service
from app.domain.events import list_events
from app.domain.household import get_household
from app.domain.issues import get_issue
from app.security.actor import HouseholdRole
from app.store import keys
from tests.unit.domain.booking_helpers import approve, book, first_slot, ready_request, set_fault
from tests.unit.domain.world import (
    HH_A,
    OWNER_A,
    OWNER_B,
    VIEW_HELPER_A,
    World,
    actor,
    put_household,
)


def _appointments(world: World, household_id: str, request_id: str) -> list[dict]:
    return world.table.query(keys.household_pk(household_id), f"SR#{request_id}#APPT#")


def _slot_taken(world: World, slot_id: str) -> int:
    item = world.table.get(keys.PROVIDER_PK, f"SLOT#{slot_id}")
    return (item or {}).get("taken", 0)


def test_at13_domain_refuses_expired_superseded_and_foreign_approvals(
    world: World, expect_error
) -> None:
    request = ready_request(world)
    request_id = request["request_id"]
    slot = first_slot(world, request_id)

    expired = approvals.prepare_action(world.ctx(OWNER_A), "SUBMIT", request_id, slot)
    world.clock.advance(timedelta(minutes=6))
    expect_error(
        "APPROVAL_EXPIRED",
        None,
        approvals.confirm_action,
        world.ctx(OWNER_A),
        expired["pending_ref"],
        channel="text",
    )

    old = approvals.prepare_action(world.ctx(OWNER_A), "SUBMIT", request_id, slot)
    approvals.prepare_action(
        world.ctx(OWNER_A), "SUBMIT", request_id, first_slot(world, request_id, skip=1)
    )  # a corrected date
    expect_error(
        "APPROVAL_EXPIRED",
        "SUPERSEDED",
        approvals.confirm_action,
        world.ctx(OWNER_A),
        old["pending_ref"],
        channel="text",
    )

    current = approvals.pending_for_session(world.ctx(OWNER_A))
    other_session = world.ctx(OWNER_A)
    other_session = type(other_session)(**{**other_session.__dict__, "session_id": "session-2"})
    expect_error(
        "AUTH_DENIED",
        None,
        approvals.confirm_action,
        other_session,
        current["pending_ref"],
        channel="text",
    )
    # Voice approvals need the read-back to have finished before the "yes" began.
    finished = world.clock.now()
    expect_error(
        "AUTH_DENIED",
        "READBACK_NOT_FINISHED",
        approvals.confirm_action,
        world.ctx(OWNER_A),
        current["pending_ref"],
        channel="voice",
    )
    expect_error(
        "AUTH_DENIED",
        "SPOKE_DURING_READBACK",
        approvals.confirm_action,
        world.ctx(OWNER_A),
        current["pending_ref"],
        readback_completed_at=finished.isoformat(),
        speech_started_at=(finished - timedelta(seconds=1)).isoformat(),
        channel="voice",
    )
    # A view-only helper cannot even prepare a booking.
    expect_error(
        "AUTH_DENIED",
        None,
        approvals.prepare_action,
        world.ctx(VIEW_HELPER_A),
        "SUBMIT",
        request_id,
        slot,
    )
    assert _appointments(world, HH_A, request_id) == []


def test_at13_fresh_explicit_yes_books_once(world: World) -> None:
    request = ready_request(world)
    slot = first_slot(world, request["request_id"])
    pending = approvals.prepare_action(world.ctx(OWNER_A), "SUBMIT", request["request_id"], slot)
    world.clock.advance(timedelta(seconds=20))  # the read-back plays, then the elder answers
    started = world.clock.now()
    approved = approvals.confirm_action(
        world.ctx(OWNER_A),
        pending["pending_ref"],
        readback_completed_at=(started - timedelta(seconds=2)).isoformat(),
        speech_started_at=started.isoformat(),
        channel="voice",
    )
    first = approvals.execute_action(world.ctx(OWNER_A), approved["approval_id"])
    again = approvals.execute_action(world.ctx(OWNER_A), approved["approval_id"])
    assert first["outcome"] == "CONFIRMED"
    assert again == first  # executed once, whatever the retries
    assert first["request"]["mode"] == "DEMO"
    (appointment,) = _appointments(world, HH_A, request["request_id"])
    assert appointment["status"] == "CONFIRMED"
    assert _slot_taken(world, slot) == 1
    issue = get_issue(world.ctx(OWNER_A), first["request"]["issue_id"])
    assert issue["status"] == "SERVICE_PENDING"
    sentinel = world.table.get(keys.household_pk(HH_A), f"SR#{request['request_id']}#ACTIVE")
    assert sentinel["appointment_id"] == appointment["appointment_id"]


def test_at14_timeout_after_success_reconciles_to_one_reference(world: World) -> None:
    request = ready_request(world)
    slot = first_slot(world, request["request_id"])
    set_fault(world, HH_A, "TIMEOUT_AFTER_SUCCESS")
    approval_id = approve(world, "SUBMIT", request["request_id"], slot)
    pending = approvals.execute_action(
        world.ctx(OWNER_A, correlation_id="corr-dispatch"), approval_id
    )
    assert pending["outcome"] == "PENDING"  # never "confirmed" on a timeout
    assert pending["request"]["state"] == "SUBMISSION_PENDING"

    status = service.get_service_status(world.ctx(OWNER_A), request_id=request["request_id"])
    assert status["reconciled"] == "CONFIRMED"
    assert status["request"]["state"] == "CONFIRMED"
    retried = approvals.execute_action(
        world.ctx(OWNER_A), approval_id
    )  # a client retry after the timeout
    assert retried["outcome"] == "CONFIRMED"
    assert retried["request"]["provider_ref"] == status["request"]["provider_ref"]
    provider_requests = world.table.query(keys.PROVIDER_PK, "REQ#")
    assert len([r for r in provider_requests if r["kind"] == "SUBMIT"]) == 1  # one provider booking
    assert len(_appointments(world, HH_A, request["request_id"])) == 1
    trail = [
        e["action"]
        for e in list_events(world.ctx(OWNER_A), request["appliance_id"])
        if e["record"] == f"SR#{request['request_id']}"
    ]
    assert trail[-3:] == ["SERVICE_APPROVED", "SERVICE_SUBMITTED", "SERVICE_CONFIRMED"]
    # FR-28: approval, dispatch and reconciliation join on the approval and dispatch IDs.
    events = list_events(world.ctx(OWNER_A), request["appliance_id"])
    service_events = [e for e in events if e["record"] == f"SR#{request['request_id']}"]
    assert {e.get("approval_id") for e in service_events[-3:]} == {approval_id}
    assert {e.get("dispatch_correlation_id") for e in service_events[-3:]} == {"corr-dispatch"}
    approval_events = [e for e in events if e["action"] == "APPROVAL_CONFIRMED"]
    assert [e.get("approval_id") for e in approval_events] == [approval_id]


def test_at15_last_slot_one_winner_others_get_alternatives(world: World) -> None:
    request_a = ready_request(world)
    slot = first_slot(world, request_a["request_id"], window="PM")  # PM windows hold one booking
    owner_b_request = ready_request(world, OWNER_B, "Study AC")
    first_slot(
        world, owner_b_request["request_id"], window="PM", who=OWNER_B
    )  # B is offered it too
    approval_a = approve(world, "SUBMIT", request_a["request_id"], slot)
    approval_b = approve(world, "SUBMIT", owner_b_request["request_id"], slot, OWNER_B)

    assert approvals.execute_action(world.ctx(OWNER_A), approval_a)["outcome"] == "CONFIRMED"
    lost = approvals.execute_action(world.ctx(OWNER_B), approval_b)
    assert lost["outcome"] == "SLOT_UNAVAILABLE"
    assert lost["request"]["state"] == "DRAFT"  # nothing booked; a new time can be chosen
    assert _slot_taken(world, slot) == 1
    remaining = {
        s["slot_id"]: s["available"]
        for s in service.list_slots(world.ctx(OWNER_B), owner_b_request["request_id"])["slots"]
    }
    assert remaining[slot] is False


def test_at15_fee_change_requires_new_approval(world: World, expect_error) -> None:
    request = ready_request(world)
    slot = first_slot(world, request["request_id"])
    pending = approvals.prepare_action(world.ctx(OWNER_A), "SUBMIT", request["request_id"], slot)
    set_fault(world, HH_A, "FEE_CHANGE")
    expect_error(
        "RECORD_CONFLICT",
        "FEE_CHANGED",
        approvals.confirm_action,
        world.ctx(OWNER_A),
        pending["pending_ref"],
        channel="text",
    )
    assert _appointments(world, HH_A, request["request_id"]) == []
    assert (
        book(world, request["request_id"], slot)["outcome"] == "CONFIRMED"
    )  # a fresh read-back and approval


def test_at16_failed_reschedule_keeps_original_success_supersedes_once(world: World) -> None:
    request = ready_request(world)
    first = first_slot(world, request["request_id"])
    book(world, request["request_id"], first)
    second = first_slot(world, request["request_id"], skip=1)

    set_fault(world, HH_A, "REPLACE_FAIL")
    failed = approvals.execute_action(
        world.ctx(OWNER_A), approve(world, "RESCHEDULE", request["request_id"], second)
    )
    assert failed["outcome"] == "CHANGE_FAILED"
    assert failed["request"]["state"] == "CONFIRMED"
    assert failed["appointment"]["slot_id"] == first  # the original stays

    changed = approvals.execute_action(
        world.ctx(OWNER_A), approve(world, "RESCHEDULE", request["request_id"], second)
    )
    assert changed["outcome"] == "CHANGED"
    statuses = {
        a["slot_id"]: a["status"] for a in _appointments(world, HH_A, request["request_id"])
    }
    assert statuses == {first: "SUPERSEDED", second: "CONFIRMED"}
    assert (_slot_taken(world, first), _slot_taken(world, second)) == (0, 1)


def test_at17_cancel_timeout_pending_refusal_restores_confirmation_cancels_issue_unresolved(
    world: World,
) -> None:
    request = ready_request(world)
    book(world, request["request_id"], first_slot(world, request["request_id"]))

    set_fault(world, HH_A, "CANCEL_REFUSE")
    refused = approvals.execute_action(
        world.ctx(OWNER_A), approve(world, "CANCEL", request["request_id"])
    )
    assert (refused["outcome"], refused["request"]["state"]) == ("CANCEL_REFUSED", "CONFIRMED")

    set_fault(world, HH_A, "CANCEL_TIMEOUT")
    pending = approvals.execute_action(
        world.ctx(OWNER_A), approve(world, "CANCEL", request["request_id"])
    )
    assert (pending["outcome"], pending["request"]["state"]) == (
        "CANCEL_PENDING",
        "CANCEL_PENDING",
    )  # not "cancelled"

    status = service.get_service_status(world.ctx(OWNER_A), request_id=request["request_id"])
    assert (status["reconciled"], status["request"]["state"]) == ("CANCELLED", "CANCELLED")
    (appointment,) = _appointments(world, HH_A, request["request_id"])
    assert appointment["status"] == "CANCELLED"
    assert (
        get_issue(world.ctx(OWNER_A), request["issue_id"])["status"] == "SERVICE_NEEDED"
    )  # unresolved


def test_at34_local_midnight_rollover_and_concurrent_edit_invalidates_approval(
    world: World, expect_error
) -> None:
    request = ready_request(world)
    world.clock.instant = datetime(2026, 10, 16, 18, 29, tzinfo=UTC)  # 23:59 in Kolkata
    before = service.list_slots(world.ctx(OWNER_A), request["request_id"])["slots"][0]
    world.clock.instant = datetime(2026, 10, 16, 18, 31, tzinfo=UTC)  # 00:01 on the 17th
    after = service.list_slots(world.ctx(OWNER_A), request["request_id"])["slots"][0]
    assert before["date"] == "2026-10-17"
    assert after["date"] == "2026-10-17"  # "today" rolled over; its morning window is still ahead
    assert after["date_words"] == "Saturday, 17 October"

    pending = approvals.prepare_action(
        world.ctx(OWNER_A), "SUBMIT", request["request_id"], after["slot_id"]
    )
    current = service.get_service_status(world.ctx(OWNER_A), request_id=request["request_id"])[
        "request"
    ]
    service.record_service_details(
        world.ctx(OWNER_A),
        request["request_id"],
        "address",
        "Flat 9, Other Place",
        current["version"],
    )
    expect_error(
        "RECORD_CONFLICT",
        None,
        approvals.confirm_action,
        world.ctx(OWNER_A),
        pending["pending_ref"],
        channel="text",
    )


def test_g3_6_consent_by_voice_unlocks_persistence(world: World, expect_error) -> None:
    put_household(world.table, HH_A, storage=None)
    helper = actor(HH_A, HouseholdRole.HELPER, sub="sub-a-helper-all")
    expect_error(
        "AUTH_DENIED", None, approvals.prepare_action, world.ctx(helper), "CONSENT_STORAGE"
    )
    outcome = approvals.execute_action(world.ctx(OWNER_A), approve(world, "CONSENT_STORAGE"))
    assert outcome["outcome"] == "CONSENT_RECORDED"
    assert get_household(world.ctx(OWNER_A))["storage_consent"] == "GRANTED"


def test_g3_10_unavailable_provider_fails_terminally(world: World) -> None:
    request = ready_request(world)
    set_fault(world, HH_A, "UNAVAILABLE")
    failed = book(world, request["request_id"], first_slot(world, request["request_id"]))
    assert (failed["outcome"], failed["request"]["state"]) == ("FAILED", "FAILED")
    # A follow-up is a new request linked to the same issue.
    again = service.draft_service_request(world.ctx(OWNER_A), request["issue_id"])
    assert again["outcome"] == "CREATED"
    assert again["request"]["request_id"] != request["request_id"]
