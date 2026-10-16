"""Typed domain errors (TDD §5.5, BRD §9.4).

Codes come only from the TDD list plus CONSENT_REQUIRED. Messages are customer-safe: no
identifiers, no stack traces, nothing from another household. The support reference is the
correlation ID, which the result envelope adds (app/domain/context.py).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    AUTH_DENIED = "AUTH_DENIED"
    INVALID_INPUT = "INVALID_INPUT"
    RECORD_CONFLICT = "RECORD_CONFLICT"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    NO_APPROVED_GUIDANCE = "NO_APPROVED_GUIDANCE"
    SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"


# Short and plain (elder-voice-copy): at most two sentences and one question, no jargon or IDs.
CUSTOMER_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.AUTH_DENIED: "I can't do that from this account.",
    ErrorCode.INVALID_INPUT: "I didn't quite get that. Could you say it another way?",
    ErrorCode.RECORD_CONFLICT: "Something changed while we were talking. Let me check again.",
    ErrorCode.APPROVAL_EXPIRED: "That confirmation has timed out. Shall I read it to you again?",
    ErrorCode.NO_APPROVED_GUIDANCE: (
        "I don't have checked advice for this. I can arrange a demo technician visit instead."
    ),
    ErrorCode.SLOT_UNAVAILABLE: "That time is no longer available.",
    ErrorCode.PROVIDER_UNAVAILABLE: "The service desk isn't answering right now.",
    ErrorCode.RESULT_UNKNOWN: "I haven't heard back yet, so this is still pending.",
    ErrorCode.CONSENT_REQUIRED: "I need your permission to save this first.",
}


# Per-reason wording where the code's default would mislead (for example, asking the elder to
# rephrase when nothing was misheard). Same rules as above.
REASON_MESSAGES: dict[str, str] = {
    "DUPLICATE_NICKNAME": "You already have one with that name. What else shall we call it?",
    "NOT_FOUND": "I couldn't find that one. Which appliance do you mean?",
    "UNDEFINED_TRANSITION": "I can't do that for this problem right now.",
    "NOT_AN_ACTIVE_ISSUE": "That problem isn't open any more. Is this a new problem?",
    "NO_INTAKE_FOR_CATEGORY": "I don't have questions for this appliance yet.",
    "TURN_ID_REQUIRED": "Something went wrong on my side. Please try again.",
    "UNSUPPORTED_CATEGORY": "I can help with ACs, fridges and TVs. Which one is it?",
    "NICKNAME_REQUIRED": "What would you like to call it?",
    "NICKNAME_TOO_LONG": "That name is a bit long. Could you give me a shorter one?",
    "SYMPTOM_REQUIRED": "What seems to be the problem?",
    "STALE_VERSION": "Something changed while we were talking. Let me check again.",
    "SAFETY_FLAG": (
        "For your safety, I won't suggest any checks now. "
        "I'll help you get a demo technician to look at it."
    ),
}


class DomainError(Exception):
    """A typed, customer-safe failure. `details` must hold only this household's safe values."""

    def __init__(self, code: ErrorCode, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
        self.details = details or {}

    @property
    def message(self) -> str:
        return REASON_MESSAGES.get(self.reason, CUSTOMER_MESSAGES[self.code])


class ConflictError(DomainError):
    """A conditional write or transaction failed. `failed_indexes` names the failed operations."""

    def __init__(self, failed_indexes: tuple[int, ...], reason: str = "CONDITION_FAILED") -> None:
        super().__init__(ErrorCode.RECORD_CONFLICT, reason)
        self.failed_indexes = failed_indexes
