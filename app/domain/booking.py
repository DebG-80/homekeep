"""Dispatch to the provider and the outcomes it produces (TDD §4.6, §6.2; BRD §7.2).

Persist before dispatch: the pending state and its provider operation key are written before
the provider is called. Every outcome is one transaction. Confirmation writes the request,
appointment, active sentinel, issue state, case reference and event together. A timeout leaves
the request pending; reconciliation (on read and in the sweep) applies whatever the provider
recorded. Nothing here ever says "confirmed" without the provider's record.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from app.config import SIMULATION_MODE
from app.domain import issues, requests
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.ids import new_id
from app.domain.state import (
    IssueEvent,
    IssueStatus,
    RequestEvent,
    RequestStatus,
    cancel_rejected_target,
    next_request_status,
)
from app.provider.simulator import DemoProvider, ProviderTimeout, ProviderUnavailable
from app.store import keys

R, Q = RequestStatus, RequestEvent


def provider(ctx: OperationContext) -> DemoProvider:
    return DemoProvider(ctx.table, ctx.clock, ctx.faults_enabled)


def default_technician(ctx: OperationContext) -> str | None:
    config = ctx.table.get(keys.PROVIDER_PK, "CONFIG")
    return (config or {}).get("default_technician_sub")


def _event(
    ctx: OperationContext, action: str, sr: dict[str, Any], updated: dict[str, Any]
) -> dict[str, Any]:
    """The request's event. Every one carries the approval and the dispatch's correlation ID, so
    approval, dispatch and a later reconciliation join up in the trail (FR-28)."""
    return ctx.table.put_new_op(
        event_item(
            ctx,
            action=action,
            record_sk=keys.request_sk(sr["request_id"]),
            appliance_id=sr["appliance_id"],
            prior_version=sr["version"],
            new_version=updated["version"],
            provenance="PROVIDER" if action.startswith("SERVICE_") else "CUSTOMER",
            extra={
                "approval_id": updated.get("active_approval_id"),
                "dispatch_correlation_id": updated.get("dispatch_correlation_id"),
            },
        )
    )


def _advance(sr: dict[str, Any], *events: RequestEvent, now: str, **fields: Any) -> dict[str, Any]:
    state = RequestStatus(sr["state"])
    for event in events:
        state = next_request_status(state, event)
    return requests.indexed(
        {
            **sr,
            **fields,
            "state": state.value,
            "mode": SIMULATION_MODE,
            "updated_at": now,
            "version": sr["version"] + 1,
        }
    )


def _write(ctx: OperationContext, operations: list[dict[str, Any]]) -> None:
    try:
        ctx.table.transact(operations)
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc


def _result(ctx: OperationContext, outcome: str, sr: dict[str, Any]) -> dict[str, Any]:
    appointment = requests.appointment(ctx, sr["request_id"], sr.get("appointment_id"))
    return {
        "outcome": outcome,
        "request": requests.view(sr),
        "appointment": requests.appointment_view(appointment),
    }


def _simple_transition(
    ctx: OperationContext,
    sr: dict[str, Any],
    action: str,
    *events: RequestEvent,
    extra_ops: tuple[dict[str, Any], ...] = (),
    **fields: Any,
) -> dict[str, Any]:
    now = iso_utc(ctx.clock.now())
    updated = _advance(sr, *events, now=now, **fields)
    _write(
        ctx,
        [
            ctx.table.put_versioned_op(updated, sr["version"]),
            ctx.table.put_op(requests.case_ref(updated)),
            _event(ctx, action, sr, updated),
            *extra_ops,
        ],
    )
    return updated


def _issue_op(
    ctx: OperationContext, issue_id: str, event: IssueEvent, when: set[IssueStatus]
) -> list[dict[str, Any]]:
    issue = issues.load(ctx, issue_id)
    if IssueStatus(issue["status"]) not in when:
        return []
    moved = issues.transition_item(ctx, issue, event, None)
    return [ctx.table.put_versioned_op(moved, issue["version"])]


# --- submit -------------------------------------------------------------------------------


def submit(ctx: OperationContext, sr: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    slot_id = approval["slot"]["slot_id"]
    operation_key = f"{approval['approval_id']}:submit"
    if sr["state"] == R.DRAFT.value:
        if not provider(ctx).slot(slot_id).available:
            return _result(ctx, "SLOT_UNAVAILABLE", sr)  # stays a draft; another time can be chosen
        now = iso_utc(ctx.clock.now())
        approved = _advance(
            sr,
            Q.USER_APPROVED,
            now=now,
            approval_id=approval["approval_id"],
            active_approval_id=approval["approval_id"],
            dispatch_correlation_id=ctx.correlation_id,
            slot_id=slot_id,
            address=approval["payload"]["address"],
            contact=approval["payload"]["contact"],
        )
        pending = _advance(approved, Q.DISPATCH_STARTED, now=now, op_key=operation_key)
        pending["version"] = sr["version"] + 1
        _write(
            ctx,
            [
                ctx.table.put_versioned_op(pending, sr["version"]),
                ctx.table.put_op(requests.case_ref(pending)),
                _event(ctx, "SERVICE_APPROVED", sr, pending),
                _event(ctx, "SERVICE_SUBMITTED", sr, pending),
            ],
        )
        sr = pending
    elif sr.get("approval_id") != approval["approval_id"]:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "REQUEST_MOVED_ON")
    if sr["state"] != R.SUBMISSION_PENDING.value:
        return _result(ctx, _settled_outcome(sr), sr)  # already settled (for example, reconciled)
    try:
        record = provider(ctx).submit(ctx.household_id, operation_key, slot_id)
    except ProviderTimeout:
        return _result(ctx, "PENDING", sr)  # RESULT_UNKNOWN: reconcile later, never guess
    except ProviderUnavailable:
        failed = _simple_transition(ctx, sr, "SERVICE_FAILED", Q.SUBMISSION_FAILED)
        return _result(ctx, "FAILED", failed)
    return _settle(ctx, sr, apply_submit_record, record, _settled_outcome)


def _settle(
    ctx: OperationContext,
    sr: dict[str, Any],
    apply: Callable[[OperationContext, dict[str, Any], dict[str, Any]], dict[str, Any]],
    record: dict[str, Any],
    outcome_of: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """Apply the provider's record. If another path (the sweep, a status read) applied it first,
    our conditional write loses: re-read and report what is now recorded (TDD §4.6)."""
    try:
        return apply(ctx, sr, record)
    except DomainError as exc:
        if exc.code is not ErrorCode.RECORD_CONFLICT:
            raise
        latest = requests.load(ctx, sr["request_id"])
        if latest["version"] == sr["version"]:
            raise  # nothing moved on: a genuine conflict
        return _result(ctx, outcome_of(latest), latest)


def _settled_outcome(sr: dict[str, Any]) -> str:
    return {
        R.CONFIRMED.value: "CONFIRMED",
        R.REQUESTED.value: "REQUESTED",
        R.REJECTED.value: "REJECTED",
        R.FAILED.value: "FAILED",
        R.CANCELLED.value: "CANCELLED",
        R.SUBMISSION_PENDING.value: "PENDING",
    }.get(sr["state"], sr["state"])


def apply_submit_record(
    ctx: OperationContext, sr: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any]:
    status = record["status"]
    if status == "REJECTED":
        rejected = _simple_transition(ctx, sr, "SERVICE_REJECTED", Q.PROVIDER_REJECTED)
        return _result(ctx, "REJECTED", rejected)
    if status == "REQUESTED":
        requested = _simple_transition(
            ctx,
            sr,
            "SERVICE_REQUESTED",
            Q.PROVIDER_ACKNOWLEDGED,
            provider_ref=record["provider_ref"],
        )
        return _result(ctx, "REQUESTED", requested)
    return confirm_booking(ctx, sr, record["provider_ref"], record["slot_id"])


def confirm_booking(
    ctx: OperationContext,
    sr: dict[str, Any],
    provider_ref: str,
    slot_id: str,
    extra_ops: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    """The single confirmation transaction (TDD §6.2)."""
    slot = provider(ctx).slot(slot_id)
    now = iso_utc(ctx.clock.now())
    appointment_id = new_id()
    pk = keys.household_pk(ctx.household_id)
    confirmed = _advance(
        sr,
        Q.PROVIDER_CONFIRMED,
        now=now,
        provider_ref=provider_ref,
        slot_id=slot_id,
        appointment_id=appointment_id,
        fee={"amount_paise": slot.fee_paise, "currency": "INR", "status": slot.fee_status},
        assignee_sub=sr.get("assignee_sub") or default_technician(ctx),
    )
    appointment = {
        "PK": pk,
        "SK": keys.appointment_sk(sr["request_id"], appointment_id),
        "kind": "APPOINTMENT",
        "appointment_id": appointment_id,
        "request_id": sr["request_id"],
        "slot_id": slot_id,
        "date": slot.date,
        "window": slot.window,
        "start_utc": slot.start_utc,
        "end_utc": slot.end_utc,
        "status": "CONFIRMED",
        "provider_ref": provider_ref,
        "version": 1,
    }
    operations = [
        ctx.table.put_versioned_op(confirmed, sr["version"]),
        ctx.table.put_new_op(appointment),
        ctx.table.put_new_op(
            {
                "PK": pk,
                "SK": keys.active_sk(sr["request_id"]),
                "kind": "ACTIVE",
                "appointment_id": appointment_id,
            }
        ),
        ctx.table.put_op(requests.case_ref(confirmed)),
        *_issue_op(
            ctx, sr["issue_id"], IssueEvent.APPOINTMENT_CONFIRMED, {IssueStatus.SERVICE_NEEDED}
        ),
        _event(ctx, "SERVICE_CONFIRMED", sr, confirmed),
        *extra_ops,
    ]
    _write(ctx, operations)
    return {
        "outcome": "CONFIRMED",
        "request": requests.view(confirmed),
        "appointment": requests.appointment_view(appointment),
    }


# --- reschedule ---------------------------------------------------------------------------


def reschedule(
    ctx: OperationContext, sr: dict[str, Any], approval: dict[str, Any]
) -> dict[str, Any]:
    new_slot = approval["slot"]["slot_id"]
    operation_key = f"{approval['approval_id']}:replace"
    if sr["state"] == R.CONFIRMED.value and sr.get("change_op") != operation_key:
        done = provider(ctx).status(operation_key)
        if done is not None:  # a retry after it already ran: supersede exactly once (FR-14)
            changed = done["status"] == "REPLACED" and sr.get("slot_id") == done.get("slot_id")
            return _result(ctx, "CHANGED" if changed else "CHANGE_FAILED", sr)
        sr = _simple_transition(
            ctx,
            sr,
            "SERVICE_CHANGE_REQUESTED",
            Q.CHANGE_APPROVED,
            change_op=operation_key,
            change_slot_id=new_slot,
            active_approval_id=approval["approval_id"],
            dispatch_correlation_id=ctx.correlation_id,
        )
    if sr["state"] != R.CHANGE_PENDING.value or sr.get("change_op") != operation_key:
        return _result(ctx, _change_outcome(sr, new_slot), sr)
    record = provider(ctx).replace(ctx.household_id, operation_key, sr["slot_id"], new_slot)
    return _settle(ctx, sr, apply_replace_record, record, lambda r: _change_outcome(r, new_slot))


def _change_outcome(sr: dict[str, Any], new_slot: str) -> str:
    if sr["state"] == R.CHANGE_PENDING.value:
        return "PENDING"
    return "CHANGED" if sr.get("slot_id") == new_slot else "CHANGE_FAILED"


def apply_replace_record(
    ctx: OperationContext, sr: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any]:
    if record["status"] != "REPLACED":
        kept = _simple_transition(
            ctx,
            sr,
            "SERVICE_RESCHEDULE_FAILED",
            Q.CHANGE_FAILED,
            change_op=None,
            change_slot_id=None,
        )
        return _result(ctx, "CHANGE_FAILED", kept)  # the original appointment stays active
    slot = provider(ctx).slot(record["slot_id"])
    now = iso_utc(ctx.clock.now())
    pk = keys.household_pk(ctx.household_id)
    old = requests.appointment(ctx, sr["request_id"], sr["appointment_id"])
    if old is None:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "NO_ACTIVE_APPOINTMENT")
    appointment_id = new_id()
    changed = _advance(
        sr,
        Q.CHANGE_CONFIRMED,
        now=now,
        slot_id=slot.slot_id,
        appointment_id=appointment_id,
        change_op=None,
        change_slot_id=None,
    )
    appointment = {
        **{k: old[k] for k in ("PK", "kind", "request_id", "provider_ref")},
        "SK": keys.appointment_sk(sr["request_id"], appointment_id),
        "appointment_id": appointment_id,
        "slot_id": slot.slot_id,
        "date": slot.date,
        "window": slot.window,
        "start_utc": slot.start_utc,
        "end_utc": slot.end_utc,
        "status": "CONFIRMED",
        "version": 1,
    }
    sentinel = {
        "PK": pk,
        "SK": keys.active_sk(sr["request_id"]),
        "kind": "ACTIVE",
        "appointment_id": appointment_id,
    }
    _write(
        ctx,
        [
            ctx.table.put_versioned_op(changed, sr["version"]),
            ctx.table.put_versioned_op(
                {**old, "status": "SUPERSEDED", "version": old["version"] + 1}, old["version"]
            ),
            ctx.table.put_new_op(appointment),
            ctx.table.put_if_op(sentinel, "appointment_id = :old", {":old": old["appointment_id"]}),
            ctx.table.put_op(requests.case_ref(changed)),
            _event(ctx, "SERVICE_RESCHEDULED", sr, changed),
        ],
    )
    return {
        "outcome": "CHANGED",
        "request": requests.view(changed),
        "appointment": requests.appointment_view(appointment),
    }


# --- cancel -------------------------------------------------------------------------------


def cancel(ctx: OperationContext, sr: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    operation_key = f"{approval['approval_id']}:cancel"
    if (
        sr["state"] in (R.REQUESTED.value, R.CONFIRMED.value)
        and sr.get("cancel_op") != operation_key
    ):
        if provider(ctx).status(operation_key) is not None:  # a retry after it already ran
            return _result(ctx, _cancel_outcome(sr), sr)
        sr = _simple_transition(
            ctx,
            sr,
            "SERVICE_CANCEL_REQUESTED",
            Q.CANCEL_APPROVED,
            cancel_op=operation_key,
            previous_state=sr["state"],
            active_approval_id=approval["approval_id"],
            dispatch_correlation_id=ctx.correlation_id,
        )
    if sr["state"] != R.CANCEL_PENDING.value or sr.get("cancel_op") != operation_key:
        return _result(ctx, _cancel_outcome(sr), sr)
    try:
        record = provider(ctx).cancel(ctx.household_id, operation_key, sr.get("slot_id"))
    except ProviderTimeout:
        return _result(ctx, "CANCEL_PENDING", sr)  # never announced as cancelled
    return _settle(ctx, sr, apply_cancel_record, record, _cancel_outcome)


def _cancel_outcome(sr: dict[str, Any]) -> str:
    if sr["state"] == R.CANCELLED.value:
        return "CANCELLED"
    return "CANCEL_PENDING" if sr["state"] == R.CANCEL_PENDING.value else "CANCEL_REFUSED"


def apply_cancel_record(
    ctx: OperationContext, sr: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any]:
    now = iso_utc(ctx.clock.now())
    if record["status"] != "CANCELLED":
        previous = cancel_rejected_target(RequestStatus(sr["previous_state"]))
        restored = requests.indexed(
            {
                **sr,
                "state": previous.value,
                "cancel_op": None,
                "updated_at": now,
                "version": sr["version"] + 1,
            }
        )
        _write(
            ctx,
            [
                ctx.table.put_versioned_op(restored, sr["version"]),
                ctx.table.put_op(requests.case_ref(restored)),
                _event(ctx, "SERVICE_CANCEL_REFUSED", sr, restored),
            ],
        )
        return _result(ctx, "CANCEL_REFUSED", restored)
    cancelled = _advance(sr, Q.CANCEL_CONFIRMED, now=now)
    operations = [
        ctx.table.put_versioned_op(cancelled, sr["version"]),
        ctx.table.put_op(requests.case_ref(cancelled)),
        _event(ctx, "SERVICE_CANCELLED", sr, cancelled),
    ]
    old = requests.appointment(ctx, sr["request_id"], sr.get("appointment_id"))
    if old is not None:
        operations += [
            ctx.table.put_versioned_op(
                {**old, "status": "CANCELLED", "version": old["version"] + 1}, old["version"]
            ),
            ctx.table.delete_op(
                keys.household_pk(ctx.household_id), keys.active_sk(sr["request_id"])
            ),
        ]
    # The issue needs service again, unless another confirmed booking still covers it.
    others = [
        r
        for r in requests.all_requests(ctx)
        if r["issue_id"] == sr["issue_id"]
        and r["request_id"] != sr["request_id"]
        and r["state"] == R.CONFIRMED.value
    ]
    if not others:
        operations += _issue_op(
            ctx, sr["issue_id"], IssueEvent.BOOKING_ENDED, {IssueStatus.SERVICE_PENDING}
        )
    _write(ctx, operations)
    return _result(ctx, "CANCELLED", cancelled)


# --- reconciliation -------------------------------------------------------------------------


def outcome_for(
    ctx: OperationContext, approval: dict[str, Any], sr: dict[str, Any]
) -> dict[str, Any]:
    """The recorded outcome of this approval's action on the request, or NOT_SENT if it was
    never dispatched (I2)."""
    kind, approval_id = approval["action_kind"], approval["approval_id"]
    if sr.get("active_approval_id") != approval_id:
        return _result(ctx, "NOT_SENT", sr)
    if kind == "SUBMIT":
        return _result(ctx, _settled_outcome(sr), sr)
    if kind == "RESCHEDULE":
        return _result(ctx, _change_outcome(sr, approval["slot"]["slot_id"]), sr)
    return _result(ctx, _cancel_outcome(sr), sr)


REDISPATCH_AFTER = timedelta(seconds=60)
STUCK_AFTER = timedelta(minutes=15)


def _dispatch_again(ctx: OperationContext, sr: dict[str, Any]) -> dict[str, Any] | None:
    """Repeat the original provider call under its operation key; the provider de-duplicates,
    so this never books twice. None while there is still no answer."""
    state = sr["state"]
    try:
        if state == R.SUBMISSION_PENDING.value:
            return provider(ctx).submit(ctx.household_id, sr["op_key"], sr["slot_id"])
        if state == R.CHANGE_PENDING.value:
            return provider(ctx).replace(
                ctx.household_id, sr["change_op"], sr["slot_id"], sr["change_slot_id"]
            )
        return provider(ctx).cancel(ctx.household_id, sr["cancel_op"], sr.get("slot_id"))
    except ProviderTimeout:
        return provider(ctx).status(_operation_key(sr))  # it was recorded; apply it below
    except ProviderUnavailable:
        if state == R.SUBMISSION_PENDING.value:  # definitive: nothing was recorded (G3-10)
            _simple_transition(ctx, sr, "SERVICE_FAILED", Q.SUBMISSION_FAILED)
        return None


def _operation_key(sr: dict[str, Any]) -> str | None:
    return {
        R.SUBMISSION_PENDING.value: sr.get("op_key"),
        R.CHANGE_PENDING.value: sr.get("change_op"),
        R.CANCEL_PENDING.value: sr.get("cancel_op"),
    }.get(sr["state"])


def _report_stuck(ctx: OperationContext, sr: dict[str, Any]) -> dict[str, Any]:
    """Once: a coordinator follows up a request the provider never answered (TDD §4.6)."""
    now = iso_utc(ctx.clock.now())
    flagged = requests.indexed({**sr, "stuck_reported": now, "version": sr["version"] + 1})
    item_id = new_id()
    _write(
        ctx,
        [
            ctx.table.put_versioned_op(flagged, sr["version"]),
            ctx.table.put_new_op(
                {
                    "PK": keys.OPS_PK,
                    "SK": keys.manual_sk(now, item_id),
                    "kind": "MANUAL",
                    "item_id": item_id,
                    "case_id": sr["request_id"],
                    "household_id": ctx.household_id,
                    "reason": "DISPATCH_UNKNOWN",
                    "status": "OPEN",
                    "at": now,
                    "version": 1,
                }
            ),
        ],
    )
    return flagged


_APPLY = {
    R.SUBMISSION_PENDING.value: (apply_submit_record, _settled_outcome),
    R.CHANGE_PENDING.value: (
        apply_replace_record,
        lambda r: _change_outcome(r, r.get("change_slot_id") or ""),
    ),
    R.CANCEL_PENDING.value: (apply_cancel_record, _cancel_outcome),
}


def reconcile(ctx: OperationContext, sr: dict[str, Any]) -> str | None:
    """Apply what the provider recorded for a pending request. None if still unknown.

    A request whose dispatch never reached the provider (the process stopped between persisting
    and calling) is dispatched again after a minute, and raised for manual review once it has
    been unanswered for 15 minutes.
    """
    operation_key = _operation_key(sr)
    if operation_key is None:
        return None
    apply, outcome_of = _APPLY[sr["state"]]
    record = provider(ctx).status(operation_key)
    if record is None:
        age = ctx.clock.now() - requests.as_utc(sr["updated_at"])
        if age < REDISPATCH_AFTER:
            return None
        if age >= STUCK_AFTER and not sr.get("stuck_reported"):
            sr = _report_stuck(ctx, sr)
        record = _dispatch_again(ctx, sr)
        if record is None:
            latest = requests.load(ctx, sr["request_id"])
            return None if latest["state"] == sr["state"] else outcome_of(latest)
    return _settle(ctx, sr, apply, record, outcome_of)["outcome"]
