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
        "I don't have checked advice for this. I can arrange a technician instead."
    ),
    ErrorCode.SLOT_UNAVAILABLE: "That time is no longer available.",
    ErrorCode.PROVIDER_UNAVAILABLE: "The service desk isn't answering right now.",
    ErrorCode.RESULT_UNKNOWN: "I haven't heard back yet, so this is still pending.",
    ErrorCode.CONSENT_REQUIRED: "I need your permission to save this first.",
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
        return CUSTOMER_MESSAGES[self.code]


class ConflictError(DomainError):
    """A conditional write or transaction failed. `failed_indexes` names the failed operations."""

    def __init__(self, failed_indexes: tuple[int, ...], reason: str = "CONDITION_FAILED") -> None:
        super().__init__(ErrorCode.RECORD_CONFLICT, reason)
        self.failed_indexes = failed_indexes
