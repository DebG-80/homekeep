"""Members and grants in the domain (FR-20; plan G4-5, G4-13)."""

from __future__ import annotations

import re

import pytest

from app.domain import approvals, members
from app.domain.errors import DomainError
from app.security.actor import Grant, HouseholdRole
from app.store import keys
from tests.unit.domain.booking_helpers import approve, first_slot, ready_request, set_fault
from tests.unit.domain.world import HH_A, OWNER_A, World, actor


def _add_helper(world: World, sub: str, *grants: str) -> None:
    world.table.put(
        {
            "PK": keys.household_pk(HH_A),
            "SK": keys.member_sk(sub),
            "kind": "MEMBERSHIP",
            "sub": sub,
            "display_name": f"name-{sub}",
            "role": "HELPER",
            "grants": list(grants),
            "status": "ACTIVE",
            "version": 1,
        }
    )


def _ref(world: World, sub: str) -> str:
    listed = members.list_members(world.ctx(OWNER_A))["members"]
    return next(m["member_ref"] for m in listed if m["display_name"] == f"name-{sub}")


def test_g4_13_member_refs_are_opaque(world: World) -> None:
    _add_helper(world, "sub-helper-1", "view")
    ref = _ref(world, "sub-helper-1")
    assert re.fullmatch(r"[0-9a-f]{24}", ref)  # opaque: the subject never leaves the server
    assert ref != members.member_ref("hh-b", "sub-helper-1")  # and differs per household
    expect_error = pytest.raises(DomainError)
    with expect_error:  # the raw subject is not accepted in its place
        members.set_grants(world.ctx(OWNER_A), "sub-helper-1", ["view"])
    assert members.set_grants(world.ctx(OWNER_A), ref, ["view", "edit"])["grants"] == [
        "view",
        "edit",
    ]


def test_fr20_grants_never_beyond_the_owners_own(world: World, expect_error) -> None:
    _add_helper(world, "sub-helper-2", "view")
    limited_owner = actor(HH_A, HouseholdRole.OWNER, Grant.VIEW, Grant.EDIT, sub="sub-a-owner")
    expect_error(
        "INVALID_INPUT",
        "BEYOND_OWNER",
        members.set_grants,
        world.ctx(limited_owner),
        _ref(world, "sub-helper-2"),
        ["view", "book"],
    )


def test_revocation_cancels_waiting_approvals_but_not_a_booking_already_sent(
    world: World,
) -> None:
    helper = actor(HH_A, HouseholdRole.HELPER, *Grant, sub="sub-helper-3")
    _add_helper(world, "sub-helper-3", "view", "edit", "book", "updates")
    sent = ready_request(world, helper, "Hall AC")
    set_fault(world, HH_A, "TIMEOUT_AFTER_SUCCESS")
    in_flight = approve(
        world,
        "SUBMIT",
        sent["request_id"],
        first_slot(world, sent["request_id"], who=helper),
        helper,
    )
    assert approvals.execute_action(world.ctx(helper), in_flight)["outcome"] == "PENDING"
    waiting = ready_request(world, helper, "Study AC")
    pending = approvals.prepare_action(
        world.ctx(helper),
        "SUBMIT",
        waiting["request_id"],
        first_slot(world, waiting["request_id"], who=helper),
    )["pending_ref"]

    members.revoke(world.ctx(OWNER_A), _ref(world, "sub-helper-3"))

    state = lambda approval_id: world.table.get(  # noqa: E731
        keys.household_pk(HH_A), keys.approval_sk(approval_id)
    )["state"]
    assert state(pending) == "CANCELLED"
    assert state(in_flight) == "APPROVED"  # already dispatched: the booking carries on
