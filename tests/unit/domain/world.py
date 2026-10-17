"""Shared builders for domain tests: households, actors and per-call contexts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.domain.clock import FixedClock
from app.domain.context import OperationContext
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole, StaffGroup
from app.store import keys
from app.store.table import Table, from_dynamo

HH_A = "hh-a"
HH_B = "hh-b"


def put_household(table: Table, household_id: str, *, storage: str | None = "GRANTED") -> None:
    table.put(
        {
            "PK": keys.household_pk(household_id),
            "SK": keys.META,
            "kind": "HOUSEHOLD",
            "household_id": household_id,
            "locale": "en-IN",
            "timezone": "Asia/Kolkata",
            "storage_consent": storage,
            "sharing_consent": None,
            "version": 1,
        }
    )


def actor(household_id: str, role: HouseholdRole, *grants: Grant, sub: str | None = None) -> Actor:
    return Actor(
        sub=sub or f"sub-{household_id}-{role.value.lower()}-{'-'.join(sorted(grants)) or 'none'}",
        kind=ActorKind.HOUSEHOLD,
        household_id=household_id,
        role=role,
        grants=frozenset(grants) if grants else frozenset(Grant),
    )


OWNER_A = actor(HH_A, HouseholdRole.OWNER, sub="sub-a-owner")
VIEW_HELPER_A = actor(HH_A, HouseholdRole.HELPER, Grant.VIEW, sub="sub-a-view")
EDIT_HELPER_A = actor(HH_A, HouseholdRole.HELPER, Grant.VIEW, Grant.EDIT, sub="sub-a-edit")
OWNER_B = actor(HH_B, HouseholdRole.OWNER, sub="sub-b-owner")
TECHNICIAN = Actor(sub="sub-tech", kind=ActorKind.STAFF, groups=frozenset({StaffGroup.TECHNICIAN}))


@dataclass
class World:
    table: Table
    clock: FixedClock

    def ctx(
        self, who: Actor, turn_id: str | None = None, correlation_id: str | None = None
    ) -> OperationContext:
        """A fresh call context. Each call is a new turn unless `turn_id` is given."""
        return OperationContext(
            actor=who,
            table=self.table,
            clock=self.clock,
            correlation_id=correlation_id or f"corr-{uuid.uuid4().hex[:8]}",
            turn_id=turn_id or f"turn-{uuid.uuid4().hex[:8]}",
            session_id="session-1",
            faults_enabled=True,  # domain tests drive the simulator's fault matrix
        )

    def items(self, household_id: str, prefix: str = "") -> list[dict[str, Any]]:
        return self.table.query(keys.household_pk(household_id), prefix)

    def snapshot(self) -> list[dict[str, Any]]:
        response = self.table.client.scan(TableName=self.table.name)
        return sorted((from_dynamo(i) for i in response["Items"]), key=lambda i: (i["PK"], i["SK"]))
