"""Staff and service-desk operations (TDD §4.10; FR-03, FR-16; plan P3-2).

Staff are not household members, so they never pass a household ID: every route takes an opaque
record reference and the household is resolved from it (G3-1). Each call checks the staff role
and, for technicians, the assignment. Events need an `event_id` (a repeat returns the original
result) and an `expected_version` (an older update is refused, so state never regresses).
Technician completion moves the issue to AWAITING_CUSTOMER; it never resolves it (invariant 8).
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

from app.catalog.loader import load_catalog, model_key
from app.catalog.overlay import effective_status
from app.domain import booking, issues, refs, requests
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.ids import new_id
from app.domain.state import IssueEvent, IssueStatus, RequestEvent, RequestStatus
from app.security.actor import StaffGroup
from app.security.authz import StaffAction, authorize_staff
from app.store import keys
from app.store.ops import canonical_json

VISIT_EVENTS = frozenset({"VISIT_STARTED", "WORK_NOTE", "VISIT_COMPLETED"})
COORDINATION_EVENTS = frozenset({"NO_SHOW", "PROVIDER_CONFIRMED", "PROVIDER_REJECTED"})


def _scoped(
    ctx: OperationContext, opaque_id: str, kind: str
) -> tuple[OperationContext, dict[str, Any]]:
    ref = refs.resolve(ctx.table, opaque_id, kind)
    return dataclasses.replace(ctx, scope_household_id=ref["household_id"]), ref


def _mask(value: str | None, keep: int) -> str | None:
    if not value:
        return None
    return f"{value[:keep]}…" if keep else f"••••{value[-2:]}"


def _summary(ctx: OperationContext, sr: dict[str, Any]) -> dict[str, Any]:
    issue = issues.load(ctx, sr["issue_id"])
    appointment = requests.appointment_view(
        requests.appointment(ctx, sr["request_id"], sr.get("appointment_id"))
    )
    return {
        "case_id": sr["request_id"],
        "state": sr["state"],
        "pending": sr["state"] in requests.PENDING_STATES,
        "issue_summary": sr["snapshot"]["summary"],
        "appliance": sr["snapshot"].get("appliance"),
        "safety_flag": issue["safety_flag"],
        "appointment": appointment,
        "fee": sr["fee"],
        "exception": sr.get("exception"),
        "demo": True,
    }


def queue(ctx: OperationContext) -> dict[str, Any]:
    authorize_staff(ctx.actor, StaffAction.QUEUE_VIEW)
    if StaffGroup.COORDINATOR in ctx.actor.groups:
        cases = []
        for ref in ctx.table.query_index("GSI1", "CASE"):
            scoped = dataclasses.replace(ctx, scope_household_id=ref["household_id"])
            sr = requests.load(scoped, ref["ref_id"])
            if sr["state"] != RequestStatus.DRAFT.value:
                cases.append(_summary(scoped, sr))
        return {"cases": cases}
    cases = []
    for sr in ctx.table.query_index("GSI1", f"ASSIGNEE#{ctx.actor.sub}"):
        scoped = dataclasses.replace(ctx, scope_household_id=sr["household_id"])
        cases.append(_summary(scoped, sr))
    return {"cases": cases}


def case_view(ctx: OperationContext, case_id: str) -> dict[str, Any]:
    scoped, _ = _scoped(ctx, case_id, "CASE")
    sr = requests.load(scoped, case_id)
    authorize_staff(ctx.actor, StaffAction.CASE_VIEW, sr.get("assignee_sub"))
    # Personal fields only for the role that needs them: the assigned technician (BRD §11.3).
    full = sr.get("assignee_sub") == ctx.actor.sub
    address = (sr.get("address") or {}).get("value")
    contact = (sr.get("contact") or {}).get("value")
    pk = keys.household_pk(scoped.household_id)
    work = scoped.table.query(pk, f"{keys.REQUEST_PREFIX}{case_id}#WORK#")
    issue = issues.load(scoped, sr["issue_id"])
    return {
        **_summary(scoped, sr),
        "version": sr["version"],
        "checks": sr["snapshot"].get("checks", []),
        "issue_status": issue["status"],
        "address": address if full else _mask(address, 4),
        "contact": contact if full else _mask(contact, 0),
        "assignee_sub": sr.get("assignee_sub"),
        "work_reports": [
            {k: w[k] for k in ("work_id", "summary", "at", "actor_role")} for w in work
        ],
    }


def post_event(
    ctx: OperationContext,
    case_id: str,
    event_id: str,
    kind: str,
    expected_version: int,
    summary: str | None = None,
) -> dict[str, Any]:
    scoped, _ = _scoped(ctx, case_id, "CASE")
    sr = requests.load(scoped, case_id)
    if kind in VISIT_EVENTS:
        authorize_staff(ctx.actor, StaffAction.VISIT_EVENT, sr.get("assignee_sub"))
    elif kind in COORDINATION_EVENTS:
        authorize_staff(ctx.actor, StaffAction.COORDINATION_EVENT)
    else:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_EVENT")
    pk = keys.household_pk(scoped.household_id)
    fingerprint = _fingerprint(kind, expected_version, summary)
    seen = scoped.table.get(pk, keys.staff_event_sk(case_id, event_id))
    if seen is not None:
        return _replay(seen, fingerprint)  # a duplicate delivery: one event, the original result
    if sr["version"] != expected_version:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_EVENT")  # never regress state
    if kind in ("WORK_NOTE", "VISIT_COMPLETED") and not (summary or "").strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "WORK_SUMMARY_REQUIRED")
    if kind in _REQUIRED_STATE and sr["state"] != _REQUIRED_STATE[kind]:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNDEFINED_TRANSITION")

    def remember(state: str) -> dict[str, Any]:
        """The de-duplication record, written in the same transaction as the event (C1)."""
        result = {"case_id": case_id, "state": state, "version": sr["version"] + 1, "event": kind}
        return scoped.table.put_new_op(
            {
                "PK": pk,
                "SK": keys.staff_event_sk(case_id, event_id),
                "kind": "STAFF_EVENT",
                "fingerprint": fingerprint,
                "result": result,
            }
        )

    if kind in ("PROVIDER_CONFIRMED", "PROVIDER_REJECTED"):
        # The provider's answer to an acknowledged booking. Its own record is settled first (a
        # rejection gives the place back), then the request, in one transaction with this event.
        confirmed = kind == "PROVIDER_CONFIRMED"
        booking.provider(scoped).settle(sr["op_key"], "CONFIRMED" if confirmed else "REJECTED")
        try:
            if confirmed:
                outcome = booking.confirm_booking(
                    scoped,
                    sr,
                    sr.get("provider_ref") or "",
                    sr["slot_id"],
                    extra_ops=(remember(RequestStatus.CONFIRMED.value),),
                )["request"]
            else:
                outcome = booking._simple_transition(
                    scoped,
                    sr,
                    "SERVICE_REJECTED",
                    RequestEvent.PROVIDER_REJECTED,
                    extra_ops=(remember(RequestStatus.REJECTED.value),),
                )
        except DomainError as exc:
            seen = scoped.table.get(pk, keys.staff_event_sk(case_id, event_id))
            if seen is not None:
                return _replay(seen, fingerprint)
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_EVENT") from exc
        return {
            "case_id": case_id,
            "state": outcome["state"],
            "version": outcome["version"],
            "event": kind,
        }

    now = iso_utc(scoped.clock.now())
    updated = dict(sr)
    operations: list[dict[str, Any]] = []
    if kind == "VISIT_STARTED":
        updated = booking._advance(sr, RequestEvent.VISIT_STARTED, now=now)
    elif kind == "WORK_NOTE":
        updated = requests.indexed({**sr, "updated_at": now, "version": sr["version"] + 1})
    elif kind == "VISIT_COMPLETED":
        updated = booking._advance(sr, RequestEvent.WORK_COMPLETED, now=now)
        appointment = requests.appointment(scoped, case_id, sr.get("appointment_id"))
        if appointment is not None:
            operations += [
                scoped.table.put_versioned_op(
                    {**appointment, "status": "COMPLETED", "version": appointment["version"] + 1},
                    appointment["version"],
                ),
                scoped.table.delete_op(pk, keys.active_sk(case_id)),
            ]
        operations += booking._issue_op(  # awaits the customer; never resolves (invariant 8)
            scoped, sr["issue_id"], IssueEvent.VISIT_COMPLETED, {IssueStatus.SERVICE_PENDING}
        )
    elif kind == "NO_SHOW":
        # A coordinator exception: the request stays CONFIRMED and the issue unresolved (AT-35).
        updated = requests.indexed(
            {**sr, "exception": "NO_SHOW", "updated_at": now, "version": sr["version"] + 1}
        )
        item_id = new_id()
        operations.append(
            scoped.table.put_new_op(
                {
                    "PK": keys.OPS_PK,
                    "SK": keys.manual_sk(now, item_id),
                    "kind": "MANUAL",
                    "item_id": item_id,
                    "case_id": case_id,
                    "household_id": scoped.household_id,
                    "reason": "NO_SHOW",
                    "status": "OPEN",
                    "at": now,
                    "version": 1,
                }
            )
        )
    if kind in ("WORK_NOTE", "VISIT_COMPLETED"):
        work_id = new_id()
        operations.append(
            scoped.table.put_new_op(
                {
                    "PK": pk,
                    "SK": keys.work_sk(case_id, work_id),
                    "kind": "WORK",
                    "work_id": work_id,
                    "summary": (summary or "").strip()[:4000],
                    "actor_sub": ctx.actor.sub,
                    "actor_role": ctx.actor.role_label,
                    "at": now,
                }
            )
        )
    result = {
        "case_id": case_id,
        "state": updated["state"],
        "version": updated["version"],
        "event": kind,
    }
    operations = [
        scoped.table.put_versioned_op(updated, sr["version"]),
        scoped.table.put_op(requests.case_ref(updated)),
        remember(updated["state"]),
        scoped.table.put_new_op(
            event_item(
                scoped,
                action=f"STAFF_{kind}",
                record_sk=keys.request_sk(case_id),
                appliance_id=sr["appliance_id"],
                prior_version=sr["version"],
                new_version=updated["version"],
                provenance="STAFF",
            )
        ),
        *operations,
    ]
    try:
        scoped.table.transact(operations)
    except ConflictError as exc:
        seen = scoped.table.get(pk, keys.staff_event_sk(case_id, event_id))
        if seen is not None:
            return _replay(seen, fingerprint)
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_EVENT") from exc
    return result


_REQUIRED_STATE = {
    "PROVIDER_CONFIRMED": RequestStatus.REQUESTED.value,
    "PROVIDER_REJECTED": RequestStatus.REQUESTED.value,  # a timed-out request may be confirmed
    "NO_SHOW": RequestStatus.CONFIRMED.value,  # only a fixed visit can be missed (N3)
}


def _fingerprint(kind: str, expected_version: int, summary: str | None) -> str:
    payload = {"kind": kind, "expected_version": expected_version, "summary": summary}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def _replay(seen: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    """The same event again gets its original result; a different event under a used ID is a
    conflict, never silently answered with another event's result (invariant 5)."""
    if seen.get("fingerprint") != fingerprint:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "EVENT_ID_REUSED")
    return seen["result"]


