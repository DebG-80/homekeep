from __future__ import annotations

from app.domain import approvals, service
from app.provider.sweep import sweep_once
from app.store import keys
from tests.unit.domain.booking_helpers import approve, first_slot, ready_request, set_fault
from tests.unit.domain.world import HH_A, OWNER_A, World


def test_p3_1_sweep_reconciles_pending_requests_once(world: World) -> None:
    request = ready_request(world)
    set_fault(world, HH_A, "TIMEOUT_AFTER_SUCCESS")
    approval_id = approve(
        world, "SUBMIT", request["request_id"], first_slot(world, request["request_id"])
    )
    assert approvals.execute_action(world.ctx(OWNER_A), approval_id)["outcome"] == "PENDING"

    assert (
        sweep_once(world.table, world.clock, faults_enabled=True) == 1
    )  # nobody asked; the sweep finds it
    status = service.get_service_status(world.ctx(OWNER_A), request_id=request["request_id"])
    assert (status["request"]["state"], status["reconciled"]) == ("CONFIRMED", None)
    assert sweep_once(world.table, world.clock, faults_enabled=True) == 0  # nothing left pending
    appointments = world.table.query(keys.household_pk(HH_A), f"SR#{request['request_id']}#APPT#")
    assert len(appointments) == 1
    sweep_event = [
        e for e in world.items(HH_A, keys.EVENT_PREFIX) if e["action"] == "SERVICE_CONFIRMED"
    ]
    assert sweep_event[-1]["actor_role"] == "SYSTEM"


def test_n5_sweep_skips_a_pending_item_whose_household_does_not_match_its_partition(
    world: World,
) -> None:
    """The sweep's identity is scoped to the partition the item lives in; an item claiming
    another household is never reconciled under it."""
    request = ready_request(world)
    set_fault(world, HH_A, "TIMEOUT_AFTER_SUCCESS")
    approval_id = approve(
        world, "SUBMIT", request["request_id"], first_slot(world, request["request_id"])
    )
    approvals.execute_action(world.ctx(OWNER_A), approval_id)
    item = world.table.get(keys.household_pk(HH_A), keys.request_sk(request["request_id"]))
    world.table.put({**item, "household_id": "hh-somebody-else"})
    assert sweep_once(world.table, world.clock, faults_enabled=True) == 0
    still = world.table.get(keys.household_pk(HH_A), keys.request_sk(request["request_id"]))
    assert still["state"] == "SUBMISSION_PENDING"
    assert world.items("hh-somebody-else") == []  # nothing written under the other household
    assert [e for e in world.items(HH_A, keys.EVENT_PREFIX) if e["actor_role"] == "SYSTEM"] == []
