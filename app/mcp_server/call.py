"""Per-call plumbing for every tool: who is calling, under which turn, and the envelope.

The household comes only from the verified token's subject → membership lookup, re-read on
every call (invariant 1). Domain code is synchronous (boto3), so it runs in a worker thread.
Nothing unexpected reaches the client: no stack traces, no other tenant's identifiers.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from typing import Any

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context

from app.domain.context import OperationContext, failure, ok
from app.domain.errors import DomainError, ErrorCode
from app.logging import log_error, log_event
from app.runtime import Runtime
from app.security.attestation import ATTEST_HEADER
from app.security.membership import resolve_actor
from app.security.verifier import verified_from

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _header_id(headers: Any, name: str) -> str | None:
    value = headers.get(name) if headers is not None else None
    return value if value and _SAFE_ID.match(value) else None


async def run_tool(
    runtime: Runtime,
    mcp_ctx: Context,
    action: str,
    fn: Callable[..., Any],
    *args: Any,
    trusted: bool = False,
    attested_args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    request = mcp_ctx.request_context.request
    headers = getattr(request, "headers", None)
    correlation_id = _header_id(headers, "x-correlation-id") or f"corr-{uuid.uuid4().hex}"
    # P2-3: external clients send no turn ID; a generated one keeps mutations working.
    turn_id = _header_id(headers, "x-hk-turn-id") or f"gen-{uuid.uuid4().hex}"
    session_id = _header_id(headers, "x-hk-session-id")
    attestation = headers.get(ATTEST_HEADER) if headers is not None else None
    access = get_access_token()
    started = time.monotonic()

    def work() -> dict[str, Any]:
        if access is None:  # the transport refuses these first; this is belt and braces
            return _bare_failure(correlation_id, DomainError(ErrorCode.AUTH_DENIED, "NO_TOKEN"))
        verified = verified_from(access)
        try:
            if trusted:
                runtime.attestor.verify(
                    attestation,
                    verified.sub,
                    session_id or "",
                    turn_id,
                    action,
                    attested_args or {},
                )
            actor = resolve_actor(runtime.table, verified)
        except DomainError as error:
            return _bare_failure(correlation_id, error)
        ctx = OperationContext(
            actor=actor,
            table=runtime.table,
            clock=runtime.clock,
            correlation_id=correlation_id,
            turn_id=turn_id,
            session_id=session_id,
            faults_enabled=runtime.settings.faults_enabled,
        )
        try:
            data = fn(ctx, *args, **kwargs)
        except DomainError as error:
            return failure(ctx, error)
        version = data.get("version") if isinstance(data, dict) else None
        return ok(ctx, data, version)

    try:
        envelope = await anyio.to_thread.run_sync(work)
    except Exception as exc:  # never leak internals; the correlation ID lets support find the log
        log_error("TOOL_FAILED", exc, correlation_id=correlation_id, action=action)
        envelope = _bare_failure(
            correlation_id, DomainError(ErrorCode.RESULT_UNKNOWN, "INTERNAL_ERROR")
        )
    log_event(
        "TOOL_CALL",
        correlation_id=correlation_id,
        sub=access.subject if access else None,
        action=action,
        result=envelope["status"],
        error_code=(envelope.get("error") or {}).get("code"),
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return envelope


def _bare_failure(correlation_id: str, error: DomainError) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "correlation_id": correlation_id,
        "version": None,
        "error": {
            "code": error.code.value,
            "reason": error.reason,
            "message": error.message,
            "support_reference": correlation_id,
            "details": {},
        },
    }
