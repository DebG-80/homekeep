"""Per-household daily turn cap (TDD §4.4, NFR-12): a conditional counter, one item per day."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.clock import local_date
from app.store import keys
from app.store.table import Table


def take_turn(table: Table, household_id: str, now: datetime, cap: int) -> bool:
    """Count one turn for today (household time). False when today's cap is already reached."""
    day = local_date(now).isoformat()
    return table.increment_below(
        keys.household_pk(household_id),
        f"USAGE#{day}",
        attribute="turns",
        limit=cap,
        ttl=int((now + timedelta(days=2)).timestamp()),
    )