def technicians(ctx: OperationContext) -> dict[str, Any]:
    authorize_staff(ctx.actor, StaffAction.CASE_ASSIGN)
    staff = ctx.table.query_index("GSI1", "STAFF", forward=True)
    return {
        "technicians": [
            {"sub": s["sub"], "username": s["username"]}
            for s in staff
            if StaffGroup.TECHNICIAN.value in s.get("groups", [])
        ]
    }


def assign(ctx: OperationContext, case_id: str, technician_sub: str) -> dict[str, Any]:
    authorize_staff(ctx.actor, StaffAction.CASE_ASSIGN)
    member = ctx.table.get(keys.staff_pk(technician_sub), keys.META)
    if member is None or StaffGroup.TECHNICIAN.value not in member.get("groups", []):
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_TECHNICIAN")
    scoped, _ = _scoped(ctx, case_id, "CASE")
    sr = requests.load(scoped, case_id)
    now = iso_utc(scoped.clock.now())
    updated = requests.indexed(
        {**sr, "assignee_sub": technician_sub, "updated_at": now, "version": sr["version"] + 1}
    )
    try:
        scoped.table.transact(
            [
                scoped.table.put_versioned_op(updated, sr["version"]),
                scoped.table.put_op(requests.case_ref(updated)),
                scoped.table.put_new_op(
                    event_item(
                        scoped,
                        action="STAFF_ASSIGNED",
                        record_sk=keys.request_sk(case_id),
                        appliance_id=sr["appliance_id"],
                        prior_version=sr["version"],
                        new_version=updated["version"],
                        provenance="STAFF",
                    )
                ),
            ]
        )
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return {"case_id": case_id, "assignee_sub": technician_sub, "version": updated["version"]}


