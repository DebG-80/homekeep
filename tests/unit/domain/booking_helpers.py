"""Shared steps for service and booking tests: an issue, a complete draft, an approved action."""

from __future__ import annotations

from typing import Any

from app.domain import approvals, service
from app.domain.appliances import register_appliance
from app.domain.issues import report_issue
from app.store import keys
from tests.unit.domain.world import OWNER_A, World

ADDRESS = "Flat 4, Example Residency, Pune"
CONTACT = "Landline 000 0000 0000"


def issue(world: World, nickname: str = "Bedroom AC", who: Any = OWNER_A) -> str:
    appliance_id = register_appliance(world.ctx(who), "AC", nickname)["appliance_id"]
    reported = report_issue(world.ctx(who), appliance_id, "Not cooling", "NOT_COOLING")
    return reported["issue"]["issue_id"]


def ready_request(world: World, who: Any = OWNER_A, nickname: str = "Bedroom AC") -> dict[str, Any]:
    request = service.draft_service_request(world.ctx(who), issue(world, nickname, who))["request"]
    request = service.record_service_details(
        world.ctx(who), request["request_id"], "address", ADDRESS, request["version"]
    )
    return service.record_service_details(
        world.ctx(who), request["request_id"], "contact", CONTACT, request["version"]
    )


def first_slot(
    world: World, request_id: str, window: str = "AM", who: Any = OWNER_A, skip: int = 0
) -> str:
    slots = [
        s
        for s in service.list_slots(world.ctx(who), request_id)["slots"]
        if s["window"] == window and s["available"]
    ]
    return slots[skip]["slot_id"]


def approve(
    world: World,
    kind: str,
    request_id: str | None = None,
    slot_id: str | None = None,
    who: Any = OWNER_A,
) -> str:
    pending = approvals.prepare_action(world.ctx(who), kind, request_id, slot_id)
    approved = approvals.confirm_action(world.ctx(who), pending["pending_ref"], channel="text")
    return approved["approval_id"]


def book(world: World, request_id: str, slot_id: str, who: Any = OWNER_A) -> dict[str, Any]:
    return approvals.execute_action(
        world.ctx(who), approve(world, "SUBMIT", request_id, slot_id, who)
    )


def set_fault(world: World, household_id: str, fault: str, remaining: int = 1) -> None:
    world.table.put(
        {
            "PK": keys.PROVIDER_PK,
            "SK": f"FAULT#{household_id}",
            "fault": fault,
            "remaining": remaining,
        }
    )
