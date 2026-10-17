"""The authenticated actor, built from a verified token plus a fresh membership read.

`household_id` is filled only by `membership.resolve_actor`, never from tool or API input
(CLAUDE.md invariant 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ActorKind(StrEnum):
    HOUSEHOLD = "HOUSEHOLD"
    STAFF = "STAFF"
    SYSTEM = "SYSTEM"  # the reconciliation sweep (P3-1): may only reconcile


class HouseholdRole(StrEnum):
    OWNER = "OWNER"
    HELPER = "HELPER"


class Grant(StrEnum):
    VIEW = "view"
    EDIT = "edit"
    BOOK = "book"
    UPDATES = "updates"


class StaffGroup(StrEnum):
    COORDINATOR = "coordinator"
    TECHNICIAN = "technician"
    CATALOG_REVIEWER = "catalog_reviewer"
    ADMIN = "admin"


@dataclass(frozen=True)
class Actor:
    sub: str
    kind: ActorKind
    household_id: str | None = None
    role: HouseholdRole | None = None
    grants: frozenset[Grant] = field(default_factory=frozenset)
    groups: frozenset[StaffGroup] = field(default_factory=frozenset)

    @property
    def role_label(self) -> str:
        """For events and logs: the household role, or the staff groups."""
        if self.kind is ActorKind.HOUSEHOLD and self.role:
            return self.role.value
        if self.kind is ActorKind.SYSTEM:
            return "SYSTEM"
        return ",".join(sorted(g.value for g in self.groups)) or "unknown"
