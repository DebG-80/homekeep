"""The deterministic approval guard (TDD §4.3; FR-12; CLAUDE.md invariant 2).

Only this code, never the model, decides whether an utterance approves the pending action. Voice
turns must pass every rule: (1) one pending, unexpired approval; (2) the read-back finished
playing; (3) speech began after that, while the client was LISTENING; (4) the whole utterance
is an affirmative; (5) it is not an echo of HomeKeep's own words. Rule 6, the grant, is checked
again by the domain. Text turns apply rules 1, 4 and 6 only. A negative cancels the pending action;
anything else leaves it pending.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

AFFIRMATIVE = frozenset(
    {
        "yes",
        "yes please",
        "yes book it",
        "yes go ahead",
        "yes do it",
        "yes confirm",
        "yes that's right",
        "yes sure",
        "confirm",
        "go ahead",
        "ok go ahead",
        "okay go ahead",
        "do it",
        "book it",
        "please book it",
        "please go ahead",
        "sure",
        # Answers to the change and call-off read-backs (N1).
        "yes change it",
        "change it",
        "yes move it",
        "move it",
        "yes call it off",
        "call it off",
    }
)
NEGATIVE = frozenset(
    {
        "no",
        "no thanks",
        "no thank you",
        "don't",
        "dont",
        "not now",
        "no don't",
        "no dont",
        "don't book it",
        "no don't book it",
        "no dont book it",
        "no wait",
        "no stop",
    }
)
ECHO_THRESHOLD = 0.6
CLIENT_CLOCK_SKEW = timedelta(seconds=2)


@dataclass(frozen=True)
class Pending:
    pending_ref: str
    expires_at: datetime
    readback_completed_at: datetime | None


@dataclass(frozen=True)
class Decision:
    kind: Literal["APPROVE", "DECLINE", "NONE"]
    reason: str


def _normalise(text: str) -> str:
    text = re.sub(r"[^a-z' ]", " ", text.casefold().replace("\u2019", "'"))
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    left, right = set(a.split()), set(b.split())
    return len(left & right) / len(left | right) if left and right else 0.0


def decide(
    text: str,
    *,
    pending: Pending | None,
    channel: str,
    client_state: str | None,
    speech_started_at: datetime | None,
    now: datetime,
    last_spoken: str | None,
) -> Decision:
    if pending is None:
        return Decision("NONE", "NO_PENDING")
    utterance = _normalise(text)
    if utterance in NEGATIVE:
        return Decision("DECLINE", "NEGATIVE")
    if "?" in text or utterance not in AFFIRMATIVE:  # rule 4: the whole utterance
        return Decision("NONE", "NOT_AFFIRMATIVE")
    if now >= pending.expires_at:  # rule 1
        return Decision("NONE", "EXPIRED")
    if channel == "voice":
        if speech_started_at is not None and speech_started_at > now + CLIENT_CLOCK_SKEW:
            return Decision("NONE", "SPEECH_TIME_INVALID")  # a client time from the future (I8)
        if pending.readback_completed_at is None:  # rule 2
            return Decision("NONE", "READBACK_NOT_FINISHED")
        if speech_started_at is None or speech_started_at <= pending.readback_completed_at:
            return Decision("NONE", "SPOKE_DURING_READBACK")  # rule 3
        if client_state != "LISTENING":
            return Decision("NONE", "NOT_LISTENING")
        if last_spoken and _similarity(utterance, _normalise(last_spoken)) >= ECHO_THRESHOLD:
            return Decision("NONE", "ECHO")  # rule 5
    return Decision("APPROVE", "OK")


def accept_playback_end(
    prepared_at: datetime | None,
    playback_ended_at: datetime | None,
    client_state: str | None,
    now: datetime,
) -> datetime | None:
    """The client's report that the read-back finished playing, if it can be true (I8): only
    for a read-back that exists, not before it was prepared, not in the future, and not while
    the client says it is still speaking."""
    if prepared_at is None or playback_ended_at is None or client_state == "SPEAKING":
        return None
    if not prepared_at <= playback_ended_at <= now + CLIENT_CLOCK_SKEW:
        return None
    return playback_ended_at
