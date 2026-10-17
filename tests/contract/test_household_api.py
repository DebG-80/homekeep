"""Household API for the web views: members, grants, revocation and the judges' reset (FR-20,
FR-24; AT-21; plan G4-3, G4-5)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.domain import approvals, service
from app.domain.clock import SystemClock
from app.domain.context import OperationContext
from app.domain.issues import report_issue
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole
from app.store import keys
from tests.contract.live import LiveServer, api, call_tool, new_session, turn


def _members(live: LiveServer, identity: str) -> list[dict[str, Any]]:
    response = api(live, "GET", "/api/household/members", identity)
    assert response.status_code == 200, response.text
    return response.json()["members"]


def _member_ref(live: LiveServer, display_name: str) -> str:
    return next(
        m["member_ref"] for m in _members(live, "a_owner") if m["display_name"] == display_name
    )


def _booking_helper_ctx(live: LiveServer) -> OperationContext:
    helper = Actor(
        sub="local-a_helper_booking",
        kind=ActorKind.HOUSEHOLD,
        household_id="qa-a",
        role=HouseholdRole.HELPER,
        grants=frozenset(Grant),
    )
    return OperationContext(
        helper,
        live.table,
        SystemClock(),
        f"corr-{uuid.uuid4().hex[:8]}",
        turn_id=f"turn-{uuid.uuid4().hex[:8]}",
        session_id="session-helper",
    )


def test_at21_view_helper_cannot_book_revoked_helper_old_token_and_pending_action_denied(
    live: LiveServer,
) -> None:
    # A view-only helper cannot book (FR-20-AC1).
    refused = call_tool(
        live,
        "prepare_action",
        {"kind": "SUBMIT", "request_id": "any", "slot_id": "any"},
        identity="a_helper_view",
    )
    assert (refused["status"], refused["error"]["code"]) == ("ERROR", "AUTH_DENIED")

    # The booking helper has a booking awaiting approval and a token issued before revocation.
    old_token = live.token("a_helper_booking")
    helper = _booking_helper_ctx(live)
    issue_id = report_issue(
        helper, "qa-a-ac-hall", "Not cooling", "NOT_COOLING", confirmed_distinct=True
    )["issue"]["issue_id"]
    request_id = service.draft_service_request(_booking_helper_ctx(live), issue_id)["request"][
        "request_id"
    ]
    slot = next(
        s["slot_id"]
        for s in service.list_slots(_booking_helper_ctx(live), request_id, days=5)["slots"]
        if s["available"]
    )
    pending = approvals.prepare_action(_booking_helper_ctx(live), "SUBMIT", request_id, slot)[
        "pending_ref"
    ]
    assert api(live, "GET", "/api/household", "a_helper_booking").status_code == 200

    revoked = api(
        live,
        "POST",
        f"/api/household/members/{_member_ref(live, 'hk-qa-a-booker')}/revoke",
        "a_owner",
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "REVOKED"

    # FR-20-AC2: the old session can neither read nor act.
    headers = {"Authorization": f"Bearer {old_token}"}
    read = httpx.get(f"{live.base_url}/api/household", headers=headers, timeout=30)
    assert read.status_code == 403
    session_start = httpx.post(f"{live.base_url}/api/sessions", headers=headers, timeout=30)
    assert session_start.status_code == 403
    approval = live.table.get(keys.household_pk("qa-a"), keys.approval_sk(pending))
    assert approval["state"] == "CANCELLED"  # the pending action is gone too
    execute = {"approval_id": pending}
    attest = live.attestor.sign(
        "local-a_helper_booking", "session-helper", "t-1", "execute_action", execute
    )
    denied = call_tool(
        live,
        "execute_action",
        execute,
        identity="a_helper_booking",
        headers={"X-HK-Session-Id": "session-helper", "X-HK-Turn-Id": "t-1", "X-HK-Attest": attest},
    )
    assert (denied["status"], denied["error"]["code"]) == ("ERROR", "AUTH_DENIED")
    # The household itself carries on.
    assert api(live, "GET", "/api/household", "a_owner").status_code == 200


def test_fr20_owner_sets_grants_never_beyond_owner_and_cannot_revoke_self(
    live: LiveServer,
) -> None:
    owner_view = _members(live, "a_owner")
    assert {m["display_name"] for m in owner_view} == {
        "hk-qa-a-owner",
        "hk-qa-a-viewer",
        "hk-qa-a-booker",
        "hk-qa-a-revoked",
    }
    assert set(owner_view[0]) == {
        "member_ref",
        "display_name",
        "role",
        "grants",
        "status",
        "is_you",
    }
    assert not any("local-" in m["member_ref"] for m in owner_view)  # opaque, not the subject
    # Helpers see only their own grants (BRD §11.2).
    assert [m["display_name"] for m in _members(live, "a_helper_view")] == ["hk-qa-a-viewer"]

    viewer = _member_ref(live, "hk-qa-a-viewer")
    changed = api(
        live,
        "POST",
        f"/api/household/members/{viewer}/grants",
        "a_owner",
        json={"grants": ["view", "edit"]},
    )
    assert changed.status_code == 200, changed.text
    assert sorted(changed.json()["grants"]) == ["edit", "view"]
    unknown = api(
        live,
        "POST",
        f"/api/household/members/{viewer}/grants",
        "a_owner",
        json={"grants": ["admin"]},
    )
    assert unknown.status_code == 422
    no_view = api(
        live,
        "POST",
        f"/api/household/members/{viewer}/grants",
        "a_owner",
        json={"grants": ["book"]},
    )
    assert no_view.status_code == 400  # every grant needs view

    owner_ref = _member_ref(live, "hk-qa-a-owner")
    assert (
        api(live, "POST", f"/api/household/members/{owner_ref}/revoke", "a_owner").status_code
        == 400
    )
    assert (
        api(
            live,
            "POST",
            f"/api/household/members/{owner_ref}/grants",
            "a_owner",
            json={"grants": ["view"]},
        ).status_code
        == 400
    )
    # Only the owner manages grants.
    assert (
        api(
            live,
            "POST",
            f"/api/household/members/{viewer}/grants",
            "a_helper_booking",
            json={"grants": ["view"]},
        ).status_code
        == 403
    )


def test_reset_only_owner_of_resettable_household(live: LiveServer) -> None:
    session = new_session(live, "j1_owner")
    turn(live, session, "hello", identity="j1_owner")
    reset = api(live, "POST", "/api/household/reset", "j1_owner")
    assert reset.status_code == 200, reset.text
    assert api(live, "POST", "/api/household/reset", "a_owner").status_code == 400  # not a judge
    assert api(live, "POST", "/api/household/reset", "a_helper_booking").status_code == 403


def test_household_view_labels_missing_data_and_history(live: LiveServer) -> None:
    household = api(live, "GET", "/api/household", "a_owner").json()
    hall = next(a for a in household["appliances"] if a["appliance_id"] == "qa-a-ac-hall")
    assert hall["fields"]["model"]["status"] == "UNKNOWN"  # shown as "not provided", not an error
    assert household["role"] == "OWNER"
    assert household["resettable"] is False
    history = api(live, "GET", "/api/appliances/qa-a-ac-bedroom/history", "a_owner")
    assert history.status_code == 200
    assert history.json()["appliance"] == "Bedroom AC"
    other = api(live, "GET", "/api/appliances/qa-b-ac-study/history", "a_owner")
    assert other.status_code == 404  # another household's appliance does not exist for A
