"""Audit records for operator actions (BRD §11.4), kept in the `OPS` partition so they outlive a
purged household."""

from __future__ import annotations

from typing import Any

from app.domain.clock import Clock, iso_utc
from app.domain.ids import new_id
from app.store import keys
from app.store.table import Table


def audit(table: Table, clock: Clock, action: str, actor_label: str, **fields: Any) -> None:
    now = iso_utc(clock.now())
    table.put_new(
        {
            "PK": keys.OPS_PK,
            "SK": f"AUDIT#{now}#{new_id()}",
            "kind": "AUDIT",
            "action": action,
            "actor": actor_label,
            "at": now,
            **fields,
        }
    )
