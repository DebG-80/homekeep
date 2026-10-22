"""The reconciliation sweep (TDD §4.6; plan P3-1): every 60 s, settle pending requests.

It finds requests through the sparse GSI1 `PENDING` partition and reconciles each with a
per-household SYSTEM identity that may do nothing else. Every write is conditional on the
request's version, so a sweep racing a status read is harmless: the loser simply re-reads.
"""

from __future__ import annotations

import uuid

import anyio

from app.domain import booking
from app.domain.clock import Clock
from app.domain.context import OperationContext
from app.domain.errors import DomainError
from app.logging import log_error, log_event
from app.security.actor import Actor, ActorKind
from app.security.authz import authorize_system
from app.store import keys
from app.store.table import Table

INTERVAL_SECONDS = 60


def sweep_once(table: Table, clock: Clock, faults_enabled: bool) -> int:
    """Reconcile every pending request once. Returns how many reached a definite outcome."""
    settled = 0
    for item in table.query_index("GSI1", "PENDING", forward=True):
        # The identity is scoped to the partition the record lives in, never to a value the
        # record carries; a record that disagrees with its own partition is skipped.
        household_id = item["PK"].removeprefix(keys.HOUSEHOLD_PREFIX)
        actor = Actor(sub="system:reconciler", kind=ActorKind.SYSTEM, household_id=household_id)
        try:
            authorize_system(actor, item.get("household_id", ""))
        except DomainError:
            log_event("SWEEP", result="SCOPE_MISMATCH")
            continue
        ctx = OperationContext(
            actor=actor,
            table=table,
            clock=clock,
            correlation_id=f"corr-sweep-{uuid.uuid4().hex}",
            turn_id=f"sweep-{uuid.uuid4().hex}",
            faults_enabled=faults_enabled,
        )
        try:
            if booking.reconcile(ctx, item) is not None:
                settled += 1
        except DomainError:
            continue  # another path settled it first
        except Exception as exc:  # one bad request must not stop the rest of the round
            log_error("SWEEP_ITEM_FAILED", exc, correlation_id=ctx.correlation_id)
    if settled:
        log_event("SWEEP", result="SETTLED")
    return settled


async def run_sweep(table: Table, clock: Clock, faults_enabled: bool) -> None:
    while True:
        await anyio.sleep(INTERVAL_SECONDS)
        try:
            await anyio.to_thread.run_sync(sweep_once, table, clock, faults_enabled)
        except Exception as exc:  # a bad round must never stop the next one
            log_error("SWEEP_FAILED", exc)
