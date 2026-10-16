from __future__ import annotations

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.domain.state import (
    APPOINTMENT_TRANSITIONS,
    ISSUE_TRANSITIONS,
    REQUEST_TRANSITIONS,
    AppointmentStatus,
    IssueEvent,
    IssueStatus,
    RequestEvent,
    RequestStatus,
    cancel_rejected_target,
    next_request_status,
)

S, E = IssueStatus, IssueEvent
R, Q = RequestStatus, RequestEvent


def test_issue_map_matches_brd_7_1() -> None:
    unresolved = (S.OPEN, S.TRIAGING, S.SERVICE_NEEDED, S.AWAITING_CUSTOMER)
    expected = {
        (S.OPEN, E.INTAKE_STARTED): S.TRIAGING,  # assistant starts approved intake
        (S.OPEN, E.SERVICE_REQUESTED): S.SERVICE_NEEDED,  # user requests service
        (S.TRIAGING, E.SERVICE_REQUESTED): S.SERVICE_NEEDED,  # or guidance exhausted
        # New reported hazard: SERVICE_NEEDED from any unresolved state, preserving a valid
        # booking. Accepted interpretation D1-3 (HANDOFF row 19), not the BRD's literal text:
        # SERVICE_PENDING keeps its status and only gains the safety flag.
        **{(state, E.HAZARD_REPORTED): S.SERVICE_NEEDED for state in unresolved},
        (S.SERVICE_PENDING, E.HAZARD_REPORTED): S.SERVICE_PENDING,
        (S.SERVICE_NEEDED, E.APPOINTMENT_CONFIRMED): S.SERVICE_PENDING,
        (S.SERVICE_PENDING, E.VISIT_COMPLETED): S.AWAITING_CUSTOMER,  # no resolution inference
        **{(state, E.CUSTOMER_CONFIRMED_RESOLVED): S.RESOLVED for state in unresolved},
        (S.SERVICE_PENDING, E.CUSTOMER_CONFIRMED_RESOLVED): S.RESOLVED,  # before the visit
        (S.AWAITING_CUSTOMER, E.CUSTOMER_SAYS_PERSISTS): S.SERVICE_NEEDED,
        (S.RESOLVED, E.CUSTOMER_SAYS_PERSISTS): S.SERVICE_NEEDED,
        (S.SERVICE_PENDING, E.BOOKING_ENDED): S.SERVICE_NEEDED,
        (S.RESOLVED, E.CUSTOMER_CLOSED): S.CLOSED,
        (S.CLOSED, E.RECURRED): S.OPEN,
    }
    assert expected == ISSUE_TRANSITIONS
    # Only a customer's answer ever produces RESOLVED.
    resolving = {event for (_, event), to in ISSUE_TRANSITIONS.items() if to is S.RESOLVED}
    assert resolving == {E.CUSTOMER_CONFIRMED_RESOLVED}


def test_service_and_appointment_maps_match_brd_7_2() -> None:
    expected = {
        (R.DRAFT, Q.USER_APPROVED): R.APPROVED,
        (R.APPROVED, Q.DISPATCH_STARTED): R.SUBMISSION_PENDING,
        (R.SUBMISSION_PENDING, Q.PROVIDER_ACKNOWLEDGED): R.REQUESTED,
        (R.SUBMISSION_PENDING, Q.PROVIDER_CONFIRMED): R.CONFIRMED,
        (R.REQUESTED, Q.PROVIDER_CONFIRMED): R.CONFIRMED,
        (R.SUBMISSION_PENDING, Q.PROVIDER_REJECTED): R.REJECTED,
        (R.REQUESTED, Q.PROVIDER_REJECTED): R.REJECTED,
        (R.SUBMISSION_PENDING, Q.SUBMISSION_FAILED): R.FAILED,
        (R.CONFIRMED, Q.CHANGE_APPROVED): R.CHANGE_PENDING,
        (R.CHANGE_PENDING, Q.CHANGE_CONFIRMED): R.CONFIRMED,
        (R.CHANGE_PENDING, Q.CHANGE_FAILED): R.CONFIRMED,
        (R.CONFIRMED, Q.VISIT_STARTED): R.IN_PROGRESS,
        (R.IN_PROGRESS, Q.WORK_COMPLETED): R.COMPLETED,
        (R.CONFIRMED, Q.WORK_COMPLETED): R.COMPLETED,
        (R.DRAFT, Q.USER_ABANDONED): R.CANCELLED,
        (R.APPROVED, Q.USER_ABANDONED): R.CANCELLED,
        (R.REQUESTED, Q.CANCEL_APPROVED): R.CANCEL_PENDING,
        (R.CONFIRMED, Q.CANCEL_APPROVED): R.CANCEL_PENDING,
        (R.CANCEL_PENDING, Q.CANCEL_CONFIRMED): R.CANCELLED,
    }
    assert expected == REQUEST_TRANSITIONS
    assert cancel_rejected_target(R.CONFIRMED) is R.CONFIRMED
    assert cancel_rejected_target(R.REQUESTED) is R.REQUESTED
    with pytest.raises(DomainError):
        cancel_rejected_target(R.DRAFT)

    # A timeout is not a terminal failure: there is no event that moves pending to FAILED
    # other than a confirmed terminal failure, and terminal requests never move again.
    for terminal in (R.COMPLETED, R.REJECTED, R.FAILED, R.CANCELLED):
        assert not [k for k in REQUEST_TRANSITIONS if k[0] is terminal]
    with pytest.raises(DomainError) as caught:
        next_request_status(R.COMPLETED, Q.PROVIDER_CONFIRMED)
    assert caught.value.code is ErrorCode.INVALID_INPUT

    A = AppointmentStatus
    assert {
        (A.PROPOSED, "CONFIRM"): A.CONFIRMED,
        (A.PROPOSED, "CANCEL"): A.CANCELLED,
        (A.CONFIRMED, "SUPERSEDE"): A.SUPERSEDED,
        (A.CONFIRMED, "COMPLETE"): A.COMPLETED,
        (A.CONFIRMED, "CANCEL"): A.CANCELLED,
    } == APPOINTMENT_TRANSITIONS
