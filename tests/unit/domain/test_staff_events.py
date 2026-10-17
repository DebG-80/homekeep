from __future__ import annotations

import pytest

from app.domain import approvals, service, staff
from app.domain.errors import DomainError
from app.domain.issues import get_issue
from app.security.actor import Actor, ActorKind, StaffGroup
from app.store import keys
from tests.unit.domain.booking_helpers import approve, first_slot, ready_request, set_fault
from tests.unit.domain.world import HH_A, OWNER_A, TECHNICIAN, World

COORDINATOR = Actor(
    sub="sub-coordinator", kind=ActorKind.STAFF, groups=frozenset({StaffGroup.COORDINATOR})
)


def acknowledged(world: World, nickname: str = "Bedroom AC") -> dict:
    request = ready_request(world, nickname=nickname)
    set_fault(world, HH_A, "ACK_ONLY")
    approval_id = approve(
        world, "SUBMIT", request["request_id"], first_slot(world, request["request_id"])
    )
    assert approvals.execute_action(world.ctx(OWNER_A), approval_id)["outcome"] == "REQUESTED"
    view = service.get_service_status(world.ctx(OWNER_A), request_id=request["request_id"])
    stored = world.table.get(keys.household_pk(HH_A), keys.request_sk(request["request_id"]))
    return {**view["request"], "op_key": stored["op_key"]}


def test_ack_only_request_is_confirmed_by_a_coordinator_provider_event(world: World) -> None:
    request = acknowledged(world)
    with pytest.raises(DomainError) as denied:  # a technician cannot speak for the provider
        staff.post_event(
            world.ctx(TECHNICIAN), request["request_id"], "e-1", "PROVIDER_CONFIRMED", 1
        )
    assert denied.value.reason == "STAFF_ROLE_NOT_PERMITTED"

    result = staff.post_event(
        world.ctx(COORDINATOR),
        request["request_id"],
        "e-2",
        "PROVIDER_CONFIRMED",
        request["version"],
    )
    assert result["state"] == "CONFIRMED"
    status = service.get_service_status(world.ctx(OWNER_A), request_id=request["request_id"])
    assert status["appointment"]["status"] == "CONFIRMED"
    assert get_issue(world.ctx(OWNER_A), request["issue_id"])["status"] == "SERVICE_PENDING"
    again = staff.post_event(
        world.ctx(COORDINATOR),
        request["request_id"],
        "e-2",
        "PROVIDER_CONFIRMED",
        request["version"],
    )
    assert again == result  # a duplicate delivery changes nothing


def test_ack_only_request_rejected_by_provider_event_leaves_issue_open(world: World) -> None:
    request = acknowledged(world)
    result = staff.post_event(
        world.ctx(COORDINATOR),
        request["request_id"],
        "e-3",
        "PROVIDER_REJECTED",
        request["version"],
    )
    assert result["state"] == "REJECTED"
    assert get_issue(world.ctx(OWNER_A), request["issue_id"])["status"] == "SERVICE_NEEDED"


def _slot_taken(world: World, slot_id: str) -> int:
    return (world.table.get(keys.PROVIDER_PK, f"SLOT#{slot_id}") or {}).get("taken", 0)


def test_c1_reused_event_id_with_a_different_event_is_a_conflict(world: World) -> None:
    request = acknowledged(world)
    first = staff.post_event(
        world.ctx(COORDINATOR),
        request["request_id"],
        "e-9",
        "PROVIDER_CONFIRMED",
        request["version"],
    )
    with pytest.raises(DomainError) as reused:  # same key, different payload
        staff.post_event(
            world.ctx(COORDINATOR), request["request_id"], "e-9", "NO_SHOW", first["version"]
        )
    assert (reused.value.code.value, reused.value.reason) == ("RECORD_CONFLICT", "EVENT_ID_REUSED")
    assert staff.case_view(world.ctx(COORDINATOR), request["request_id"])["exception"] is None


def test_c1_event_ids_are_scoped_to_their_case(world: World) -> None:
    one = acknowledged(world)
    other = acknowledged(world, nickname="Hall AC")
    staff.post_event(
        world.ctx(COORDINATOR), one["request_id"], "e-1", "PROVIDER_CONFIRMED", one["version"]
    )
    result = staff.post_event(
        world.ctx(COORDINATOR), other["request_id"], "e-1", "PROVIDER_CONFIRMED", other["version"]
    )
    assert result["case_id"] == other["request_id"]  # never the other case's stored result
    status = service.get_service_status(world.ctx(OWNER_A), request_id=other["request_id"])
    assert status["request"]["state"] == "CONFIRMED"


def test_i4_provider_rejection_releases_the_place_and_needs_an_acknowledged_request(
    world: World,
) -> None:
    request = acknowledged(world)
    staff.post_event(
        world.ctx(COORDINATOR),
        request["request_id"],
        "e-r",
        "PROVIDER_REJECTED",
        request["version"],
    )
    assert _slot_taken(world, request["slot_id"]) == 0
    record = world.table.get(keys.PROVIDER_PK, f"REQ#{request['op_key']}")
    assert record["status"] == "REJECTED"  # the provider's own record agrees

    timed_out = ready_request(world, nickname="Hall AC")
    set_fault(world, HH_A, "TIMEOUT_AFTER_SUCCESS")
    approval_id = approve(
        world, "SUBMIT", timed_out["request_id"], first_slot(world, timed_out["request_id"])
    )
    pending = approvals.execute_action(world.ctx(OWNER_A), approval_id)["request"]
    with pytest.raises(DomainError) as refused:  # the provider may already have confirmed it
        staff.post_event(
            world.ctx(COORDINATOR),
            pending["request_id"],
            "e-p",
            "PROVIDER_REJECTED",
            pending["version"],
        )
    assert refused.value.reason == "UNDEFINED_TRANSITION"


def test_n3_no_show_needs_a_confirmed_visit(world: World) -> None:
    request = acknowledged(world)  # REQUESTED: no visit is fixed yet
    with pytest.raises(DomainError) as refused:
        staff.post_event(
            world.ctx(COORDINATOR), request["request_id"], "e-n", "NO_SHOW", request["version"]
        )
    assert refused.value.reason == "UNDEFINED_TRANSITION"
