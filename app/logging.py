"""Structured JSON logs restricted to the TDD §10.2 allowlist (NFR-07).

Only allowlisted fields are written; the subject is hashed; transcripts, addresses, documents and
tokens are dropped whatever the caller passes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from typing import Any

LOGGER = logging.getLogger("homekeep")
ALLOWED_FIELDS = frozenset(
    {
        "correlation_id",
        "actor",
        "role",
        "action",
        "result",
        "error_code",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "cache_tokens",
        "model_id",
    }
)


def hash_subject(sub: str) -> str:
    return hashlib.sha256(sub.encode()).hexdigest()[:16]


class _StderrHandler(logging.Handler):
    """Writes each record's message (already JSON) to the current stderr, one line each."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stderr.write(record.getMessage() + "\n")
        except Exception:  # logging must never break a request
            self.handleError(record)


def configure_logging(level: str) -> None:
    """Called once by create_app: JSON lines on stderr (CloudWatch via the ECS log driver)."""
    LOGGER.setLevel(level)
    LOGGER.propagate = False  # FastMCP configures the root logger; never write a line twice
    # Library INFO lines (request URLs, MCP session notices) are not on the allowlist (§10.2).
    for library in ("httpx", "httpcore", "mcp"):
        logging.getLogger(library).setLevel(logging.WARNING)
    if not any(isinstance(h, _StderrHandler) for h in LOGGER.handlers):
        LOGGER.addHandler(_StderrHandler())


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    payload: dict[str, Any] = {"event": event}
    if fields.get("sub"):
        payload["actor"] = hash_subject(str(fields["sub"]))
    payload.update(
        {k: v for k, v in fields.items() if k in ALLOWED_FIELDS and k != "actor" and v is not None}
    )
    LOGGER.log(level, json.dumps(payload, sort_keys=False, default=str))


def log_error(event: str, exc: BaseException, **fields: Any) -> None:
    """An unexpected failure: the exception's type only. No message or traceback, which may hold
    transcripts, addresses or tokens (TDD §10.2)."""
    log_event(event, level=logging.ERROR, error_code=type(exc).__name__, **fields)
