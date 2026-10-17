"""Domain errors as HTTP responses for the REST APIs (turn API and staff API).

401 means "who are you?": no token or one that fails verification. 403 means "you may not": a
valid token whose holder lacks the role, scope, grant or membership (Slice 2 review N1).
"""

from __future__ import annotations

import re

from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, ErrorCode

UNAUTHENTICATED = frozenset(
    {
        "NO_TOKEN",
        "MALFORMED_TOKEN",
        "UNSUPPORTED_ALGORITHM",
        "UNKNOWN_KEY",
        "JWKS_UNAVAILABLE",
        "TOKEN_EXPIRED",
        "WRONG_ISSUER",
        "INVALID_TOKEN",
        "WRONG_TOKEN_USE",
        "UNKNOWN_CLIENT",
    }
)


def bearer(authorization: str | None) -> str | None:
    match = re.match(r"^Bearer\s+(\S+)$", authorization or "")
    return match.group(1) if match else None


def status_for(error: DomainError) -> int:
    if error.code is ErrorCode.AUTH_DENIED:
        return 401 if error.reason in UNAUTHENTICATED else 403
    if error.code is ErrorCode.INVALID_INPUT:
        return 404 if error.reason == "NOT_FOUND" else 400
    if error.code is ErrorCode.RECORD_CONFLICT:
        return 409
    return 400


def error_response(error: DomainError) -> JSONResponse:
    body = {"error": {"code": error.code.value, "reason": error.reason, "message": error.message}}
    return JSONResponse(body, status_code=status_for(error))
