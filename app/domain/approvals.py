"""The approval ledger (TDD §3.4 F2, §4.3, §5.4; FR-12; CLAUDE.md invariant 2).

The agent may only *prepare* an action. Its server-built read-back is spoken verbatim, and only
HomeKeep's channel, after its deterministic guard accepts a "yes", calls `confirm_action` and
then `execute_action`. Both are trusted tools that need attestation. Confirmation re-checks
everything against current records: expiry, actor and session, grant, read-back timing (voice),
and the payload hash, including a fresh fee quote. Execution runs once per approval.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain import booking, household, mutations, requests
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.household import ConsentDecision, ConsentPurpose, require_storage_consent
from app.domain.ids import new_id
from app.domain.state import RequestStatus
from app.provider.simulator import PROVIDER_NAME
from app.security.authz import Action, authorize
from app.store import keys
from app.store.ops import canonical_json

SERVICE_KINDS = frozenset({"SUBMIT", "RESCHEDULE", "CANCEL"})
CONSENT_KINDS = {
    "CONSENT_STORAGE": ConsentPurpose.STORAGE,
    "CONSENT_SHARING": ConsentPurpose.SHARING,
}
APPROVAL_TTL = timedelta(minutes=5)
CLIENT_CLOCK_SKEW = timedelta(seconds=2)
CONSENT_VERSION = "consent-v1"
DATA_SHARED = ("appliance problem and checks", "service address", "contact route")
_FINAL_STATES = frozenset({"EXECUTED", "CANCELLED", "SUPERSEDED", "EXPIRED", "REFUSED"})


def _action(kind: str) -> Action:
    if kind in CONSENT_KINDS:
        return Action.CONSENT_RECORD
    if kind in SERVICE_KINDS:
        return Action.SERVICE_BOOK
    raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_ACTION")


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def _load(ctx: OperationContext, approval_id: str) -> dict[str, Any]:
    item = ctx.table.get(keys.household_pk(ctx.household_id), keys.approval_sk(approval_id))
    if item is None:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    return item


def _pending_in_session(ctx: OperationContext) -> list[dict[str, Any]]:
    items = ctx.table.query(keys.household_pk(ctx.household_id), keys.APPROVAL_PREFIX)
    return [
        i
        for i in items
        if i["state"] == "PENDING"
        and i["session_id"] == ctx.session_id
        and i["actor_sub"] == ctx.actor.sub
    ]


def pending_for_session(ctx: OperationContext) -> dict[str, Any] | None:
    now = iso_utc(ctx.clock.now())
    live = [i for i in _pending_in_session(ctx) if i["expires_at"] > now]
    if not live:
        return None
    latest = max(live, key=lambda i: i["created_at"])
    return {
        "pending_ref": latest["approval_id"],
        "kind": latest["action_kind"],
        "expires_at": latest["expires_at"],
    }


def _service_payload(
    ctx: OperationContext, kind: str, sr: dict[str, Any], slot_id: str | None
) -> dict[str, Any]:
    fee = None
    if kind in ("SUBMIT", "RESCHEDULE"):
        fee = booking.provider(ctx).quote(ctx.household_id, slot_id or "")
    return {
        "kind": kind,
        "request_id": sr["request_id"],
        "request_version": sr["version"],
        "slot_id": slot_id,
        "fee_paise": fee,
        "address": sr.get("address"),
        "contact": sr.get("contact"),
        "data_shared": list(DATA_SHARED),
    }


def _validate_service(
    ctx: OperationContext, kind: str, sr: dict[str, Any], slot_id: str | None
) -> dict[str, Any] | None:
    state = sr["state"]
    if kind == "SUBMIT":
        if state != RequestStatus.DRAFT.value:
            raise DomainError(ErrorCode.INVALID_INPUT, "NOT_A_DRAFT")
        missing = requests.missing_details(sr)
        if missing:  # a draft can exist without them; submission cannot (FR-11-AC2)
            raise DomainError(
                ErrorCode.INVALID_INPUT, "MISSING_SERVICE_DETAILS", {"missing": missing}
            )
    elif kind == "RESCHEDULE" and state != RequestStatus.CONFIRMED.value:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_RESCHEDULABLE")
    elif kind == "CANCEL" and state not in (
        RequestStatus.REQUESTED.value,
        RequestStatus.CONFIRMED.value,
    ):
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_CANCELLABLE")
    if kind == "CANCEL":
        return None
    if not slot_id:
        raise DomainError(ErrorCode.INVALID_INPUT, "SLOT_REQUIRED")
    try:
        slot = booking.provider(ctx).slot(slot_id)
    except ValueError:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_SLOT") from None
    if not slot.available or slot_id == sr.get("slot_id"):
        raise DomainError(ErrorCode.SLOT_UNAVAILABLE, "SLOT_UNAVAILABLE")
    offer = ctx.table.get(
        keys.household_pk(ctx.household_id), keys.offer_sk(sr["request_id"], slot_id)
    )
    if offer is None or offer["expires_at"] <= iso_utc(ctx.clock.now()):
        raise DomainError(ErrorCode.INVALID_INPUT, "SLOT_NOT_OFFERED")  # list the times again
    return {**slot.as_dict(), "offer_expires_at": offer["expires_at"]}


def _expiry(ctx: OperationContext, now: datetime, slot: dict[str, Any] | None) -> str:
    """The earliest of five minutes, the slot offer's expiry and the session's end (TDD §4.3)."""
    candidates = [iso_utc(now + APPROVAL_TTL)]
    if slot:
        candidates.append(slot["offer_expires_at"])
    session = ctx.table.get(
        keys.household_pk(ctx.household_id), keys.session_sk(ctx.session_id or "")
    )
    if session and session.get("ttl"):
        candidates.append(iso_utc(datetime.fromtimestamp(int(session["ttl"]), tz=UTC)))
    return min(candidates)


def prepare_action(
    ctx: OperationContext, kind: str, request_id: str | None = None, slot_id: str | None = None
) -> dict[str, Any]:
    authorize(ctx.actor, _action(kind), ctx.household_id)
    if not ctx.session_id:
        raise DomainError(ErrorCode.INVALID_INPUT, "SESSION_REQUIRED")
    args = {"kind": kind, "request_id": request_id, "slot_id": slot_id}

    def body(mutation: mutations.Mutation) -> Any:
        now = ctx.clock.now()
        slot = None
        sr = None
        if kind in SERVICE_KINDS:
            require_storage_consent(ctx)  # consent kinds are the one exception (G3-6)
            if not request_id:
                raise DomainError(ErrorCode.INVALID_INPUT, "REQUEST_REQUIRED")
            sr = requests.load(ctx, request_id)
            slot = _validate_service(ctx, kind, sr, slot_id)
            payload = _service_payload(ctx, kind, sr, slot_id)
        else:
            payload = {
                "kind": kind,
                "purpose": CONSENT_KINDS[kind].value,
                "version": CONSENT_VERSION,
            }
        approval_id = new_id()
        pk = keys.household_pk(ctx.household_id)
        approval = {
            "PK": pk,
            "SK": keys.approval_sk(approval_id),
            "kind": "APPROVAL",
            "approval_id": approval_id,
            "action_kind": kind,
            "request_id": request_id,
            "slot": slot,
            "payload": payload,
            "payload_hash": _hash(payload),
            "actor_sub": ctx.actor.sub,
            "session_id": ctx.session_id,
            "created_at": iso_utc(now),
            "expires_at": _expiry(ctx, now, slot),
            "state": "PENDING",
            "ttl": int((now + timedelta(days=1)).timestamp()),
            "version": 1,
        }
        operations = [
            # A newer read-back (a corrected date, say) supersedes the earlier one.
            ctx.table.put_versioned_op(
                {**old, "state": "SUPERSEDED", "version": old["version"] + 1}, old["version"]
            )
            for old in _pending_in_session(ctx)
        ]
        operations += [
            ctx.table.put_new_op(approval),
            ctx.table.put_new_op(
                event_item(
                    ctx,
                    action="APPROVAL_PREPARED",
                    record_sk=approval["SK"],
                    appliance_id=sr["appliance_id"] if sr else None,
                    prior_version=None,
                    new_version=1,
                    extra={"approval_id": approval_id},
                )
            ),
        ]
        result = {
            "pending_ref": approval_id,
            "kind": kind,
            "readback": _readback(kind, payload, slot, sr),
            "expires_at": approval["expires_at"],
            "prepared_at": approval["created_at"],
        }
        try:
            return mutations.commit(ctx, mutation, operations, result)
        except ConflictError as exc:
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    return mutations.run(ctx, "prepare_action", args, body)


def _readback(
    kind: str, payload: dict[str, Any], slot: dict[str, Any] | None, sr: dict[str, Any] | None
) -> dict[str, Any]:
    """The facts the channel's read-back template speaks (FR-12): every material item."""
    facts: dict[str, Any] = {"kind": kind, "demo": True}
    if kind in CONSENT_KINDS:
        return {**facts, "purpose": payload["purpose"]}
    facts["provider"] = PROVIDER_NAME
    if slot:
        facts.update(
            date=slot["date"],
            date_words=requests.date_words(slot["date"]),
            window_words=requests.WINDOW_WORDS[slot["window"]],
        )
    elif sr and sr.get("slot_id"):
        day, _, window = sr["slot_id"].partition("#")
        facts.update(
            date=day,
            date_words=requests.date_words(day),
            window_words=requests.WINDOW_WORDS[window],
        )
    facts["fee_paise"] = payload.get("fee_paise")
    facts["fee_status"] = "ESTIMATE" if payload.get("fee_paise") else "UNKNOWN"
    facts["warranty"] = "UNKNOWN"
    facts["address"] = (payload.get("address") or {}).get("value")
    facts["contact"] = (payload.get("contact") or {}).get("value")
    facts["data_shared"] = payload.get("data_shared")
    return facts


