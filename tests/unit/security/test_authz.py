from __future__ import annotations

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole, StaffGroup
from app.security.authz import Action, authorize

HH = "hh-a"
ALL_GRANTS = frozenset(Grant)


def _household(role: HouseholdRole, grants: frozenset[Grant], household: str = HH) -> Actor:
    return Actor(
        sub="s", kind=ActorKind.HOUSEHOLD, household_id=household, role=role, grants=grants
    )


OWNER = _household(HouseholdRole.OWNER, ALL_GRANTS)
VIEW_HELPER = _household(HouseholdRole.HELPER, frozenset({Grant.VIEW}))
EDIT_HELPER = _household(HouseholdRole.HELPER, frozenset({Grant.VIEW, Grant.EDIT}))
BOOKING_HELPER = _household(
    HouseholdRole.HELPER, frozenset({Grant.VIEW, Grant.EDIT, Grant.BOOK, Grant.UPDATES})
)
OTHER_OWNER = _household(HouseholdRole.OWNER, ALL_GRANTS, household="hh-b")
COORDINATOR = Actor(sub="c", kind=ActorKind.STAFF, groups=frozenset({StaffGroup.COORDINATOR}))
ADMIN = Actor(sub="a", kind=ActorKind.STAFF, groups=frozenset({StaffGroup.ADMIN}))

READS = (Action.HOUSEHOLD_READ, Action.APPLIANCE_READ, Action.ISSUE_READ, Action.HISTORY_READ)
EDITS = (Action.APPLIANCE_WRITE, Action.ISSUE_WRITE, Action.OBSERVATION_WRITE)

MATRIX = [
    *[(OWNER, action, True) for action in Action],
    *[(VIEW_HELPER, action, action in READS) for action in Action],
    *[(EDIT_HELPER, action, action in READS or action in EDITS) for action in Action],
    *[
        (
            BOOKING_HELPER,
            action,
            action in READS or action in EDITS or action is Action.SERVICE_BOOK,
        )
        for action in Action
    ],
    *[(OTHER_OWNER, action, False) for action in Action],  # another household: never
    *[(COORDINATOR, action, False) for action in Action],  # staff: via the Slice 3 staff API
    *[(ADMIN, action, False) for action in Action],  # admin: no automatic household authority
]


def _allowed(actor: Actor, action: Action) -> bool:
    try:
        authorize(actor, action, HH)
    except DomainError as error:
        denied = error
    else:
        return True
    assert denied.code is ErrorCode.AUTH_DENIED
    return False


@pytest.mark.parametrize(("actor", "action", "expected"), MATRIX)
def test_brd4_permission_matrix(actor: Actor, action: Action, expected: bool) -> None:
    assert _allowed(actor, action) is expected


def test_fr20_ac1_view_only_helper_cannot_edit_or_book() -> None:
    for action in READS:
        assert _allowed(VIEW_HELPER, action)
    for action in (*EDITS, Action.SERVICE_BOOK, Action.CONSENT_RECORD, Action.RESOLUTION_CONFIRM):
        assert not _allowed(VIEW_HELPER, action), action
    # Granting sharing or consent is the owner's alone, whatever grants a helper holds.
    assert not _allowed(BOOKING_HELPER, Action.CONSENT_RECORD)
