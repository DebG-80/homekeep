from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.domain import approvals, history, service
from app.domain.clock import SystemClock
from app.domain.context import OperationContext
from app.domain.issues import confirm_resolution, get_issue, report_issue, report_warning_sign
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole
from app.security.local_issuer import LocalIssuer
from app.store import keys
from app.store.table import Table
from scripts import seed
from tests.contract.live import LiveServer, serve

GROUPS = {
    "tech_assigned": ["technician"],
    "tech_unassigned": ["technician"],
    "coordinator": ["coordinator"],
    "catalog_reviewer": ["catalog_reviewer"],
    "admin": ["admin"],
}


@pytest.fixture
def live(table: Table, issuer: LocalIssuer) -> Iterator[LiveServer]:
    seed.seed_local(table)
    with serve(table, issuer, start_sweep=False) as server:
        yield server


def staff(
    live: LiveServer, identity: str | None, method: str, path: str, **kwargs: Any
) -> httpx.Response:
    headers = {}
    if identity:
        token = live.token(identity, groups=GROUPS.get(identity, []))
        headers["Authorization"] = f"Bearer {token}"
    return httpx.request(
        method, f"{live.base_url}/api/staff{path}", headers=headers, timeout=30, **kwargs
    )


def owner_ctx(live: LiveServer) -> OperationContext:
    owner = Actor(
        sub="local-a_owner",
        kind=ActorKind.HOUSEHOLD,
        household_id="qa-a",
        role=HouseholdRole.OWNER,
        grants=frozenset(Grant),
    )
    return OperationContext(
        owner,
        live.table,
        SystemClock(),
        f"corr-{uuid.uuid4().hex[:8]}",
        turn_id=f"turn-{uuid.uuid4().hex[:8]}",
        session_id="session-staff-tests",
    )


def confirmed_case(live: LiveServer, appliance_id: str = "qa-a-ac-bedroom") -> dict[str, str]:
    issue_id = report_issue(
        owner_ctx(live), appliance_id, "Not cooling", "NOT_COOLING", confirmed_distinct=True
    )["issue"]["issue_id"]
    request = service.draft_service_request(owner_ctx(live), issue_id)["request"]
    slot = next(
        s["slot_id"]
        for s in service.list_slots(owner_ctx(live), request["request_id"], days=5)["slots"]
        if s["available"]
    )
    pending = approvals.prepare_action(owner_ctx(live), "SUBMIT", request["request_id"], slot)
    approval = approvals.confirm_action(owner_ctx(live), pending["pending_ref"], channel="text")
    outcome = approvals.execute_action(owner_ctx(live), approval["approval_id"])
    assert outcome["outcome"] == "CONFIRMED"
    return {"case_id": request["request_id"], "issue_id": issue_id}


def case(live: LiveServer, case_id: str, identity: str = "coordinator") -> dict[str, Any]:
    response = staff(live, identity, "GET", f"/cases/{case_id}")
    assert response.status_code == 200, response.text
    return response.json()


def event(
    live: LiveServer,
    identity: str,
    case_id: str,
    kind: str,
    version: int,
    event_id: str | None = None,
    **extra: Any,
) -> httpx.Response:
    body = {
        "event_id": event_id or f"evt-{uuid.uuid4().hex[:8]}",
        "type": kind,
        "expected_version": version,
        **extra,
    }
    return staff(live, identity, "POST", f"/cases/{case_id}/events", json=body)


def test_at18_only_assigned_technician_duplicate_and_stale_events_do_not_regress(
    live: LiveServer,
) -> None:
    ids = confirmed_case(live)
    version = case(live, ids["case_id"])["version"]
    assert (
        event(live, "tech_unassigned", ids["case_id"], "VISIT_STARTED", version).status_code == 403
    )

    started = event(live, "tech_assigned", ids["case_id"], "VISIT_STARTED", version)
    assert (started.status_code, started.json()["state"]) == (200, "IN_PROGRESS")
    version = started.json()["version"]
    first = event(
        live,
        "tech_assigned",
        ids["case_id"],
        "VISIT_COMPLETED",
        version,
        "evt-done",
        summary="Cleaned the drain line.",
    )
    duplicate = event(
        live,
        "tech_assigned",
        ids["case_id"],
        "VISIT_COMPLETED",
        version,
        "evt-done",
        summary="Cleaned the drain line.",
    )
    assert first.status_code == duplicate.status_code == 200
    assert duplicate.json() == first.json()  # one event, whatever the retries
    stale = event(
        live, "tech_assigned", ids["case_id"], "VISIT_STARTED", version
    )  # an older update
    assert stale.status_code == 409
    view = case(live, ids["case_id"])
    assert view["state"] == "COMPLETED"  # never regressed
    assert len(view["work_reports"]) == 1
    # Technician completion never resolves the issue (invariant 8).
    assert get_issue(owner_ctx(live), ids["issue_id"])["status"] == "AWAITING_CUSTOMER"


