from __future__ import annotations

import time

import pytest

from app.domain.errors import DomainError
from app.security.attestation import Attestor


def test_inv2_attestation_round_trip_and_30s_expiry() -> None:
    attestor = Attestor()
    now = time.time()
    value = attestor.sign("sub-1", "session-1", "turn-1", now=now)
    attestor.verify(value, "sub-1", "session-1", "turn-1", now=now + 29)  # fresh enough

    for label, candidate, now_offset, args in [
        ("stale", value, 31, ("sub-1", "session-1", "turn-1")),
        (
            "future",
            attestor.sign("sub-1", "session-1", "turn-1", now=now + 60),
            0,
            ("sub-1", "session-1", "turn-1"),
        ),
        ("other subject", value, 0, ("sub-2", "session-1", "turn-1")),
        ("other session", value, 0, ("sub-1", "session-2", "turn-1")),
        ("other turn", value, 0, ("sub-1", "session-1", "turn-2")),
        (
            "other process key",
            Attestor().sign("sub-1", "session-1", "turn-1", now=now),
            0,
            ("sub-1", "session-1", "turn-1"),
        ),
        ("missing", None, 0, ("sub-1", "session-1", "turn-1")),
        ("malformed", "12345", 0, ("sub-1", "session-1", "turn-1")),
    ]:
        with pytest.raises(DomainError) as caught:
            attestor.verify(candidate, *args, now=now + now_offset)
        assert caught.value.code.value == "AUTH_DENIED", label
