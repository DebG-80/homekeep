"""Session checkpoints and turn records (TDD §4.2 T3/T9, §6.1).

`SESSION#{id}`: active issue, last committed step, pending approval and the last 12 messages.
`TURN#{session}#{turn}`: the finished response, so a retried turn returns it unchanged (FR-22).
Both expire after 24 hours and are written in one transaction, after everything else committed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from app.domain.clock import iso_utc
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.store import keys
from app.store.table import Table

SESSION_TTL = timedelta(hours=24)
MAX_MESSAGES = 12


def _session_sk(session_id: str) -> str:
    return f"SESSION#{session_id}"


def _turn_sk(session_id: str, turn_id: str) -> str:
    return f"TURN#{session_id}#{turn_id}"


def create_session(table: Table, household_id: str, sub: str, now: datetime) -> dict[str, Any]:
    session = {
        "PK": keys.household_pk(household_id),
        "SK": _session_sk(f"s-{uuid.uuid4().hex}"),
        "kind": "SESSION",
        "actor_sub": sub,
        "active_issue_id": None,
        "last_step_id": None,
        "pending_approval_id": None,
        "messages": [],
        "speech_rate": "normal",
        "created_at": iso_utc(now),
        "ttl": int((now + SESSION_TTL).timestamp()),
        "version": 1,
    }
    session["session_id"] = session["SK"].removeprefix("SESSION#")
    table.put_new(session)
    return session


def load_session(table: Table, household_id: str, session_id: str) -> dict[str, Any]:
    session = table.get(keys.household_pk(household_id), _session_sk(session_id))
    if session is None:  # another household's session is simply not found
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    return session


def stored_turn(
    table: Table, household_id: str, session_id: str, turn_id: str
) -> dict[str, Any] | None:
    item = table.get(keys.household_pk(household_id), _turn_sk(session_id, turn_id))
    return item.get("response") if item and item.get("status", "DONE") == "DONE" else None


def claim_turn(
    table: Table,
    session: dict[str, Any],
    turn_id: str,
    now: datetime,
    stale_after: timedelta = timedelta(minutes=1),
) -> dict[str, Any] | None:
    """T3: claim this turn before doing anything (FR-22, invariant 5). Returns None when the
    caller now owns the turn, or the existing record: DONE (replay it) or IN_PROGRESS (a retry
    while the original runs). A claim left behind by a crashed turn is taken over after
    `stale_after`."""
    pk, sk = session["PK"], _turn_sk(session["session_id"], turn_id)
    claim = {
        "PK": pk,
        "SK": sk,
        "kind": "TURN",
        "status": "IN_PROGRESS",
        "response": None,
        "claimed_at": iso_utc(now),
        "ttl": int((now + SESSION_TTL).timestamp()),
    }
    try:
        table.put_new(claim)
        return None
    except ConflictError:
        existing = table.get(pk, sk)
    if existing is None:
        return None  # vanished meanwhile (released); the caller may proceed
    claimed_at = existing.get("claimed_at")
    if (
        existing.get("status") == "IN_PROGRESS"
        and claimed_at
        and claimed_at < iso_utc(now - stale_after)
    ):
        try:
            table.transact(
                [table.put_if_op(claim, "#at = :old", {":old": claimed_at}, {"#at": "claimed_at"})]
            )
            return None
        except ConflictError:
            return table.get(pk, sk)
    return existing


def release_turn(table: Table, session: dict[str, Any], turn_id: str) -> None:
    """A turn that failed before committing gives up its claim, so a retry can run it."""
    table.delete(session["PK"], _turn_sk(session["session_id"], turn_id))


def commit_turn(
    table: Table,
    session: dict[str, Any],
    turn_id: str,
    response: dict[str, Any],
    updates: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Persist the checkpoint and the finished turn together, then acknowledge (invariant 4).

    If another turn on this session committed first, its changes are kept: this turn's updates
    are re-applied to the latest checkpoint (messages appended after the other turn's)."""
    sk = _turn_sk(session["session_id"], turn_id)
    record = {
        "PK": session["PK"],
        "SK": sk,
        "kind": "TURN",
        "status": "DONE",
        "response": response,
        "ttl": int((now + SESSION_TTL).timestamp()),
    }
    current = session
    for _ in range(3):
        new_session = {
            **current,
            **{k: v for k, v in updates.items() if k != "new_messages"},
            "messages": (current["messages"] + updates.get("new_messages", []))[-MAX_MESSAGES:],
            "ttl": int((now + SESSION_TTL).timestamp()),
            "version": current["version"] + 1,
        }
        try:
            table.transact(
                [
                    table.put_versioned_op(new_session, current["version"]),
                    table.put_if_op(
                        record,
                        "attribute_not_exists(PK) OR #status = :claimed",
                        {":claimed": "IN_PROGRESS"},
                        {"#status": "status"},
                    ),
                ]
            )
            return response
        except ConflictError as exc:
            if 1 in exc.failed_indexes:  # the same turn already finished elsewhere
                existing = table.get(session["PK"], sk)
                if existing and existing.get("response") is not None:
                    return existing["response"]
            latest = table.get(session["PK"], session["SK"])
            if latest is None:
                raise
            current = latest  # another turn moved the session on: merge and try again
    raise DomainError(ErrorCode.RECORD_CONFLICT, "SESSION_BUSY")