def test_at19_completion_awaits_customer_still_faulty_reopen_history_intact(
    live: LiveServer,
) -> None:
    ids = confirmed_case(live)
    version = case(live, ids["case_id"])["version"]
    assert (
        event(
            live,
            "tech_assigned",
            ids["case_id"],
            "VISIT_COMPLETED",
            version,
            summary="Reset the unit.",
        ).status_code
        == 200
    )
    issue_id = ids["issue_id"]
    assert (
        confirm_resolution(owner_ctx(live), issue_id, "PERSISTS")["issue"]["status"]
        == "SERVICE_NEEDED"
    )
    assert (
        confirm_resolution(owner_ctx(live), issue_id, "UNSURE")["issue"]["status"]
        == "SERVICE_NEEDED"
    )
    resolved = confirm_resolution(owner_ctx(live), issue_id, "RESOLVED", close=True)
    assert (resolved["issue"]["status"], resolved["closed"]) == ("CLOSED", True)
    reopened = report_issue(
        owner_ctx(live),
        "qa-a-ac-bedroom",
        "Not cooling again",
        "NOT_COOLING",
        continue_issue_id=issue_id,
    )
    assert (reopened["outcome"], reopened["issue"]["status"]) == ("REOPENED", "OPEN")
    assert reopened["issue"]["reopen_reason"] == "Not cooling again"  # FR-17-AC2

    timeline = history.get_history(owner_ctx(live), "qa-a-ac-bedroom")
    actions = [e["action"] for e in timeline["entries"]]
    expected = [
        "ISSUE_REPORTED",
        "SERVICE_CONFIRMED",
        "STAFF_VISIT_COMPLETED",
        "ISSUE_CUSTOMER_SAYS_PERSISTS",
        "ISSUE_CUSTOMER_CONFIRMED_RESOLVED",
        "ISSUE_CUSTOMER_CLOSED",
        "ISSUE_RECURRED",
    ]
    positions = [actions.index(a) for a in expected]
    assert positions == sorted(positions)  # chronological, nothing erased
    completed = next(e for e in timeline["entries"] if e["action"] == "STAFF_VISIT_COMPLETED")
    assert (
        completed["actor_role"] == "technician"
    )  # technician reports labelled apart from customers
    assert timeline["appliance"] == "Bedroom AC"


def test_at35_no_show_stays_unresolved_and_raises_exception(live: LiveServer) -> None:
    ids = confirmed_case(live)
    version = case(live, ids["case_id"])["version"]
    assert (
        event(live, "tech_assigned", ids["case_id"], "NO_SHOW", version).status_code == 403
    )  # coordinator only
    no_show = event(live, "coordinator", ids["case_id"], "NO_SHOW", version)
    assert no_show.status_code == 200
    view = case(live, ids["case_id"])
    assert (view["state"], view["exception"]) == ("CONFIRMED", "NO_SHOW")
    assert (
        get_issue(owner_ctx(live), ids["issue_id"])["status"] == "SERVICE_PENDING"
    )  # not resolved
    manual = staff(live, "coordinator", "GET", "/manual").json()["items"]
    assert [(m["case_id"], m["reason"], m["status"]) for m in manual] == [
        (ids["case_id"], "NO_SHOW", "OPEN")
    ]


