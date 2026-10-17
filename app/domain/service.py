"""Service requests from the household's side (FR-11, FR-13 to FR-15, FR-27; plan P3-3).

A draft can exist without an address or contact route; submission cannot. Fee and warranty start
UNKNOWN, never zero or "covered". The address and contact are captured by voice
(`record_service_details`), stored USER_REPORTED and never logged.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.config import SIMULATION_MODE
from app.domain import booking, guidance, issues, mutations, requests
from app.domain.clock import iso_utc, local_date
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.household import require_storage_consent
from app.domain.ids import new_id
from app.domain.state import (
    TERMINAL_REQUEST_STATUSES,
    IssueEvent,
    IssueStatus,
    RequestStatus,
)
from app.provider.simulator import PROVIDER_NAME
from app.security.authz import Action, authorize
from app.store import keys

OFFER_MINUTES = 10
_FIELDS = {"address": ("service_address", 300), "contact": ("contact_route", 100)}


def draft_service_request(ctx: OperationContext, issue_id: str) -> dict[str, Any]:
    authorize(ctx.actor, Action.SERVICE_BOOK, ctx.household_id)

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        issue = issues.load(ctx, issue_id)
        existing = requests.open_request_for_issue(ctx, issue_id)
        if existing is not None:  # one open request per issue (BRD §7.3)
            return _existing(existing)
        pk = keys.household_pk(ctx.household_id)
        # The per-issue sentinel makes "one open request" hold under concurrent drafts (I15). A
        # sentinel left by a request that has since ended is taken over conditionally.
        sentinel = ctx.table.get(pk, keys.open_request_sk(issue_id))
        if sentinel is not None:
            held = ctx.table.get(pk, keys.request_sk(sentinel["request_id"]))
            if held is not None and held["state"] not in TERMINAL_REQUEST_STATUSES:
                return _existing(held)
        meta = ctx.table.get(pk, keys.META) or {}
        appliance = ctx.table.get(pk, keys.appliance_sk(issue["appliance_id"])) or {}
        now = iso_utc(ctx.clock.now())
        request_id = new_id()
        item = requests.indexed(
            {
                "PK": pk,
                "SK": keys.request_sk(request_id),
                "kind": "SR",
                "request_id": request_id,
                "household_id": ctx.household_id,
                "issue_id": issue_id,
                "appliance_id": issue["appliance_id"],
                "state": RequestStatus.DRAFT.value,
                "mode": SIMULATION_MODE,
                "snapshot": {
                    "summary": issue["summary"],
                    "symptom_category": issue["symptom_category"],
                    "appliance": appliance.get("nickname"),
                    "category": appliance.get("category"),
                    "model_status": (appliance.get("fields") or {}).get("model", {}).get("status"),
                    "checks": [
                        {"step_id": s["step_id"], "result": s["result"]}
                        for s in guidance.recorded_steps(ctx, issue_id)
                    ],
                },
                "fee": {"amount_paise": None, "currency": "INR", "status": "UNKNOWN"},
                "warranty": "UNKNOWN",
                "address": meta.get("service_address"),
                "contact": meta.get("contact_route"),
                "created_at": now,
                "updated_at": now,
                "version": 1,
            }
        )
        claim = {"PK": pk, "SK": keys.open_request_sk(issue_id), "request_id": request_id}
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_new_op(claim)
            if sentinel is None
            else ctx.table.put_if_op(
                claim, "request_id = :ended", {":ended": sentinel["request_id"]}
            ),
            ctx.table.put_new_op(item),
            ctx.table.put_new_op(requests.case_ref(item)),
            ctx.table.put_new_op(
                event_item(
                    ctx,
                    action="SERVICE_DRAFTED",
                    record_sk=item["SK"],
                    appliance_id=item["appliance_id"],
                    prior_version=None,
                    new_version=1,
                )
            ),
        ]
        if issue["status"] in (IssueStatus.OPEN.value, IssueStatus.TRIAGING.value):
            moved = issues.transition_item(ctx, issue, IssueEvent.SERVICE_REQUESTED, None)
            operations.append(ctx.table.put_versioned_op(moved, issue["version"]))
        result = {
            "outcome": "CREATED",
            "request": requests.view(item),
            "missing": requests.missing_details(item),
        }
        try:
            return mutations.commit(ctx, mutation, operations, result)
        except ConflictError as exc:
            if 0 in exc.failed_indexes:
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            if 1 in exc.failed_indexes:  # someone else drafted for this issue just now
                winner = ctx.table.get(pk, keys.open_request_sk(issue_id))
                held = winner and ctx.table.get(pk, keys.request_sk(winner["request_id"]))
                if held:
                    return _existing(held)
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    return mutations.run(ctx, "draft_service_request", {"issue_id": issue_id}, body)


def _existing(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "outcome": "EXISTING",
        "request": requests.view(item),
        "missing": requests.missing_details(item),
    }


def record_service_details(
    ctx: OperationContext, request_id: str, field: str, value: str, expected_version: int
) -> dict[str, Any]:
    """Save the service address or contact route the user dictated (P3-3)."""
    authorize(ctx.actor, Action.SERVICE_BOOK, ctx.household_id)
    if field not in _FIELDS:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_FIELD")
    attribute, limit = _FIELDS[field]
    text = " ".join(value.split())
    if not text or len(text) > limit:
        raise DomainError(ErrorCode.INVALID_INPUT, "INVALID_DETAIL")
    args = {
        "request_id": request_id,
        "field": field,
        "value": text,
        "expected_version": expected_version,
    }

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        sr = requests.load(ctx, request_id)
        if sr["version"] != expected_version:
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION")
        if sr["state"] != RequestStatus.DRAFT.value:
            raise DomainError(ErrorCode.INVALID_INPUT, "NOT_EDITABLE")
        now = iso_utc(ctx.clock.now())
        detail = {"value": text, "status": "USER_REPORTED"}
        updated = requests.indexed(
            {**sr, field: detail, "updated_at": now, "version": sr["version"] + 1}
        )
        pk = keys.household_pk(ctx.household_id)
        meta = ctx.table.get(pk, keys.META)
        if meta is None:
            raise DomainError(ErrorCode.AUTH_DENIED, "HOUSEHOLD_NOT_FOUND")
        remembered = {**meta, attribute: detail, "version": meta["version"] + 1}
        operations = [
            ctx.table.put_versioned_op(updated, sr["version"]),
            # One write to META: still the version we read, and storage consent still granted
            # (a transaction may touch an item only once).
            ctx.table.put_if_op(
                remembered,
                "#version = :expected AND #consent = :granted",
                {":expected": meta["version"], ":granted": "GRANTED"},
                {"#version": "version", "#consent": "storage_consent"},
            ),
            ctx.table.put_op(requests.case_ref(updated)),
            ctx.table.put_new_op(
                event_item(  # the value itself never goes into the history or the logs
                    ctx,
                    action=f"SERVICE_{field.upper()}_RECORDED",
                    record_sk=updated["SK"],
                    appliance_id=updated["appliance_id"],
                    prior_version=sr["version"],
                    new_version=updated["version"],
                )
            ),
        ]
        try:
            return mutations.commit(ctx, mutation, operations, requests.view(updated))
        except ConflictError as exc:
            if 1 in exc.failed_indexes and meta.get("storage_consent") != "GRANTED":
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    return mutations.run(ctx, "record_service_details", args, body)


def list_slots(
    ctx: OperationContext, request_id: str, from_date: str | None = None, days: int = 3
) -> dict[str, Any]:
    """Demo slots from the household's local date. Listing never reserves a slot (FR-13)."""
    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)
    requests.load(ctx, request_id)
    start = date.fromisoformat(from_date) if from_date else local_date(ctx.clock.now())
    now = ctx.clock.now()
    slots = booking.provider(ctx).list_slots(start, max(1, min(days, 7)))
    expires = now + timedelta(minutes=OFFER_MINUTES)
    # Remember what was offered: an approval may only name an offered slot, and it expires with
    # the offer (TDD §4.3 rule 1; I7). Listing still reserves nothing.
    pk = keys.household_pk(ctx.household_id)
    for slot in slots:
        if slot.available:
            ctx.table.put(
                {
                    "PK": pk,
                    "SK": keys.offer_sk(request_id, slot.slot_id),
                    "kind": "OFFER",
                    "expires_at": iso_utc(expires),
                    "ttl": int((expires + timedelta(days=1)).timestamp()),
                }
            )
    return {
        "provider": PROVIDER_NAME,
        "offer_expires_at": iso_utc(expires),
        "slots": [
            {
                **slot.as_dict(),
                "date_words": requests.date_words(slot.date),
                "window_words": requests.WINDOW_WORDS[slot.window],
            }
            for slot in slots
        ],
    }


def get_service_status(
    ctx: OperationContext, request_id: str | None = None, issue_id: str | None = None
) -> dict[str, Any]:
    """The latest authoritative state, reconciling a pending request first (FR-15)."""
    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)
    if request_id:
        sr = requests.load(ctx, request_id)
    else:
        candidates = [r for r in requests.all_requests(ctx) if r["issue_id"] == issue_id]
        if not candidates:
            raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
        sr = max(candidates, key=lambda r: r["updated_at"])
    reconciled = None
    if sr["state"] in requests.PENDING_STATES:
        reconciled = booking.reconcile(ctx, sr)
        sr = requests.load(ctx, sr["request_id"])
    appointment = requests.appointment(ctx, sr["request_id"], sr.get("appointment_id"))
    return {
        "request": requests.view(sr),
        "appointment": requests.appointment_view(appointment),
        "reconciled": reconciled,
        "provider": PROVIDER_NAME,
        "last_update": sr["updated_at"],
    }
