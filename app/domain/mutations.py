"""The idempotent-mutation pattern every domain write follows (TDD §5.5, §6.2).

1. `run` derives the operation key server-side and returns the stored result on a replay.
2. The service body builds its conditional operations (records, sentinel, event).
3. `commit` adds the `OP#` record to the same transaction and writes it all at once, so the
   result is acknowledged only after it is stored (invariant 4).

A retry can read the ledger just before the original commits and then trip over the original's
own write (its nickname sentinel, its version bump, its now-active issue). So whenever the body
raises or returns without committing, `run` reads the ledger again and replays the original's
result if there is one. If a concurrent duplicate commits first, our `OP#` put fails and `commit`
returns the stored result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError
from app.store import keys, ops


@dataclass
class Mutation:
    key: str
    payload_hash: str
    replayed: Any | None
    committed: bool = False

    @property
    def is_replay(self) -> bool:
        return self.replayed is not None


def start(ctx: OperationContext, action: str, args: dict[str, Any]) -> Mutation:
    key = ops.operation_key(ctx.household_id, ctx.require_turn_id(), action, args)
    hashed = ops.payload_hash(args)
    return Mutation(key, hashed, ops.lookup(ctx.table, ctx.household_id, key, hashed))


def _stored(ctx: OperationContext, mutation: Mutation) -> Any | None:
    return ops.lookup(ctx.table, ctx.household_id, mutation.key, mutation.payload_hash)


def run(
    ctx: OperationContext,
    action: str,
    args: dict[str, Any],
    body: Callable[[Mutation], Any],
) -> Any:
    mutation = start(ctx, action, args)
    if mutation.is_replay:
        return mutation.replayed
    try:
        result = body(mutation)
    except DomainError:
        stored = _stored(ctx, mutation)
        if stored is not None:
            return stored  # the original committed while this retry was checking
        raise
    if not mutation.committed:
        # A read-only outcome (for example NEEDS_CHOICE) may only be the original's own effect.
        stored = _stored(ctx, mutation)
        if stored is not None:
            return stored
    return result


def commit(
    ctx: OperationContext,
    mutation: Mutation,
    operations: list[dict[str, Any]],
    result: Any,
) -> Any:
    op_record = ops.operation_item(
        ctx.household_id, mutation.key, mutation.payload_hash, result, ctx.clock.now()
    )
    op_index = len(operations)
    try:
        ctx.table.transact([*operations, ctx.table.put_new_op(op_record)])
    except ConflictError as exc:
        if op_index in exc.failed_indexes:
            stored = _stored(ctx, mutation)
            if stored is not None:
                mutation.committed = True
                return stored
        raise
    mutation.committed = True
    return result


def storage_consent_check(ctx: OperationContext) -> dict[str, Any]:
    """Condition that storage consent is still granted, evaluated inside the transaction (FR-01)."""
    return ctx.table.condition_op(
        keys.household_pk(ctx.household_id),
        keys.META,
        "#consent = :granted",
        {":granted": "GRANTED"},
        {"#consent": "storage_consent"},
    )
