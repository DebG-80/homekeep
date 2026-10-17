"""Issues: capture without accidental duplicates, and transitions through the BRD §7.1 map.

The original wording is kept alongside a short summary (FR-05). If the appliance already has an
active issue, the caller must say whether this continues it or is a confirmed, distinct problem.
The safety flag is orthogonal to status: once set it stays, whatever the status does, and only
staff can clear it (Slice 3).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.catalog.hazards import classify
from app.domain import appliances, mutations, refs
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.household import require_storage_consent
from app.domain.ids import new_id
from app.domain.state import ACTIVE_ISSUE_STATUSES, IssueEvent, IssueStatus, next_issue_status
from app.security.actor import Grant, HouseholdRole
from app.security.authz import Action, authorize
from app.store import keys

SYMPTOM_TEXT_MAX = 2000  # BRD §8.2


class SymptomCategory(StrEnum):
    NOT_COOLING = "NOT_COOLING"
    WEAK_AIRFLOW = "WEAK_AIRFLOW"
    WATER_LEAK = "WATER_LEAK"
    NOISE = "NOISE"
    ERROR_CODE = "ERROR_CODE"
    NOT_TURNING_ON = "NOT_TURNING_ON"
    REMOTE_ISSUE = "REMOTE_ISSUE"
    OTHER = "OTHER"


# Events a household member may fire. Service events (APPOINTMENT_CONFIRMED, VISIT_COMPLETED,
# BOOKING_ENDED) come only from the booking and staff services in Slice 3.
CUSTOMER_EVENTS = frozenset(
    {
        IssueEvent.INTAKE_STARTED,
        IssueEvent.SERVICE_REQUESTED,
        IssueEvent.HAZARD_REPORTED,
        IssueEvent.CUSTOMER_CONFIRMED_RESOLVED,
        IssueEvent.CUSTOMER_SAYS_PERSISTS,
        IssueEvent.CUSTOMER_CLOSED,
        IssueEvent.RECURRED,
    }
)


def view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_id": item["issue_id"],
        "appliance_id": item["appliance_id"],
        "original_wording": item["original_wording"],
        "summary": item["summary"],
        "symptom_category": item["symptom_category"],
        "status": item["status"],
        "safety_flag": item["safety_flag"],
        "safety_reason": item.get("safety_reason"),
        "reopen_reason": item.get("reopen_reason"),
        "version": item["version"],
    }


def load(ctx: OperationContext, issue_id: str) -> dict[str, Any]:
    item = ctx.table.get(keys.household_pk(ctx.household_id), keys.issue_sk(issue_id))
    if item is None or item.get("kind") != "ISSUE":
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    return item


def active_issues(ctx: OperationContext, appliance_id: str) -> list[dict[str, Any]]:
    items = ctx.table.query(keys.household_pk(ctx.household_id), keys.ISSUE_PREFIX)
    return [
        item
        for item in items
        if item.get("kind") == "ISSUE"
        and item["appliance_id"] == appliance_id
        and item["status"] in ACTIVE_ISSUE_STATUSES
    ]


def get_issue(ctx: OperationContext, issue_id: str) -> dict[str, Any]:
    authorize(ctx.actor, Action.ISSUE_READ, ctx.household_id)
    item = load(ctx, issue_id)
    observations = ctx.table.query(
        keys.household_pk(ctx.household_id), keys.observation_prefix(issue_id)
    )
    return {
        **view(item),
        "observations": [
            {k: o[k] for k in ("field", "value", "status", "version")} for o in observations
        ],
        "steps": [
            {k: s[k] for k in ("step_id", "result", "catalog_item", "catalog_version", "at")}
            for s in ctx.table.query(
                keys.household_pk(ctx.household_id), keys.step_prefix(issue_id)
            )
        ],
    }


def report_issue(
    ctx: OperationContext,
    appliance_id: str,
    symptom_text: str,
    symptom_category: str,
    summary: str | None = None,
    continue_issue_id: str | None = None,
    confirmed_distinct: bool = False,
) -> dict[str, Any]:
    authorize(ctx.actor, Action.ISSUE_WRITE, ctx.household_id)
    wording = symptom_text.strip()
    if not wording:
        raise DomainError(ErrorCode.INVALID_INPUT, "SYMPTOM_REQUIRED")
    if len(wording) > SYMPTOM_TEXT_MAX:
        raise DomainError(ErrorCode.INVALID_INPUT, "SYMPTOM_TOO_LONG")
    try:
        category = SymptomCategory(symptom_category)
    except ValueError:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_SYMPTOM_CATEGORY") from None
    args = {
        "appliance_id": appliance_id,
        "symptom_text": wording,
        "symptom_category": category.value,
        "summary": summary,
        "continue_issue_id": continue_issue_id,
        "confirmed_distinct": confirmed_distinct,
    }

    # The replay check comes first: after the original call, its own issue is active.
    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        appliances.load(ctx, appliance_id)

        active = active_issues(ctx, appliance_id)
        if continue_issue_id is not None:
            chosen = [i for i in active if i["issue_id"] == continue_issue_id]
            if not chosen:
                previous = ctx.table.get(
                    keys.household_pk(ctx.household_id), keys.issue_sk(continue_issue_id)
                )
                if (
                    previous
                    and previous.get("kind") == "ISSUE"
                    and previous["appliance_id"] == appliance_id
                    and previous["status"] == IssueStatus.CLOSED.value
                ):
                    # The same problem came back: reopen it; its history is kept (G3-7).
                    reopened = apply_issue_event(
                        ctx,
                        continue_issue_id,
                        IssueEvent.RECURRED,
                        previous["version"],
                        reopen_reason=wording,
                    )
                    return {"outcome": "REOPENED", "issue": reopened}
                raise DomainError(ErrorCode.INVALID_INPUT, "NOT_AN_ACTIVE_ISSUE")
            return {"outcome": "CONTINUED", "issue": view(chosen[0])}
        if active and not confirmed_distinct:
            # FR-05: ask whether this is the existing case before creating another. Nothing written.
            return {"outcome": "NEEDS_CHOICE", "active_issues": [view(i) for i in active]}

        issue_id = new_id()
        now = iso_utc(ctx.clock.now())
        hold = household_safety_hold(ctx)
        item = {
            "PK": keys.household_pk(ctx.household_id),
            "SK": keys.issue_sk(issue_id),
            "kind": "ISSUE",
            "issue_id": issue_id,
            "appliance_id": appliance_id,
            "original_wording": wording,
            "summary": summary or wording,
            "symptom_category": category.value,
            "status": IssueStatus.OPEN.value,
            "safety_flag": hold is not None,  # born under a household safety hold
            "safety_reason": hold["reason"] if hold else None,
            "reporting_actor": ctx.actor.sub,
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_new_op(item),
            ctx.table.put_new_op(
                refs.ref_item(
                    issue_id,
                    ctx.household_id,
                    "ISSUE",
                    item["SK"],
                    index="SAFETY" if item["safety_flag"] else None,
                    sort=now,
                )
            ),
            ctx.table.put_new_op(
                event_item(
                    ctx,
                    action="ISSUE_REPORTED",
                    record_sk=item["SK"],
                    appliance_id=appliance_id,
                    prior_version=None,
                    new_version=1,
                )
            ),
        ]
        result = {"outcome": "CREATED", "issue": view(item)}
        try:
            return mutations.commit(ctx, mutation, operations, result)
        except ConflictError as exc:
            if 0 in exc.failed_indexes:
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            raise

    return mutations.run(ctx, "report_issue", args, body)


def transition_item(
    ctx: OperationContext, item: dict[str, Any], event: IssueEvent, safety_reason: str | None
) -> dict[str, Any]:
    """The issue as it is after `event`. Raises INVALID_INPUT for an undefined transition."""
    updated = {
        **item,
        "status": next_issue_status(IssueStatus(item["status"]), event).value,
        "updated_at": iso_utc(ctx.clock.now()),
        "version": item["version"] + 1,
    }
    if event is IssueEvent.HAZARD_REPORTED:
        updated["safety_flag"] = True
        updated["safety_reason"] = safety_reason or "UNSPECIFIED"
    return updated


def apply_issue_event(
    ctx: OperationContext,
    issue_id: str,
    event: IssueEvent,
    expected_version: int,
    safety_reason: str | None = None,
    reopen_reason: str | None = None,
) -> dict[str, Any]:
    if event not in CUSTOMER_EVENTS:
        # Invariant 8: a household member can never fire a technician or provider outcome.
        raise DomainError(ErrorCode.AUTH_DENIED, "NOT_A_CUSTOMER_EVENT")
    action = Action.RESOLUTION_CONFIRM if event in _RESOLUTION_EVENTS else Action.ISSUE_WRITE
    authorize(ctx.actor, action, ctx.household_id)
    args = {
        "issue_id": issue_id,
        "event": event.value,
        "expected_version": expected_version,
        "safety_reason": safety_reason,
        "reopen_reason": reopen_reason,
    }

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        item = load(ctx, issue_id)
        if item["version"] != expected_version:
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION")
        updated = transition_item(ctx, item, event, safety_reason)
        if event is IssueEvent.RECURRED and reopen_reason:
            updated["reopen_reason"] = reopen_reason  # FR-17-AC2: reopened with a reason
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_versioned_op(updated, expected_version),
            ctx.table.put_op(issue_ref(ctx, updated)),
            ctx.table.put_new_op(
                event_item(
                    ctx,
                    action=f"ISSUE_{event.value}",
                    record_sk=item["SK"],
                    appliance_id=item["appliance_id"],
                    prior_version=expected_version,
                    new_version=updated["version"],
                )
            ),
        ]
        try:
            return mutations.commit(ctx, mutation, operations, view(updated))
        except ConflictError as exc:
            if 0 in exc.failed_indexes:
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    return mutations.run(ctx, "apply_issue_event", args, body)


_RESOLUTION_EVENTS = frozenset(
    {
        IssueEvent.CUSTOMER_CONFIRMED_RESOLVED,
        IssueEvent.CUSTOMER_SAYS_PERSISTS,
        IssueEvent.CUSTOMER_CLOSED,
    }
)


def report_warning_sign(
    ctx: OperationContext, sign: str, issue_id: str | None = None
) -> dict[str, Any]:
    """A reported warning sign (FR-07). Always returns the approved escalation text, verbatim.

    With an issue: that issue gets the safety flag. Without one (a fresh session, or a hazard on
    an appliance not yet discussed): the household gets a safety hold, which blocks routine
    guidance and is inherited by issues reported afterwards, and every open issue the actor may
    edit is flagged too. Only staff clear a flag or a hold (Slice 3).
    """
    hazard = classify(sign)
    if issue_id is not None:
        authorize(ctx.actor, Action.ISSUE_WRITE, ctx.household_id)
        issue = load(ctx, issue_id)
        if issue["status"] in ACTIVE_ISSUE_STATUSES:
            updated = apply_issue_event(
                ctx, issue_id, IssueEvent.HAZARD_REPORTED, issue["version"], hazard.reason
            )
        else:
            updated = view(issue)  # a resolved or closed case keeps its status
        return {"reason": hazard.reason, "speech": hazard.speech, "issue": updated}

    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)  # restricting is always allowed
    flagged = []
    meta = ctx.table.get(keys.household_pk(ctx.household_id), keys.META)
    if meta is not None and meta.get("storage_consent") == "GRANTED":
        set_safety_hold(ctx, hazard.reason)
        if ctx.actor.role is HouseholdRole.OWNER or Grant.EDIT in ctx.actor.grants:
            for item in ctx.table.query(keys.household_pk(ctx.household_id), keys.ISSUE_PREFIX):
                if item.get("kind") == "ISSUE" and item["status"] in ACTIVE_ISSUE_STATUSES:
                    flagged.append(
                        apply_issue_event(
                            ctx,
                            item["issue_id"],
                            IssueEvent.HAZARD_REPORTED,
                            item["version"],
                            hazard.reason,
                        )["issue_id"]
                    )
    return {"reason": hazard.reason, "speech": hazard.speech, "issue": None, "flagged": flagged}


def set_safety_hold(ctx: OperationContext, reason: str) -> None:
    args = {"reason": reason}

    def body(mutation: mutations.Mutation) -> Any:
        pk = keys.household_pk(ctx.household_id)
        meta = ctx.table.get(pk, keys.META)
        if meta is None:
            raise DomainError(ErrorCode.AUTH_DENIED, "HOUSEHOLD_NOT_FOUND")
        if meta.get("safety_hold"):
            return {"safety_hold": meta["safety_hold"]}  # already held; keep the first reason
        now = iso_utc(ctx.clock.now())
        hold = {"hold_id": new_id(), "reason": reason, "at": now, "actor_sub": ctx.actor.sub}
        updated = {**meta, "safety_hold": hold, "version": meta["version"] + 1}
        operations = [
            ctx.table.put_versioned_op(updated, meta["version"]),
            ctx.table.put_new_op(
                refs.ref_item(
                    hold["hold_id"], ctx.household_id, "HOLD", keys.META, index="SAFETY", sort=now
                )
            ),
            ctx.table.put_new_op(
                event_item(
                    ctx,
                    action="SAFETY_HOLD_SET",
                    record_sk=keys.META,
                    appliance_id=None,
                    prior_version=meta["version"],
                    new_version=updated["version"],
                )
            ),
        ]
        try:
            return mutations.commit(ctx, mutation, operations, {"safety_hold": hold})
        except ConflictError as exc:
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    mutations.run(ctx, "set_safety_hold", args, body)


def household_safety_hold(ctx: OperationContext) -> dict[str, Any] | None:
    meta = ctx.table.get(keys.household_pk(ctx.household_id), keys.META)
    return (meta or {}).get("safety_hold")


def issue_ref(ctx: OperationContext, item: dict[str, Any]) -> dict[str, Any]:
    """The issue's opaque reference; flagged issues are on the coordinator's safety list."""
    return refs.ref_item(
        item["issue_id"],
        ctx.household_id,
        "ISSUE",
        keys.issue_sk(item["issue_id"]),
        index="SAFETY" if item.get("safety_flag") else None,
        sort=item.get("updated_at"),
    )


def confirm_resolution(
    ctx: OperationContext, issue_id: str, answer: str, close: bool = False
) -> dict[str, Any]:
    """The customer's own answer (FR-17; invariant 8): only this resolves an issue. Closing is a
    separate, explicit request; a visit still booked is mentioned, never cancelled silently."""
    authorize(ctx.actor, Action.RESOLUTION_CONFIRM, ctx.household_id)
    if answer not in ("RESOLVED", "PERSISTS", "UNSURE"):
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_ANSWER")
    item = load(ctx, issue_id)
    status = IssueStatus(item["status"])
    if answer == "RESOLVED" and status is not IssueStatus.RESOLVED:
        item_view = apply_issue_event(
            ctx, issue_id, IssueEvent.CUSTOMER_CONFIRMED_RESOLVED, item["version"]
        )
    elif answer == "PERSISTS" and status in (IssueStatus.AWAITING_CUSTOMER, IssueStatus.RESOLVED):
        item_view = apply_issue_event(
            ctx, issue_id, IssueEvent.CUSTOMER_SAYS_PERSISTS, item["version"]
        )
    else:
        item_view = view(item)  # "not sure", or nothing to change: no state change
    closed = False
    if close and answer == "RESOLVED" and item_view["status"] == IssueStatus.RESOLVED.value:
        item_view = apply_issue_event(
            ctx, issue_id, IssueEvent.CUSTOMER_CLOSED, item_view["version"]
        )
        closed = True
    booked = [
        r
        for r in ctx.table.query(keys.household_pk(ctx.household_id), keys.REQUEST_PREFIX)
        if r.get("kind") == "SR" and r["issue_id"] == issue_id and r["state"] == "CONFIRMED"
    ]
    return {
        "answer": answer,
        "issue": item_view,
        "closed": closed,
        "uncancelled_visit": bool(booked),
    }