def manual_items(ctx: OperationContext) -> dict[str, Any]:
    authorize_staff(ctx.actor, StaffAction.MANUAL_REVIEW)
    items = ctx.table.query(keys.OPS_PK, "MANUAL#")
    fields = ("item_id", "case_id", "reason", "status", "at", "note")
    return {"items": [{k: i.get(k) for k in fields} for i in items]}


def resolve_manual(ctx: OperationContext, item_id: str, note: str) -> dict[str, Any]:
    authorize_staff(ctx.actor, StaffAction.MANUAL_REVIEW)
    item = next(
        (i for i in ctx.table.query(keys.OPS_PK, "MANUAL#") if i["item_id"] == item_id), None
    )
    if item is None:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    if item["status"] == "RESOLVED":
        return {"item_id": item_id, "status": "RESOLVED"}
    updated = {
        **item,
        "status": "RESOLVED",
        "note": note.strip()[:1000],
        "resolved_by": ctx.actor.sub,
        "resolved_at": iso_utc(ctx.clock.now()),
        "version": item["version"] + 1,
    }
    try:
        ctx.table.put_versioned(updated, item["version"])
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return {"item_id": item_id, "status": "RESOLVED"}


def safety_items(ctx: OperationContext) -> dict[str, Any]:
    authorize_staff(ctx.actor, StaffAction.SAFETY_CLEAR)
    return {
        "items": [
            {"ref_id": r["ref_id"], "kind": r["ref_kind"], "since": r.get("GSI1SK")}
            for r in ctx.table.query_index("GSI1", "SAFETY")
        ]
    }


