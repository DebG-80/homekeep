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