def _mark(
    ctx: OperationContext, approval: dict[str, Any], state: str, **fields: Any
) -> dict[str, Any]:
    updated = {**approval, **fields, "state": state, "version": approval["version"] + 1}
    try:
        ctx.table.put_versioned(updated, approval["version"])
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return updated


def _bound_to_caller(
    ctx: OperationContext, approval: dict[str, Any], same_session: bool = True
) -> None:
    if approval["actor_sub"] != ctx.actor.sub or (
        same_session and approval["session_id"] != ctx.session_id
    ):
        raise DomainError(ErrorCode.AUTH_DENIED, "NOT_YOUR_APPROVAL")


def _parse(moment: str | None) -> datetime | None:
    return datetime.fromisoformat(moment.replace("Z", "+00:00")) if moment else None


def confirm_action(
    ctx: OperationContext,
    pending_ref: str,
    readback_completed_at: str | None = None,
    speech_started_at: str | None = None,
    channel: str = "text",
) -> dict[str, Any]:
    """Trusted: the channel's guard accepted a "yes"; the domain re-checks everything (G3-5)."""
    approval = _load(ctx, pending_ref)
    _bound_to_caller(ctx, approval)
    if approval["state"] == "APPROVED":
        return {
            "approval_id": approval["approval_id"],
            "state": "APPROVED",
            "channel": approval["channel"],
        }
    if approval["state"] == "SUPERSEDED":
        raise DomainError(ErrorCode.APPROVAL_EXPIRED, "SUPERSEDED")
    if approval["state"] in _FINAL_STATES:
        raise DomainError(ErrorCode.APPROVAL_EXPIRED, "NOT_PENDING")
    if approval["expires_at"] <= iso_utc(ctx.clock.now()):
        _mark(ctx, approval, "EXPIRED")
        raise DomainError(ErrorCode.APPROVAL_EXPIRED, "EXPIRED")
    authorize(ctx.actor, _action(approval["action_kind"]), ctx.household_id)
    if channel == "voice":
        finished, started = _parse(readback_completed_at), _parse(speech_started_at)
        latest = ctx.clock.now() + CLIENT_CLOCK_SKEW
        # The read-back can only have finished after it was prepared (not, say, the playback
        # end of an earlier reply), and nothing the client reports may lie in the future (I8).
        if finished is None or finished < _parse(approval["created_at"]) or finished > latest:
            raise DomainError(ErrorCode.AUTH_DENIED, "READBACK_NOT_FINISHED")
        if started is not None and started > latest:
            raise DomainError(ErrorCode.AUTH_DENIED, "SPEECH_TIME_INVALID")
        if started is None or started <= finished:
            raise DomainError(ErrorCode.AUTH_DENIED, "SPOKE_DURING_READBACK")

    kind = approval["action_kind"]
    sr = None
    if kind in SERVICE_KINDS:
        sr = requests.load(ctx, approval["request_id"])
        current = _service_payload(ctx, kind, sr, approval["payload"]["slot_id"])
        if current["fee_paise"] != approval["payload"]["fee_paise"]:
            _mark(ctx, approval, "REFUSED", refusal="FEE_CHANGED")
            raise DomainError(
                ErrorCode.RECORD_CONFLICT, "FEE_CHANGED", {"fee_paise": current["fee_paise"]}
            )
        if _hash(current) != approval["payload_hash"]:
            _mark(ctx, approval, "REFUSED", refusal="PAYLOAD_CHANGED")
            raise DomainError(ErrorCode.RECORD_CONFLICT, "PAYLOAD_CHANGED")
    approved = _mark(
        ctx,
        approval,
        "APPROVED",
        channel=channel,
        readback_completed_at=readback_completed_at,
        speech_started_at=speech_started_at,
        approved_at=iso_utc(ctx.clock.now()),
    )
    ctx.table.put_new(
        event_item(
            ctx,
            action="APPROVAL_CONFIRMED",
            record_sk=approved["SK"],
            appliance_id=sr["appliance_id"] if sr else None,
            prior_version=approval["version"],
            new_version=approved["version"],
            provenance=f"CUSTOMER_{channel.upper()}",
            extra={"approval_id": approved["approval_id"]},
        )
    )
    return {"approval_id": approved["approval_id"], "state": "APPROVED", "channel": channel}


