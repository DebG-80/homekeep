"""Token subject → household membership and grants, read from DynamoDB on every call.

This is the only place a household ID enters the system (CLAUDE.md invariant 1). Grants live in
DynamoDB rather than token claims, so revocation takes effect on the next request (FR-20-AC2).
"""

from __future__ import annotations

from app.domain.errors import DomainError, ErrorCode
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole, StaffGroup
from app.security.tokens import VerifiedToken
from app.store import keys
from app.store.table import Table

ACTIVE = "ACTIVE"
_STAFF_GROUPS = {group.value for group in StaffGroup}


def resolve_actor(table: Table, token: VerifiedToken) -> Actor:
    groups = frozenset(StaffGroup(g) for g in token.groups if g in _STAFF_GROUPS)
    links = table.query(keys.user_pk(token.sub), "HH#")
    if len(links) > 1:
        raise DomainError(ErrorCode.AUTH_DENIED, "MULTIPLE_HOUSEHOLDS")
    if links:
        household_id = links[0]["household_id"]
        member = table.get(keys.household_pk(household_id), keys.member_sk(token.sub))
        if member is not None and member.get("status") == ACTIVE:
            return Actor(
                sub=token.sub,
                kind=ActorKind.HOUSEHOLD,
                household_id=household_id,
                role=HouseholdRole(member["role"]),
                grants=frozenset(Grant(g) for g in member.get("grants", [])),
            )
    if groups:
        return Actor(sub=token.sub, kind=ActorKind.STAFF, groups=groups)
    raise DomainError(ErrorCode.AUTH_DENIED, "NO_ACTIVE_MEMBERSHIP")
