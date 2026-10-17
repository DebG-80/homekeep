from __future__ import annotations

import time

import pytest

from app.domain.errors import DomainError
from app.security.attestation import Attestor


def test_inv2_attestation_round_trip_and_30s_expiry() -> None:
    attestor = Attestor()
    now = time.time()
    value = attestor.sign("sub-1", "session-1", "turn-1", "cancel_pending_action", {}, now=now)
    attestor.verify(
        value, "sub-1", "session-1", "turn-1", "cancel_pending_action", {}, now=now + 29
    )  # fresh enough

    for label, candidate, now_offset, args in [
        ("stale", value, 31, ("sub-1", "session-1", "turn-1")),
        (
            "future",
            attestor.sign(
                "sub-1", "session-1", "turn-1", "cancel_pending_action", {}, now=now + 60
            ),
            0,
            ("sub-1", "session-1", "turn-1"),
        ),
        ("other subject", value, 0, ("sub-2", "session-1", "turn-1")),
        ("other session", value, 0, ("sub-1", "session-2", "turn-1")),
        ("other turn", value, 0, ("sub-1", "session-1", "turn-2")),
        (
            "other process key",
            Attestor().sign("sub-1", "session-1", "turn-1", "cancel_pending_action", {}, now=now),
            0,
            ("sub-1", "session-1", "turn-1"),
        ),
        ("missing", None, 0, ("sub-1", "session-1", "turn-1")),
        ("malformed", "12345", 0, ("sub-1", "session-1", "turn-1")),
    ]:
        with pytest.raises(DomainError) as caught:
            attestor.verify(candidate, *args, "cancel_pending_action", {}, now=now + now_offset)
        assert caught.value.code.value == "AUTH_DENIED", label


def test_g3_8_attestation_bound_to_tool_and_arguments() -> None:
    attestor = Attestor()
    now = time.time()
    args = {"approval_id": "ap-1", "channel": "voice", "unused": None}
    value = attestor.sign("sub-1", "session-1", "turn-1", "execute_action", args, now=now)
    # None-valued arguments are ignored, so the client may omit them.
    attestor.verify(
        value,
        "sub-1",
        "session-1",
        "turn-1",
        "execute_action",
        {"approval_id": "ap-1", "channel": "voice"},
        now=now,
    )
    for tool, other in [
        ("confirm_action", args),
        ("execute_action", {**args, "approval_id": "ap-2"}),
        ("execute_action", {}),
    ]:
        with pytest.raises(DomainError) as caught:
            attestor.verify(value, "sub-1", "session-1", "turn-1", tool, other, now=now)
        assert caught.value.reason == "ATTESTATION_INVALID", (tool, other)