def _require_evidence(evidence: str) -> str:
    text = evidence.strip()
    if not text:
        raise DomainError(ErrorCode.INVALID_INPUT, "EVIDENCE_REQUIRED")
    return text[:1000]


def clear_issue_safety(ctx: OperationContext, issue_id: str, evidence: str) -> dict[str, Any]:
    """A reviewed clearance with evidence (BRD §7.1); conversation can never clear a flag."""
    authorize_staff(ctx.actor, StaffAction.SAFETY_CLEAR)
    text = _require_evidence(evidence)
    scoped, _ = _scoped(ctx, issue_id, "ISSUE")
    item = issues.load(scoped, issue_id)
    now = iso_utc(scoped.clock.now())
    cleared = {
        **item,
        "safety_flag": False,
        "safety_reason": None,
        "safety_cleared": {"by": ctx.actor.sub, "evidence": text, "at": now},
        "updated_at": now,
        "version": item["version"] + 1,
    }
    try:
        scoped.table.transact(
            [
                scoped.table.put_versioned_op(cleared, item["version"]),
                scoped.table.put_op(issues.issue_ref(scoped, cleared)),
                scoped.table.put_new_op(
                    event_item(
                        scoped,
                        action="STAFF_SAFETY_CLEARED",
                        record_sk=item["SK"],
                        appliance_id=item["appliance_id"],
                        prior_version=item["version"],
                        new_version=cleared["version"],
                        provenance="STAFF",
                    )
                ),
            ]
        )
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return {"issue_id": issue_id, "safety_flag": False}


