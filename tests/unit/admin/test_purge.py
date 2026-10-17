"""Judge reset and test-household purge (FR-24; AT-25; plan G4-6)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.admin import purge
from app.domain import approvals, service
from app.domain.appliances import register_appliance
from app.domain.clock import SystemClock
from app.domain.context import OperationContext
from app.domain.errors import DomainError
from app.domain.household import ConsentDecision, ConsentPurpose, record_consent
from app.domain.issues import report_issue, report_warning_sign
from app.mcp_server.names import CUSTOMER_TOOLS, TRUSTED_TOOLS
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole
from app.security.membership import resolve_actor
from app.security.tokens import VerifiedToken
from app.store import keys
from app.store.table import Table, from_dynamo
from scripts import seed


def _scan(table: Table) -> list[dict[str, Any]]:
    items = table.client.scan(TableName=table.name)["Items"]
    return sorted((from_dynamo(i) for i in items), key=lambda i: (i["PK"], i["SK"]))


def _owned_by(items: list[dict[str, Any]], household_id: str) -> list[dict[str, Any]]:
    """Every item that belongs to the household, wherever it is stored."""
    pk = keys.household_pk(household_id)
    return [
        i
        for i in items
        if i["PK"] == pk
        or i.get("household_id") == household_id
        or i["SK"] == keys.user_household_sk(household_id)
        or i["SK"] == keys.fault_sk(household_id)
    ]


def _owner(household_id: str, key: str) -> Actor:
    return Actor(
        sub=f"local-{key}",
        kind=ActorKind.HOUSEHOLD,
        household_id=household_id,
        role=HouseholdRole.OWNER,
        grants=frozenset(Grant),
    )


def _ctx(table: Table, actor: Actor) -> OperationContext:
    return OperationContext(
        actor,
        table,
        SystemClock(),
        f"corr-{uuid.uuid4().hex[:8]}",
        turn_id=f"turn-{uuid.uuid4().hex[:8]}",
        session_id="session-purge",
        faults_enabled=True,
    )


def _slot_taken(table: Table, slot_id: str) -> int:
    return (table.get(keys.PROVIDER_PK, keys.slot_sk(slot_id)) or {}).get("taken", 0)


def _use_household(table: Table, household_id: str, key: str) -> str:
    """A judge's session: consent, an AC, a problem, a confirmed demo visit, a safety hold, a
    manual-review item and a fault. Returns the booked slot."""
    who = _owner(household_id, key)
    record_consent(_ctx(table, who), ConsentPurpose.STORAGE, ConsentDecision.GRANTED, "consent-v1")
    appliance_id = register_appliance(_ctx(table, who), "AC", "Bedroom AC")["appliance_id"]
    issue_id = report_issue(_ctx(table, who), appliance_id, "Not cooling", "NOT_COOLING")["issue"][
        "issue_id"
    ]
    request = service.draft_service_request(_ctx(table, who), issue_id)["request"]
    for field, value in (("address", "Flat 1, Sample Lane"), ("contact", "Landline 000 0000 0000")):
        request = service.record_service_details(
            _ctx(table, who), request["request_id"], field, value, request["version"]
        )
    slot = next(
        s["slot_id"]
        for s in service.list_slots(_ctx(table, who), request["request_id"], days=5)["slots"]
        if s["available"]
    )
    pending = approvals.prepare_action(_ctx(table, who), "SUBMIT", request["request_id"], slot)
    approval = approvals.confirm_action(_ctx(table, who), pending["pending_ref"], channel="text")
    assert approvals.execute_action(_ctx(table, who), approval["approval_id"])["outcome"] == (
        "CONFIRMED"
    )
    report_warning_sign(_ctx(table, who), "I can see sparks")  # a household safety hold
    table.put(
        {
            "PK": keys.OPS_PK,
            "SK": keys.manual_sk("2026-10-17T00:00:00Z", f"m-{household_id}"),
            "kind": "MANUAL",
            "item_id": f"m-{household_id}",
            "case_id": request["request_id"],
            "household_id": household_id,
            "reason": "NO_SHOW",
            "status": "OPEN",
            "version": 1,
        }
    )
    table.put({"PK": keys.PROVIDER_PK, "SK": keys.fault_sk(household_id), "fault": "REJECT"})
    return slot


def test_reset_restores_seed_releases_slots_keeps_members(table: Table) -> None:
    seed.seed_local(table)
    seeded = _scan(table)
    seeded_judge = _owned_by(seeded, "judge-1")
    slot = _use_household(table, "judge-1", "j1_owner")
    other = _use_household(table, "judge-2", "j2_owner")
    before_others = [i for i in _scan(table) if i not in _owned_by(_scan(table), "judge-1")]
    assert _slot_taken(table, slot) >= 1

    report = purge.reset_household(table, SystemClock(), "judge-1", actor_label="owner")

    after = _scan(table)
    judge_now = [i for i in _owned_by(after, "judge-1") if i["kind"] != "EVENT"]
    assert judge_now == [i for i in seeded_judge if i["kind"] != "EVENT"]  # back to the seed
    resets = [i for i in _owned_by(after, "judge-1") if i["kind"] == "EVENT"]
    assert [e["action"] for e in resets] == ["HOUSEHOLD_RESET"]  # the reset itself is recorded
    assert report.released_places == 1
    assert _slot_taken(table, slot) == (1 if slot == other else 0)
    untouched = [i for i in after if i not in _owned_by(after, "judge-1")]
    slot_items = {keys.slot_sk(slot)}
    assert [i for i in untouched if i["SK"] not in slot_items and i["PK"] != keys.OPS_PK] == [
        i for i in before_others if i["SK"] not in slot_items and i["PK"] != keys.OPS_PK
    ]  # judge-2 and everything else unchanged
    # The judge can carry on at once with the same login.
    owner = resolve_actor(table, VerifiedToken("local-j1_owner", "web", frozenset(), frozenset()))
    assert owner.household_id == "judge-1"


def test_reset_only_for_resettable_households(table: Table) -> None:
    seed.seed_local(table)
    with pytest.raises(DomainError) as refused:
        purge.reset_household(table, SystemClock(), "qa-a", actor_label="owner")
    assert refused.value.reason == "NOT_RESETTABLE"


def test_at25_purge_removes_records_refs_links_and_access_other_household_untouched(
    table: Table,
) -> None:
    seed.seed_local(table)
    purged_slot = _use_household(table, "judge-2", "j2_owner")
    slot = _use_household(table, "judge-3", "j3_owner")
    before = _scan(table)
    others_before = [i for i in before if i not in _owned_by(before, "judge-2")]

    report = purge.purge_household(table, SystemClock(), "judge-2", actor_label="admin:cli")

    after = _scan(table)
    assert _owned_by(after, "judge-2") == []  # records, refs, links, manual items, faults
    assert report.signed_out == ["hk-judge-2"]  # for Cognito global sign-out (FR-24-AC1)
    with pytest.raises(DomainError):  # access is revoked
        resolve_actor(table, VerifiedToken("local-j2_owner", "web", frozenset(), frozenset()))
    audit = [i for i in after if i["PK"] == keys.OPS_PK and i.get("kind") == "AUDIT"]
    # Audited outside the purged partition (BRD §11.4).
    assert [(a["action"], a["target_household"]) for a in audit] == [
        ("HOUSEHOLD_PURGED", "judge-2")
    ]
    assert report.released_places == 1  # judge-2's booking gave its place back
    assert _slot_taken(table, purged_slot) == (1 if purged_slot == slot else 0)
    ignore = {keys.slot_sk(slot), keys.slot_sk(purged_slot)}
    assert [i for i in after if i.get("kind") != "AUDIT" and i["SK"] not in ignore] == [
        i for i in others_before if i["SK"] not in ignore
    ]  # judge-3 and everyone else unchanged


def test_at25_no_tool_or_route_can_delete() -> None:
    """FR-24-AC2: no conversation path can delete anything, so an unverified voice request
    cannot delete another household."""
    for name in (*CUSTOMER_TOOLS, *TRUSTED_TOOLS):
        assert not any(word in name for word in ("delete", "purge", "reset", "remove")), name
    from app.config import Settings
    from app.main import create_app

    app = create_app(
        Settings.from_env({"ENV": "local", "TABLE_NAME": "t", "DYNAMODB_ENDPOINT_URL": "http://x"}),
        start_sweep=False,
    )
    paths = app.openapi()["paths"]  # every route, including routers FastAPI includes lazily
    methods = {method for operations in paths.values() for method in operations}
    assert "delete" not in methods
    resets = [path for path in paths if "reset" in path or "purge" in path]
    assert resets == ["/api/household/reset"]  # the caller's own household, owner only


def _book(table: Table, household_id: str, key: str, window: str = "AM") -> dict[str, Any]:
    """A confirmed demo booking for the household; returns the request item."""
    who = _owner(household_id, key)
    record_consent(_ctx(table, who), ConsentPurpose.STORAGE, ConsentDecision.GRANTED, "consent-v1")
    appliance_id = register_appliance(_ctx(table, who), "AC", f"AC {uuid.uuid4().hex[:4]}")[
        "appliance_id"
    ]
    issue_id = report_issue(_ctx(table, who), appliance_id, "Not cooling", "NOT_COOLING")["issue"][
        "issue_id"
    ]
    request = service.draft_service_request(_ctx(table, who), issue_id)["request"]
    for field, value in (("address", "Flat 1, Sample Lane"), ("contact", "Landline 000 0000 0000")):
        request = service.record_service_details(
            _ctx(table, who), request["request_id"], field, value, request["version"]
        )
    slot = next(
        s["slot_id"]
        for s in service.list_slots(_ctx(table, who), request["request_id"], days=2)["slots"]
        if s["available"] and s["window"] == window
    )
    pending = approvals.prepare_action(_ctx(table, who), "SUBMIT", request["request_id"], slot)
    approval = approvals.confirm_action(_ctx(table, who), pending["pending_ref"], channel="text")
    approvals.execute_action(_ctx(table, who), approval["approval_id"])
    return table.get(keys.household_pk(household_id), keys.request_sk(request["request_id"]))


def test_i1_reset_never_gives_back_a_place_twice(table: Table) -> None:
    seed.seed_local(table)
    mine = _book(table, "judge-1", "j1_owner")
    theirs = _book(table, "judge-2", "j2_owner")
    assert mine["slot_id"] == theirs["slot_id"]  # the AM window holds two
    slot = mine["slot_id"]
    assert _slot_taken(table, slot) == 2

    # A cancellation whose reply was lost: the provider already gave the place back.
    who = _owner("judge-1", "j1_owner")
    table.put(
        {
            "PK": keys.PROVIDER_PK,
            "SK": keys.fault_sk("judge-1"),
            "fault": "CANCEL_TIMEOUT",
            "remaining": 1,
        }
    )
    pending = approvals.prepare_action(_ctx(table, who), "CANCEL", mine["request_id"])
    approval = approvals.confirm_action(_ctx(table, who), pending["pending_ref"], channel="text")
    assert approvals.execute_action(_ctx(table, who), approval["approval_id"])["outcome"] == (
        "CANCEL_PENDING"
    )
    assert _slot_taken(table, slot) == 1

    purge.reset_household(table, SystemClock(), "judge-1", actor_label="owner")
    assert _slot_taken(table, slot) == 1  # judge-2's place is untouched


def test_i1_two_resets_racing_release_each_place_once(table: Table) -> None:
    seed.seed_local(table)
    mine = _book(table, "judge-1", "j1_owner")
    _book(table, "judge-2", "j2_owner")
    items = table.query(keys.household_pk("judge-1"))  # both resets read the same records
    first = purge._release_places(table, SystemClock(), items)
    second = purge._release_places(table, SystemClock(), items)
    assert (first, second) == (1, 0)
    assert _slot_taken(table, mine["slot_id"]) == 1


def test_i2_reset_keeps_the_daily_turn_count(table: Table) -> None:
    seed.seed_local(table)
    usage = {"PK": keys.household_pk("judge-1"), "SK": "USAGE#2026-10-17", "turns": 299}
    table.put(usage)
    purge.reset_household(table, SystemClock(), "judge-1", actor_label="owner")
    assert table.get(usage["PK"], usage["SK"]) == usage  # resetting never buys more turns


def test_i3_a_failed_reset_can_be_run_again(table: Table, monkeypatch: pytest.MonkeyPatch) -> None:
    seed.seed_local(table)
    _use_household(table, "judge-1", "j1_owner")

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the task stopped mid-reset")

    monkeypatch.setattr(purge, "household_items", broken)
    with pytest.raises(RuntimeError):
        purge.reset_household(table, SystemClock(), "judge-1", actor_label="owner")
    assert table.get(keys.household_pk("judge-1"), keys.META) is not None  # still resettable
    owner = resolve_actor(table, VerifiedToken("local-j1_owner", "web", frozenset(), frozenset()))
    assert owner.household_id == "judge-1"  # and the judge is still signed in to it
    monkeypatch.undo()
    purge.reset_household(table, SystemClock(), "judge-1", actor_label="owner")
    assert table.query(keys.household_pk("judge-1"), keys.APPLIANCE_PREFIX) == []


def test_i1_reset_gives_back_a_future_place_after_the_visit_was_marked_done(table: Table) -> None:
    from app.domain import staff
    from app.security.actor import StaffGroup

    seed.seed_local(table)
    booked = _book(table, "judge-1", "j1_owner", window="PM")  # one place per afternoon
    technician = Actor(
        sub="local-tech_assigned", kind=ActorKind.STAFF, groups=frozenset({StaffGroup.TECHNICIAN})
    )
    staff.post_event(
        _ctx(table, technician),
        booked["request_id"],
        "e-done",
        "VISIT_COMPLETED",
        booked["version"],
        "Cleaned the filter.",
    )
    assert _slot_taken(table, booked["slot_id"]) == 1
    purge.reset_household(table, SystemClock(), "judge-1", actor_label="owner")
    assert _slot_taken(table, booked["slot_id"]) == 0  # the next judge can book that afternoon
