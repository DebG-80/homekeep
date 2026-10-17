from __future__ import annotations

from datetime import UTC, datetime

from app.channel import sessions
from app.store.table import Table
from tests.unit.domain.world import HH_A, put_household

NOW = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)


def test_nfr05_commit_turn_merges_after_concurrent_session_update(table: Table) -> None:
    put_household(table, HH_A)
    session = sessions.create_session(table, HH_A, "sub-a", NOW)
    # Another turn on the same session commits first.
    other = {
        "new_messages": [{"role": "user", "text": "one"}, {"role": "assistant", "text": "first"}]
    }
    assert sessions.claim_turn(table, session, "turn-1", NOW) is None
    sessions.commit_turn(table, session, "turn-1", {"speech": ["first"]}, other, NOW)

    # This turn still holds the old session version: it must merge, not fail or lose the other.
    mine = {
        "new_messages": [{"role": "user", "text": "two"}, {"role": "assistant", "text": "second"}],
        "active_issue_id": "issue-9",
    }
    assert sessions.claim_turn(table, session, "turn-2", NOW) is None
    response = sessions.commit_turn(table, session, "turn-2", {"speech": ["second"]}, mine, NOW)
    assert response == {"speech": ["second"]}
    stored = sessions.load_session(table, HH_A, session["session_id"], "sub-a")
    assert [m["text"] for m in stored["messages"]] == ["one", "first", "two", "second"]
    assert stored["active_issue_id"] == "issue-9"
    assert sessions.stored_turn(table, HH_A, session["session_id"], "turn-1") == {
        "speech": ["first"]
    }


def test_g3_9_another_members_session_is_not_found(table: Table) -> None:
    import pytest

    from app.domain.errors import DomainError

    put_household(table, HH_A)
    session = sessions.create_session(table, HH_A, "sub-owner", NOW)
    assert (
        sessions.load_session(table, HH_A, session["session_id"], "sub-owner")["session_id"]
        == session["session_id"]
    )
    with pytest.raises(DomainError) as caught:
        sessions.load_session(table, HH_A, session["session_id"], "sub-helper")  # same household
    assert caught.value.reason == "NOT_FOUND"
