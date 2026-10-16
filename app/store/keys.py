"""Key builders for the single table (TDD §6.1). Every PK and SK string is built here only."""

from __future__ import annotations

META = "META"
APPLIANCE_PREFIX = "APPL#"
ISSUE_PREFIX = "ISSUE#"
MEMBER_PREFIX = "MEMBER#"
CONSENT_PREFIX = "CONSENT#"
EVENT_PREFIX = "EVT#"
OBSERVATION_INFIX = "#OBS#"


def household_pk(household_id: str) -> str:
    return f"HH#{household_id}"


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
