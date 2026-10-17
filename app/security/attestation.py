"""Channel attestation for trusted tools (TDD §5.3; CLAUDE.md invariant 2).

`X-HK-Attest: {unix_ts}.{hex hmac_sha256(key, "sub|session|turn|tool|args_digest|ts")}`, where
`args_digest` is the sha256 of the canonical JSON arguments without None values (G3-8). The key is
random per process and never leaves memory, which works because the channel and the MCP server
share one process (one Uvicorn worker). Values older than 30 s, from the future, or for another
subject, session, turn, tool or argument set are refused. Freshness uses the real clock, never
CLOCK_OVERRIDE.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping
from typing import Any

from app.domain.errors import DomainError, ErrorCode

ATTEST_HEADER = "x-hk-attest"
MAX_AGE_SECONDS = 30
MAX_SKEW_SECONDS = 5


def arguments_digest(arguments: Mapping[str, Any]) -> str:
    present = {k: v for k, v in arguments.items() if v is not None}
    canonical = json.dumps(present, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _deny(reason: str) -> DomainError:
    return DomainError(ErrorCode.AUTH_DENIED, reason)


class Attestor:
    def __init__(self, key: bytes | None = None) -> None:
        self._key = key or secrets.token_bytes(32)

    def _mac(
        self,
        sub: str,
        session: str,
        turn: str,
        tool: str,
        arguments: Mapping[str, Any],
        timestamp: int,
    ) -> str:
        message = f"{sub}|{session}|{turn}|{tool}|{arguments_digest(arguments)}|{timestamp}"
        return hmac.new(self._key, message.encode(), hashlib.sha256).hexdigest()

    def sign(
        self,
        sub: str,
        session: str,
        turn: str,
        tool: str,
        arguments: Mapping[str, Any],
        now: float | None = None,
    ) -> str:
        timestamp = int(time.time() if now is None else now)
        return f"{timestamp}.{self._mac(sub, session, turn, tool, arguments, timestamp)}"

    def verify(
        self,
        value: str | None,
        sub: str,
        session: str,
        turn: str,
        tool: str,
        arguments: Mapping[str, Any],
        now: float | None = None,
    ) -> None:
        if not value:
            raise _deny("ATTESTATION_MISSING")
        timestamp_text, _, mac = value.partition(".")
        if not timestamp_text.isdigit() or not mac:
            raise _deny("ATTESTATION_MALFORMED")
        timestamp = int(timestamp_text)
        current = time.time() if now is None else now
        if current - timestamp > MAX_AGE_SECONDS or timestamp - current > MAX_SKEW_SECONDS:
            raise _deny("ATTESTATION_STALE")
        expected = self._mac(sub, session, turn, tool, arguments, timestamp)
        if not hmac.compare_digest(mac, expected):
            raise _deny("ATTESTATION_INVALID")
