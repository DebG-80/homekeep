"""`authorize(actor, action, household_id)`: the BRD §4 matrix plus helper grant flags.

Every domain entry point calls this before touching data (TDD §9.3). The household argument is
always the one from the actor's membership, so a household actor can only ever act inside its
own household. Staff access to household records arrives with the staff API (Slice 3), where
assignment can be checked; until then staff are denied household actions.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.errors import DomainError, ErrorCode
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole, StaffGroup


class Action(StrEnum):
    HOUSEHOLD_READ = "household.read"
    CONSENT_RECORD = "consent.record"
    APPLIANCE_READ = "appliance.read"
    APPLIANCE_WRITE = "appliance.write"
    ISSUE_READ = "issue.read"
    ISSUE_WRITE = "issue.write"
    OBSERVATION_WRITE = "observation.write"
    HISTORY_READ = "history.read"
    SERVICE_BOOK = "service.book"
    RESOLUTION_CONFIRM = "resolution.confirm"


# The grant a helper needs for each action. None means owner only.
_HELPER_GRANT: dict[Action, Grant | None] = {
    Action.HOUSEHOLD_READ: Grant.VIEW,
    Action.APPLIANCE_READ: Grant.VIEW,
    Action.ISSUE_READ: Grant.VIEW,
    Action.HISTORY_READ: Grant.VIEW,
    Action.APPLIANCE_WRITE: Grant.EDIT,
    Action.ISSUE_WRITE: Grant.EDIT,
    Action.OBSERVATION_WRITE: Grant.EDIT,
    Action.SERVICE_BOOK: Grant.BOOK,
    Action.CONSENT_RECORD: None,  # owner through a secured flow (BRD §4)
    Action.RESOLUTION_CONFIRM: None,  # helpers only if explicitly delegated; not in H
}


def authorize(actor: Actor, action: Action, household_id: str) -> None:
    if actor.kind is not ActorKind.HOUSEHOLD:
        raise DomainError(ErrorCode.AUTH_DENIED, "STAFF_HOUSEHOLD_ACCESS_NOT_PERMITTED")
    if actor.household_id != household_id:
        raise DomainError(ErrorCode.AUTH_DENIED, "OTHER_HOUSEHOLD")
    if actor.role is HouseholdRole.OWNER:
        return
    needed = _HELPER_GRANT[action]
    if needed is None or needed not in actor.grants:
        raise DomainError(ErrorCode.AUTH_DENIED, "GRANT_MISSING")


class StaffAction(StrEnum):
    QUEUE_VIEW = "staff.queue"
    CASE_VIEW = "staff.case.view"
    VISIT_EVENT = "staff.case.visit_event"  # VISIT_STARTED, WORK_NOTE, VISIT_COMPLETED
    COORDINATION_EVENT = "staff.case.coordination_event"  # NO_SHOW, provider confirm/reject
    CASE_ASSIGN = "staff.case.assign"
    MANUAL_REVIEW = "staff.manual"
    SAFETY_CLEAR = "staff.safety.clear"
    MODEL_VERIFY = "staff.model.verify"


_COORDINATOR_ACTIONS = frozenset(StaffAction) - {StaffAction.MODEL_VERIFY}


def authorize_staff(actor: Actor, action: StaffAction, assignee_sub: str | None = None) -> None:
    """BRD §4 for staff: a technician sees and updates only their own assigned job, a coordinator
    manages cases, a catalog reviewer verifies models, and an admin has no automatic authority."""
    if actor.kind is not ActorKind.STAFF:
        raise DomainError(ErrorCode.AUTH_DENIED, "NOT_STAFF")
    if StaffGroup.COORDINATOR in actor.groups and action in _COORDINATOR_ACTIONS:
        return
    if StaffGroup.TECHNICIAN in actor.groups:
        if action is StaffAction.QUEUE_VIEW:
            return
        if action in (StaffAction.CASE_VIEW, StaffAction.VISIT_EVENT) and assignee_sub == actor.sub:
            return
    if StaffGroup.CATALOG_REVIEWER in actor.groups and action is StaffAction.MODEL_VERIFY:
        return
    raise DomainError(ErrorCode.AUTH_DENIED, "STAFF_ROLE_NOT_PERMITTED")


def authorize_system(actor: Actor, household_id: str) -> None:
    """The sweep's per-household identity may only reconcile that household's requests."""
    if actor.kind is not ActorKind.SYSTEM or actor.household_id != household_id:
        raise DomainError(ErrorCode.AUTH_DENIED, "NOT_SYSTEM")