def test_p3_2_queue_masking_assignment_manual_review_safety_clear_verify_model(
    live: LiveServer,
) -> None:
    ids = confirmed_case(live)
    # Queues: the assigned technician sees the case, the other technician does not, and the
    # coordinator sees all.
    assert [
        c["case_id"] for c in staff(live, "tech_assigned", "GET", "/queue").json()["cases"]
    ] == [ids["case_id"]]
    assert staff(live, "tech_unassigned", "GET", "/queue").json()["cases"] == []
    assert ids["case_id"] in [
        c["case_id"] for c in staff(live, "coordinator", "GET", "/queue").json()["cases"]
    ]
    assert staff(live, "admin", "GET", "/queue").status_code == 403  # no automatic authority
    assert staff(live, None, "GET", "/queue").status_code == 401
    household = httpx.get(
        f"{live.base_url}/api/staff/queue",
        headers={"Authorization": f"Bearer {live.token('a_owner')}"},
        timeout=30,
    )
    assert household.status_code == 403

    # Masking: the assigned technician needs the address; the coordinator sees it masked.
    assert (
        case(live, ids["case_id"], "tech_assigned")["address"] == "Flat 4, Example Residency, Pune"
    )
    masked = case(live, ids["case_id"], "coordinator")
    assert masked["address"] != "Flat 4, Example Residency, Pune"
    assert "Example Residency" not in str(masked)
    assert masked["demo"] is True

    # Assignment moves the case between technicians' queues.
    technicians = staff(live, "coordinator", "GET", "/technicians").json()["technicians"]
    other = next(t["sub"] for t in technicians if t["username"] == "hk-tech-2")
    assert (
        staff(
            live,
            "coordinator",
            "POST",
            f"/cases/{ids['case_id']}/assign",
            json={"technician_sub": other},
        ).status_code
        == 200
    )
    assert [
        c["case_id"] for c in staff(live, "tech_unassigned", "GET", "/queue").json()["cases"]
    ] == [ids["case_id"]]

    # Manual review: list and resolve.
    event(live, "coordinator", ids["case_id"], "NO_SHOW", case(live, ids["case_id"])["version"])
    (item,) = staff(live, "coordinator", "GET", "/manual").json()["items"]
    resolved = staff(
        live,
        "coordinator",
        "POST",
        f"/manual/{item['item_id']}/resolve",
        json={"note": "Rebooked by phone."},
    )
    assert resolved.json()["status"] == "RESOLVED"

    # Safety: a flagged issue is listed and only a coordinator clears it, with evidence.
    report_warning_sign(owner_ctx(live), "there is smoke", ids["issue_id"])
    flagged = staff(live, "coordinator", "GET", "/safety").json()["items"]
    assert ids["issue_id"] in [f["ref_id"] for f in flagged]
    assert (
        staff(
            live,
            "tech_assigned",
            "POST",
            f"/issues/{ids['issue_id']}/clear-safety",
            json={"evidence": "x"},
        ).status_code
        == 403
    )
    cleared = staff(
        live,
        "coordinator",
        "POST",
        f"/issues/{ids['issue_id']}/clear-safety",
        json={"evidence": "Electrician checked the socket."},
    )
    assert cleared.status_code == 200
    assert get_issue(owner_ctx(live), ids["issue_id"])["safety_flag"] is False
    hold = report_warning_sign(owner_ctx(live), "I can see sparks")  # no issue: a household hold
    hold_id = live.table.get(keys.household_pk("qa-a"), keys.META)["safety_hold"]["hold_id"]
    assert hold["reason"] == "SPARKS"
    assert (
        staff(
            live,
            "coordinator",
            "POST",
            f"/safety-holds/{hold_id}/clear",
            json={"evidence": "Checked."},
        ).status_code
        == 200
    )
    assert live.table.get(keys.household_pk("qa-a"), keys.META).get("safety_hold") is None

    # Model verification: a catalog reviewer, a published model and its document.
    body = {"model": "FL-18i", "document_id": "frostline-fl-18i-manual-v2"}
    assert (
        staff(
            live, "coordinator", "POST", "/appliances/qa-a-ac-hall/verify-model", json=body
        ).status_code
        == 403
    )
    assert (
        staff(
            live,
            "catalog_reviewer",
            "POST",
            "/appliances/qa-a-ac-hall/verify-model",
            json={**body, "document_id": "wrong"},
        ).status_code
        == 400
    )
    verified = staff(
        live, "catalog_reviewer", "POST", "/appliances/qa-a-ac-hall/verify-model", json=body
    )
    assert verified.status_code == 200
    hall = live.table.get(keys.household_pk("qa-a"), keys.appliance_sk("qa-a-ac-hall"))
    assert (hall["fields"]["model"]["value"], hall["fields"]["model"]["status"]) == (
        "FL-18i",
        "VERIFIED",
    )
