"""State maps from BRD §7.1 (issue) and §7.2 (service request and appointment).

Each map is `(from_state, event) -> to_state`. A pair that is not in the map is an undefined
transition and raises INVALID_INPUT; nothing is ever silently ignored (TDD §7). Guards that need
data (assignment, active sentinel, confirmed reference) are enforced by the service that fires
the event, inside the same transaction.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.errors import DomainError, ErrorCode


class IssueStatus(StrEnum):
    OPEN = "OPEN"
    TRIAGING = "TRIAGING"
    SERVICE_NEEDED = "SERVICE_NEEDED"
    SERVICE_PENDING = "SERVICE_PENDING"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IssueEvent(StrEnum):
    INTAKE_STARTED = "INTAKE_STARTED"
    SERVICE_REQUESTED = "SERVICE_REQUESTED"  # user asks for service, or guidance exhausted
    HAZARD_REPORTED = "HAZARD_REPORTED"
    APPOINTMENT_CONFIRMED = "APPOINTMENT_CONFIRMED"
    VISIT_COMPLETED = "VISIT_COMPLETED"
    CUSTOMER_CONFIRMED_RESOLVED = "CUSTOMER_CONFIRMED_RESOLVED"
    CUSTOMER_SAYS_PERSISTS = "CUSTOMER_SAYS_PERSISTS"
    BOOKING_ENDED = "BOOKING_ENDED"  # rejected, cancelled or failed; guard: no other active booking
    CUSTOMER_CLOSED = "CUSTOMER_CLOSED"
    RECURRED = "RECURRED"


ACTIVE_ISSUE_STATUSES = frozenset(
    {
        IssueStatus.OPEN,
        IssueStatus.TRIAGING,
        IssueStatus.SERVICE_NEEDED,
        IssueStatus.SERVICE_PENDING,
        IssueStatus.AWAITING_CUSTOMER,
    }
)

_S = IssueStatus
_E = IssueEvent

ISSUE_TRANSITIONS: dict[tuple[IssueStatus, IssueEvent], IssueStatus] = {
    (_S.OPEN, _E.INTAKE_STARTED): _S.TRIAGING,
    (_S.OPEN, _E.SERVICE_REQUESTED): _S.SERVICE_NEEDED,
    (_S.TRIAGING, _E.SERVICE_REQUESTED): _S.SERVICE_NEEDED,
    # A hazard moves any unresolved state to SERVICE_NEEDED and sets the safety flag. A valid
    # booking is preserved, so SERVICE_PENDING keeps its status and only gains the flag.
    (_S.OPEN, _E.HAZARD_REPORTED): _S.SERVICE_NEEDED,
    (_S.TRIAGING, _E.HAZARD_REPORTED): _S.SERVICE_NEEDED,
    (_S.SERVICE_NEEDED, _E.HAZARD_REPORTED): _S.SERVICE_NEEDED,
    (_S.SERVICE_PENDING, _E.HAZARD_REPORTED): _S.SERVICE_PENDING,
    (_S.AWAITING_CUSTOMER, _E.HAZARD_REPORTED): _S.SERVICE_NEEDED,
    (_S.SERVICE_NEEDED, _E.APPOINTMENT_CONFIRMED): _S.SERVICE_PENDING,
    # Invariant 8: technician completion awaits the customer; it never resolves the issue.
    (_S.SERVICE_PENDING, _E.VISIT_COMPLETED): _S.AWAITING_CUSTOMER,
    (_S.OPEN, _E.CUSTOMER_CONFIRMED_RESOLVED): _S.RESOLVED,
    (_S.TRIAGING, _E.CUSTOMER_CONFIRMED_RESOLVED): _S.RESOLVED,
    (_S.SERVICE_NEEDED, _E.CUSTOMER_CONFIRMED_RESOLVED): _S.RESOLVED,
    (_S.AWAITING_CUSTOMER, _E.CUSTOMER_CONFIRMED_RESOLVED): _S.RESOLVED,
    (_S.SERVICE_PENDING, _E.CUSTOMER_CONFIRMED_RESOLVED): _S.RESOLVED,  # booking stays active
    (_S.AWAITING_CUSTOMER, _E.CUSTOMER_SAYS_PERSISTS): _S.SERVICE_NEEDED,
    (_S.RESOLVED, _E.CUSTOMER_SAYS_PERSISTS): _S.SERVICE_NEEDED,
    (_S.SERVICE_PENDING, _E.BOOKING_ENDED): _S.SERVICE_NEEDED,
    (_S.RESOLVED, _E.CUSTOMER_CLOSED): _S.CLOSED,
    (_S.CLOSED, _E.RECURRED): _S.OPEN,
}

# Only a customer's answer can produce RESOLVED (BRD §7.1; CLAUDE.md invariant 8).
RESOLVING_EVENTS = frozenset({IssueEvent.CUSTOMER_CONFIRMED_RESOLVED})


class RequestStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CHANGE_PENDING = "CHANGE_PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"


class RequestEvent(StrEnum):
    USER_APPROVED = "USER_APPROVED"
    DISPATCH_STARTED = "DISPATCH_STARTED"
    PROVIDER_ACKNOWLEDGED = "PROVIDER_ACKNOWLEDGED"
    PROVIDER_CONFIRMED = "PROVIDER_CONFIRMED"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    SUBMISSION_FAILED = "SUBMISSION_FAILED"  # confirmed terminal failure; a timeout is not one
    CHANGE_APPROVED = "CHANGE_APPROVED"
    CHANGE_CONFIRMED = "CHANGE_CONFIRMED"
    CHANGE_FAILED = "CHANGE_FAILED"
    VISIT_STARTED = "VISIT_STARTED"
    WORK_COMPLETED = "WORK_COMPLETED"
    USER_ABANDONED = "USER_ABANDONED"
    CANCEL_APPROVED = "CANCEL_APPROVED"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    CANCEL_REJECTED = "CANCEL_REJECTED"


_R = RequestStatus
_Q = RequestEvent

REQUEST_TRANSITIONS: dict[tuple[RequestStatus, RequestEvent], RequestStatus] = {
    (_R.DRAFT, _Q.USER_APPROVED): _R.APPROVED,
    (_R.APPROVED, _Q.DISPATCH_STARTED): _R.SUBMISSION_PENDING,
    (_R.SUBMISSION_PENDING, _Q.PROVIDER_ACKNOWLEDGED): _R.REQUESTED,
    (_R.SUBMISSION_PENDING, _Q.PROVIDER_CONFIRMED): _R.CONFIRMED,
    (_R.REQUESTED, _Q.PROVIDER_CONFIRMED): _R.CONFIRMED,
    (_R.SUBMISSION_PENDING, _Q.PROVIDER_REJECTED): _R.REJECTED,
    (_R.REQUESTED, _Q.PROVIDER_REJECTED): _R.REJECTED,
    (_R.SUBMISSION_PENDING, _Q.SUBMISSION_FAILED): _R.FAILED,
    (_R.CONFIRMED, _Q.CHANGE_APPROVED): _R.CHANGE_PENDING,
    (_R.CHANGE_PENDING, _Q.CHANGE_CONFIRMED): _R.CONFIRMED,
    (_R.CHANGE_PENDING, _Q.CHANGE_FAILED): _R.CONFIRMED,  # original appointment stays active
    (_R.CONFIRMED, _Q.VISIT_STARTED): _R.IN_PROGRESS,
    (_R.IN_PROGRESS, _Q.WORK_COMPLETED): _R.COMPLETED,
    (_R.CONFIRMED, _Q.WORK_COMPLETED): _R.COMPLETED,
    (_R.DRAFT, _Q.USER_ABANDONED): _R.CANCELLED,
    (_R.APPROVED, _Q.USER_ABANDONED): _R.CANCELLED,
    (_R.REQUESTED, _Q.CANCEL_APPROVED): _R.CANCEL_PENDING,
    (_R.CONFIRMED, _Q.CANCEL_APPROVED): _R.CANCEL_PENDING,
    (_R.CANCEL_PENDING, _Q.CANCEL_CONFIRMED): _R.CANCELLED,
    # CANCEL_REJECTED returns to the previous active state, which the request item records;
    # see `cancel_rejected_target`.
}

TERMINAL_REQUEST_STATUSES = frozenset({_R.COMPLETED, _R.REJECTED, _R.FAILED, _R.CANCELLED})


def cancel_rejected_target(previous_active: RequestStatus) -> RequestStatus:
    """CANCEL_PENDING + provider rejects cancellation → the state before CANCEL_PENDING."""
    if previous_active not in (_R.REQUESTED, _R.CONFIRMED):
        raise DomainError(ErrorCode.INVALID_INPUT, "UNDEFINED_TRANSITION")
    return previous_active


class AppointmentStatus(StrEnum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


APPOINTMENT_TRANSITIONS: dict[tuple[AppointmentStatus, str], AppointmentStatus] = {
    (AppointmentStatus.PROPOSED, "CONFIRM"): AppointmentStatus.CONFIRMED,
    (AppointmentStatus.PROPOSED, "CANCEL"): AppointmentStatus.CANCELLED,
    (AppointmentStatus.CONFIRMED, "SUPERSEDE"): AppointmentStatus.SUPERSEDED,
    (AppointmentStatus.CONFIRMED, "COMPLETE"): AppointmentStatus.COMPLETED,
    (AppointmentStatus.CONFIRMED, "CANCEL"): AppointmentStatus.CANCELLED,
}


def next_issue_status(current: IssueStatus, event: IssueEvent) -> IssueStatus:
    try:
        return ISSUE_TRANSITIONS[(current, event)]
    except KeyError:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            "UNDEFINED_TRANSITION",
            {"from": current.value, "event": event.value},
        ) from None


def next_request_status(current: RequestStatus, event: RequestEvent) -> RequestStatus:
    try:
        return REQUEST_TRANSITIONS[(current, event)]
    except KeyError:
        raise DomainError(
            ErrorCode.INVALID_INPUT,
            "UNDEFINED_TRANSITION",
            {"from": current.value, "event": event.value},
        ) from None