def execute_action(ctx: OperationContext, approval_id: str) -> dict[str, Any]:
    """Trusted: runs an approved action once (operation key `approval_id:<kind>`)."""
    approval = _load(ctx, approval_id)
    _bound_to_caller(ctx, approval, same_session=False)
    if approval["state"] == "EXECUTED":
        return approval["result"]  # a retry gets the original outcome
    if approval["state"] != "APPROVED":
        raise DomainError(ErrorCode.APPROVAL_EXPIRED, "NOT_APPROVED")
    kind = approval["action_kind"]
    authorize(ctx.actor, _action(kind), ctx.household_id)
    if kind in CONSENT_KINDS:
        consent = household.record_consent(
            ctx, CONSENT_KINDS[kind], ConsentDecision.GRANTED, CONSENT_VERSION
        )
        result: dict[str, Any] = {
            "outcome": "CONSENT_RECORDED",
            "purpose": CONSENT_KINDS[kind].value,
            "household": consent,
        }
    else:
        sr = requests.load(ctx, approval["request_id"])
        result = {
            "SUBMIT": booking.submit,
            "RESCHEDULE": booking.reschedule,
            "CANCEL": booking.cancel,
        }[kind](ctx, sr, approval)
    if result["outcome"] not in ("PENDING", "CANCEL_PENDING"):
        _mark(ctx, approval, "EXECUTED", result=result)  # unknown outcomes stay retryable
    return result


