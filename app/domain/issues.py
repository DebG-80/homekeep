"""Issues: capture without accidental duplicates, and transitions through the BRD §7.1 map.

The original wording is kept alongside a short summary (FR-05). If the appliance already has an
active issue, the caller must say whether this continues it or is a confirmed, distinct problem.
The safety flag is orthogonal to status: once set it stays, whatever the status does, and only
staff can clear it (Slice 3).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.domain import appliances, mutations
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.household import require_storage_consent
from app.domain.ids import new_id
from app.domain.state import ACTIVE_ISSUE_STATUSES, IssueEvent, IssueStatus, next_issue_status
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
                raise DomainError(ErrorCode.INVALID_INPUT, "NOT_AN_ACTIVE_ISSUE")
            return {"outcome": "CONTINUED", "issue": view(chosen[0])}
        if active and not confirmed_distinct:
            # FR-05: ask whether this is the existing case before creating another. Nothing written.
            return {"outcome": "NEEDS_CHOICE", "active_issues": [view(i) for i in active]}

        issue_id = new_id()
        now = iso_utc(ctx.clock.now())
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
            "safety_flag": False,
            "safety_reason": None,
            "reporting_actor": ctx.actor.sub,
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_new_op(item),
            ctx.table.put_op(
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
    }

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        item = load(ctx, issue_id)
        if item["version"] != expected_version:
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION")
        updated = transition_item(ctx, item, event, safety_reason)
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_versioned_op(updated, expected_version),
            ctx.table.put_op(
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
