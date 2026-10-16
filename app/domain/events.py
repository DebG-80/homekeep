"""History and audit events (TDD §6.1 `EVT#`, FR-18, FR-28).

Every mutation appends exactly one event in the same transaction as the change, carrying the
correlation ID, the actor and role, the action, the result and the prior and new versions.
Events are append-only: corrections are new events, never edits (FR-18).
"""

from __future__ import annotations

from typing import Any

from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.ids import ordered_id
from app.security.authz import Action, authorize
from app.store import keys


def event_item(
    ctx: OperationContext,
    *,
    action: str,
    record_sk: str,
    appliance_id: str | None,
    prior_version: int | None,
    new_version: int | None,
    provenance: str = "CUSTOMER",
    result: str = "OK",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = ordered_id()
    timestamp = iso_utc(ctx.clock.now())
    return {
        "PK": keys.household_pk(ctx.household_id),
        "SK": keys.event_sk(appliance_id, timestamp, event_id),
        "kind": "EVENT",
        "event_id": event_id,
        "at": timestamp,
        "correlation_id": ctx.correlation_id,
        "actor_sub": ctx.actor.sub,
        "actor_role": ctx.actor.role_label,
        "action": action,
        "result": result,
        "record": record_sk,
        "appliance_id": appliance_id,
        "prior_version": prior_version,
        "new_version": new_version,
        "provenance": provenance,
        **(extra or {}),
    }


def list_events(ctx: OperationContext, appliance_id: str | None) -> list[dict[str, Any]]:
    """Chronological events for one appliance (or household-level events when None)."""
    authorize(ctx.actor, Action.HISTORY_READ, ctx.household_id)
    items = ctx.table.query(keys.household_pk(ctx.household_id), keys.event_prefix(appliance_id))
    return [{k: v for k, v in item.items() if k not in ("PK", "SK")} for item in items]
