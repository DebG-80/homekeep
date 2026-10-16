"""Per-call context for domain services, and the result envelope tools return (TDD §5.4, §5.5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.clock import Clock
from app.domain.errors import DomainError, ErrorCode
from app.security.actor import Actor
from app.store.table import Table


@dataclass(frozen=True)
class OperationContext:
    actor: Actor
    table: Table
    clock: Clock
    correlation_id: str
    turn_id: str | None = None
    session_id: str | None = None

    @property
    def household_id(self) -> str:
        """The actor's household, from the membership lookup. Staff have none here."""
        if not self.actor.household_id:
            raise DomainError(ErrorCode.AUTH_DENIED, "NO_HOUSEHOLD_SCOPE")
        return self.actor.household_id

    def require_turn_id(self) -> str:
        if not self.turn_id:
            raise DomainError(ErrorCode.INVALID_INPUT, "TURN_ID_REQUIRED")
        return self.turn_id


def ok(ctx: OperationContext, data: Any, version: int | None = None) -> dict[str, Any]:
    return {"status": "OK", "correlation_id": ctx.correlation_id, "version": version, "data": data}


def failure(ctx: OperationContext, error: DomainError) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "correlation_id": ctx.correlation_id,
        "version": None,
        "error": {
            "code": error.code.value,
            "reason": error.reason,
            "message": error.message,
            "support_reference": ctx.correlation_id,
            "details": error.details,
        },
    }
