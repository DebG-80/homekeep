"""Household members and their grants (FR-20; TDD §9.1; plan P4-3, G4-5).

The owner manages helpers: changes their grants or revokes them. Helpers see only their own
membership (BRD §11.2). Grants live here, not in token claims, and membership is read afresh on
every call, so a revoked helper's existing token is refused on its next request. Revocation also
cancels the helper's approvals that have not been sent to the provider, in the same transaction;
bookings already made or in flight for the household stay intact (FR-20-AC2).
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.security.actor import Grant, HouseholdRole
from app.security.authz import Action, authorize
from app.store import keys

ACTIVE, REVOKED = "ACTIVE", "REVOKED"
_OPEN_APPROVALS = frozenset({"PENDING", "APPROVED"})


def member_ref(household_id: str, sub: str) -> str:
    """An opaque reference for a membership: the Cognito subject never leaves the server or
    reaches a URL or an access log (TDD §10.2; plan G4-13)."""
    return hashlib.sha256(f"{household_id}|{sub}".encode()).hexdigest()[:24]


def _view(member: dict[str, Any], viewer_sub: str) -> dict[str, Any]:
    return {
        "member_ref": member_ref(member["PK"].removeprefix("HH#"), member["sub"]),
        "display_name": member.get("display_name") or "Household member",
        "role": member["role"],
        "grants": list(member.get("grants", [])),
        "status": member["status"],
        "is_you": member["sub"] == viewer_sub,
    }


def list_members(ctx: OperationContext) -> dict[str, Any]:
    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)
    members = ctx.table.query(keys.household_pk(ctx.household_id), keys.MEMBER_PREFIX)
    if ctx.actor.role is not HouseholdRole.OWNER:
        members = [m for m in members if m["sub"] == ctx.actor.sub]  # only their own grants
    return {"members": [_view(m, ctx.actor.sub) for m in members]}


def _helper(ctx: OperationContext, ref: str) -> dict[str, Any]:
    authorize(ctx.actor, Action.MEMBER_MANAGE, ctx.household_id)
    member = next(
        (
            m
            for m in ctx.table.query(keys.household_pk(ctx.household_id), keys.MEMBER_PREFIX)
            if member_ref(ctx.household_id, m["sub"]) == ref
        ),
        None,
    )
    if member is None:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    if member["role"] == HouseholdRole.OWNER.value:
        raise DomainError(ErrorCode.INVALID_INPUT, "OWNER_NOT_CHANGEABLE")
    return member


def _event(
    ctx: OperationContext, action: str, member: dict[str, Any], updated: dict[str, Any]
) -> dict[str, Any]:
    return ctx.table.put_new_op(
        event_item(
            ctx,
            action=action,
            record_sk=member["SK"],
            appliance_id=None,
            prior_version=member["version"],
            new_version=updated["version"],
        )
    )


def set_grants(ctx: OperationContext, ref: str, grants: list[str]) -> dict[str, Any]:
    """The owner changes an active helper's grants, never beyond the owner's own."""
    member = _helper(ctx, ref)
    try:
        wanted = sorted({Grant(g) for g in grants}, key=list(Grant).index)
    except ValueError:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_GRANT") from None
    if Grant.VIEW not in wanted:
        raise DomainError(ErrorCode.INVALID_INPUT, "GRANT_NEEDS_VIEW")
    if not set(wanted) <= ctx.actor.grants:
        raise DomainError(ErrorCode.INVALID_INPUT, "BEYOND_OWNER")
    if member["status"] != ACTIVE:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_ACTIVE")
    updated = {
        **member,
        "grants": [g.value for g in wanted],
        "updated_at": iso_utc(ctx.clock.now()),
        "version": member["version"] + 1,
    }
    try:
        ctx.table.transact(
            [
                ctx.table.put_versioned_op(updated, member["version"]),
                _event(ctx, "MEMBER_GRANTS_CHANGED", member, updated),
            ]
        )
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return _view(updated, ctx.actor.sub)


def _dispatched(ctx: OperationContext, approval: dict[str, Any]) -> bool:
    """An approved action already sent to the provider carries on: cancelling only its record
    would leave it saying CANCELLED while the booking goes ahead."""
    if approval["state"] != "APPROVED" or not approval.get("request_id"):
        return False
    request = ctx.table.get(
        keys.household_pk(ctx.household_id), keys.request_sk(approval["request_id"])
    )
    return bool(request) and request.get("active_approval_id") == approval["approval_id"]


def revoke(ctx: OperationContext, ref: str) -> tuple[dict[str, Any], str]:
    """Revoke a helper. Returns their view and sign-in name (for Cognito global sign-out)."""
    member = _helper(ctx, ref)
    display_name = member.get("display_name") or member["sub"]
    if member["status"] == REVOKED:
        return _view(member, ctx.actor.sub), display_name
    pk = keys.household_pk(ctx.household_id)
    now = iso_utc(ctx.clock.now())
    updated = {**member, "status": REVOKED, "revoked_at": now, "version": member["version"] + 1}
    open_approvals = [
        a
        for a in ctx.table.query(pk, keys.APPROVAL_PREFIX)
        if a["actor_sub"] == member["sub"]
        and a["state"] in _OPEN_APPROVALS
        and not _dispatched(ctx, a)
    ]
    try:
        ctx.table.transact(
            [
                ctx.table.put_versioned_op(updated, member["version"]),
                *(
                    ctx.table.put_versioned_op(
                        {
                            **a,
                            "state": "CANCELLED",
                            "refusal": "MEMBER_REVOKED",
                            "version": a["version"] + 1,
                        },
                        a["version"],
                    )
                    for a in open_approvals
                ),
                _event(ctx, "MEMBER_REVOKED", member, updated),
            ]
        )
    except ConflictError as exc:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc
    return _view(updated, ctx.actor.sub), display_name