def clear_safety_hold(ctx: OperationContext, hold_id: str, evidence: str) -> dict[str, Any]:
    authorize_staff(ctx.actor, StaffAction.SAFETY_CLEAR)
    text = _require_evidence(evidence)
    scoped, ref = _scoped(ctx, hold_id, "HOLD")
    pk = keys.household_pk(scoped.household_id)
    meta = scoped.table.get(pk, keys.META)
    if meta is None or (meta.get("safety_hold") or {}).get("hold_id") != hold_id:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    now = iso_utc(scoped.clock.now())
    updated = {
        **meta,
        "safety_hold": None,
        "safety_hold_cleared": {
            "hold_id": hold_id,
            "by": ctx.actor.sub,
            "evidence": text,
            "at": now,
        },
        "version": meta["version"] + 1,
    }
    unindexed = {k: v for k, v in ref.items() if k not in ("GSI1PK", "GSI1SK")}
    try:
        scoped.table.transact(
            [
                scoped.table.put_versioned_op(updated, meta["version"]),
                scoped.table.put_op(unindexed),
                scoped.table.put_new_op(
                    event_item(
                        scoped,
                        action="STAFF_SAFETY_HOLD_CLEARED",
                        record_sk=keys.META,
                        appliance_id=None,
                        prior_version=meta["version"],
                        new_version=updated["version"],
                        provenance="STAFF",
                    )
                ),
            ]
        )
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return {"hold_id": hold_id, "cleared": True}


def verify_model(
    ctx: OperationContext, appliance_id: str, model: str, document_id: str
) -> dict[str, Any]:
    """FR-03: a reviewer verifies an exact model against a published catalog document. This
    resolves earlier user claims about the model; they stay visible in `resolved_conflicts`."""
    authorize_staff(ctx.actor, StaffAction.MODEL_VERIFY)
    scoped, _ = _scoped(ctx, appliance_id, "APPLIANCE")
    published = [
        item
        for item in load_catalog().items_for_model(model)
        if effective_status(scoped.table, item) == "PUBLISHED"
    ]
    if not published:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_IN_CATALOG")
    if document_id not in {item.document_id for item in published}:
        raise DomainError(ErrorCode.INVALID_INPUT, "DOCUMENT_MISMATCH")
    pk = keys.household_pk(scoped.household_id)
    appliance = scoped.table.get(pk, keys.appliance_sk(appliance_id))
    if appliance is None:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    now = iso_utc(scoped.clock.now())
    previous = appliance["fields"]["model"]
    earlier = [c for c in appliance.get("conflicts", []) if c.get("field") == "model"]
    if previous.get("value") and model_key(previous["value"]) != model_key(model):
        earlier.append({"field": "model", **previous})  # the mismatch stays visible
    verified = {
        "value": published[0].model,
        "status": "VERIFIED",
        "provenance": {
            "source": "REVIEWER",
            "reviewer_sub": ctx.actor.sub,
            "document_id": document_id,
            "at": now,
        },
    }
    updated = {
        **appliance,
        "fields": {**appliance["fields"], "model": verified},
        "conflicts": [c for c in appliance.get("conflicts", []) if c.get("field") != "model"],
        "resolved_conflicts": [*appliance.get("resolved_conflicts", []), *earlier],
        "updated_at": now,
        "version": appliance["version"] + 1,
    }
    try:
        scoped.table.transact(
            [
                scoped.table.put_versioned_op(updated, appliance["version"]),
                scoped.table.put_new_op(
                    event_item(
                        scoped,
                        action="STAFF_MODEL_VERIFIED",
                        record_sk=appliance["SK"],
                        appliance_id=appliance_id,
                        prior_version=appliance["version"],
                        new_version=updated["version"],
                        provenance="STAFF",
                    )
                ),
            ]
        )
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return {"appliance_id": appliance_id, "model": verified["value"], "status": "VERIFIED"}
