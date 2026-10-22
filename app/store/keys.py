"""Key builders for the single table (TDD §6.1). Every PK and SK string is built here only."""

from __future__ import annotations

META = "META"
APPLIANCE_PREFIX = "APPL#"
ISSUE_PREFIX = "ISSUE#"
MEMBER_PREFIX = "MEMBER#"
CONSENT_PREFIX = "CONSENT#"
EVENT_PREFIX = "EVT#"
OBSERVATION_INFIX = "#OBS#"


HOUSEHOLD_PREFIX = "HH#"


def household_pk(household_id: str) -> str:
    return f"{HOUSEHOLD_PREFIX}{household_id}"


def member_sk(sub: str) -> str:
    return f"{MEMBER_PREFIX}{sub}"


def user_pk(sub: str) -> str:
    """Membership lookup partition: resolves a token subject to its household."""
    return f"USER#{sub}"


def user_household_sk(household_id: str) -> str:
    return f"HH#{household_id}"


def consent_sk(purpose: str, timestamp: str, record_id: str) -> str:
    """The ordered record ID keeps two decisions at one (fixed) instant distinct and in order."""
    return f"{CONSENT_PREFIX}{purpose}#{timestamp}#{record_id}"


def appliance_sk(appliance_id: str) -> str:
    return f"{APPLIANCE_PREFIX}{appliance_id}"


def nickname_sk(normalised_nickname: str) -> str:
    """Sentinel written in the same transaction as the appliance (no silent duplicates)."""
    return f"NICK#{normalised_nickname}"


def issue_sk(issue_id: str) -> str:
    return f"{ISSUE_PREFIX}{issue_id}"


def observation_sk(issue_id: str, field: str) -> str:
    return f"{ISSUE_PREFIX}{issue_id}{OBSERVATION_INFIX}{field}"


def observation_prefix(issue_id: str) -> str:
    return f"{ISSUE_PREFIX}{issue_id}{OBSERVATION_INFIX}"


def step_sk(issue_id: str, timestamp: str, record_id: str, step_id: str) -> str:
    """One record per offered step outcome (TDD §6.1 `ISSUE#{id}#STEP#{ts}#{step}`)."""
    return f"{ISSUE_PREFIX}{issue_id}#STEP#{timestamp}#{record_id}#{step_id}"


def step_prefix(issue_id: str) -> str:
    return f"{ISSUE_PREFIX}{issue_id}#STEP#"


def operation_sk(operation_key: str) -> str:
    return f"OP#{operation_key}"


def event_sk(appliance_id: str | None, timestamp: str, event_id: str) -> str:
    return f"{EVENT_PREFIX}{appliance_id or '-'}#{timestamp}#{event_id}"


def event_prefix(appliance_id: str | None) -> str:
    return f"{EVENT_PREFIX}{appliance_id or '-'}#"


# --- Slice 3: requests, approvals, provider, staff ------------------------------------------

REQUEST_PREFIX = "SR#"
APPROVAL_PREFIX = "APPROVAL#"
PROVIDER_PK = "PROVIDER#demo"
OPS_PK = "OPS"


def ref_pk(opaque_id: str) -> str:
    """Global lookup from an opaque record ID to its household, for staff routes (G3-1)."""
    return f"REF#{opaque_id}"


def request_sk(request_id: str) -> str:
    return f"{REQUEST_PREFIX}{request_id}"


def appointment_sk(request_id: str, appointment_id: str) -> str:
    return f"{REQUEST_PREFIX}{request_id}#APPT#{appointment_id}"


def appointment_prefix(request_id: str) -> str:
    return f"{REQUEST_PREFIX}{request_id}#APPT#"


def active_sk(request_id: str) -> str:
    """Holds the single confirmed appointment of a request; changed only inside transactions."""
    return f"{REQUEST_PREFIX}{request_id}#ACTIVE"


def offer_sk(request_id: str, slot_id: str) -> str:
    """A slot offered for this request by `list_slots`; it expires 10 minutes later (I7)."""
    return f"{REQUEST_PREFIX}{request_id}#OFFER#{slot_id}"


def open_request_sk(issue_id: str) -> str:
    """At most one open service request per issue (BRD §7.3; I15)."""
    return f"OPENSR#{issue_id}"


def hold_sk(hold_id: str) -> str:
    return f"HOLD#{hold_id}"


def session_sk(session_id: str) -> str:
    return f"SESSION#{session_id}"


def work_sk(request_id: str, work_id: str) -> str:
    return f"{REQUEST_PREFIX}{request_id}#WORK#{work_id}"


def staff_event_sk(case_id: str, event_id: str) -> str:
    """A staff event's de-duplication record, scoped to its case (C1)."""
    return f"SREVT#{case_id}#{event_id}"


def approval_sk(approval_id: str) -> str:
    return f"{APPROVAL_PREFIX}{approval_id}"


def slot_sk(slot_id: str) -> str:
    return f"SLOT#{slot_id}"


def provider_request_sk(operation_key: str) -> str:
    return f"REQ#{operation_key}"


def fault_sk(household_id: str) -> str:
    return f"FAULT#{household_id}"


def staff_pk(sub: str) -> str:
    return f"STAFF#{sub}"


def manual_sk(timestamp: str, item_id: str) -> str:
    return f"MANUAL#{timestamp}#{item_id}"
