"""Channel attestation for trusted tools (TDD §5.3; CLAUDE.md invariant 2).

`X-HK-Attest: {unix_ts}.{hex hmac_sha256(key, "sub|session|turn|ts")}`. The key is random per
process and never leaves memory, which works because the channel and the MCP server share one
process (one Uvicorn worker). Values older than 30 s, from the future, or for another subject,
session or turn are refused. Freshness uses the real clock, never CLOCK_OVERRIDE.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from app.domain.errors import DomainError, ErrorCode

ATTEST_HEADER = "x-hk-attest"
MAX_AGE_SECONDS = 30
MAX_SKEW_SECONDS = 5


def _deny(reason: str) -> DomainError:
    return DomainError(ErrorCode.AUTH_DENIED, reason)


class Attestor:
    def __init__(self, key: bytes | None = None) -> None:
        self._key = key or secrets.token_bytes(32)

    def _mac(self, sub: str, session: str, turn: str, timestamp: int) -> str:
        message = f"{sub}|{session}|{turn}|{timestamp}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def sign(self, sub: str, session: str, turn: str, now: float | None = None) -> str:
        timestamp = int(time.time() if now is None else now)
        return f"{timestamp}.{self._mac(sub, session, turn, timestamp)}"

    def verify(
        self, value: str | None, sub: str, session: str, turn: str, now: float | None = None
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
        if not hmac.compare_digest(mac, self._mac(sub, session, turn, timestamp)):
            raise _deny("ATTESTATION_INVALID")