def outcome_after_failure(ctx: OperationContext, approval_id: str) -> dict[str, Any]:
    """The outcome to speak when `execute_action` failed or its reply never arrived: read from
    the records (reconciling first), never assumed. NOT_SENT when nothing was dispatched."""
    approval = _load(ctx, approval_id)
    _bound_to_caller(ctx, approval, same_session=False)
    if approval["state"] == "EXECUTED":
        return approval["result"]
    if approval["action_kind"] in CONSENT_KINDS:
        return {"outcome": "NOT_SENT"}
    sr = requests.load(ctx, approval["request_id"])
    if sr["state"] in requests.PENDING_STATES:
        booking.reconcile(ctx, sr)
        sr = requests.load(ctx, sr["request_id"])
    return booking.outcome_for(ctx, approval, sr)


def cancel_pending_action(ctx: OperationContext, pending_ref: str | None = None) -> dict[str, Any]:
    """Trusted: the user said no or stop. The prior committed state is kept (FR-21, FR-22)."""
    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)
    if pending_ref is None:
        current = pending_for_session(ctx)
        if current is None:
            return {"outcome": "NOTHING_PENDING", "pending_ref": None}
        pending_ref = current["pending_ref"]
    approval = _load(ctx, pending_ref)
    _bound_to_caller(ctx, approval)
    if approval["state"] != "PENDING":
        return {"outcome": "NOTHING_PENDING", "pending_ref": pending_ref}
    _mark(ctx, approval, "CANCELLED")
    return {"outcome": "CANCELLED", "pending_ref": pending_ref}
