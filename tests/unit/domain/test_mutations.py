from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.domain import mutations
from app.domain.appliances import register_appliance, update_appliance_fact
from app.domain.household import ConsentDecision, ConsentPurpose, record_consent
from app.domain.issues import apply_issue_event, report_issue
from app.domain.observations import record_observation
from app.domain.state import IssueEvent
from app.store import keys, ops
from tests.unit.domain.world import HH_A, OWNER_A, World


def _stale_first_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry's first ledger read happens just before the original commits (it sees nothing);
    every later read sees the committed original."""
    real = ops.lookup
    calls: list[int] = []

    def lookup(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return None if len(calls) == 1 else real(*args, **kwargs)

    monkeypatch.setattr(ops, "lookup", lookup)


def test_inv5_retry_racing_the_original_commit_replays_for_every_mutation(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    appliance_id = register_appliance(world.ctx(OWNER_A), "AC", "Hall AC")["appliance_id"]
    issue_id = report_issue(world.ctx(OWNER_A), appliance_id, "Noisy", "NOISE")["issue"]["issue_id"]

    calls: list[tuple[str, Callable[..., Any], tuple[Any, ...]]] = [
        ("register", register_appliance, ("AC", "Bedroom AC")),  # trips the nickname sentinel
        ("fact", update_appliance_fact, (appliance_id, "brand", "Frostline", 1)),  # trips version
        (
            "report",
            report_issue,
            (appliance_id, "Also leaking", "WATER_LEAK"),
        ),  # trips active check
        ("event", apply_issue_event, (issue_id, IssueEvent.SERVICE_REQUESTED, 1)),  # trips version
        ("consent", record_consent, (ConsentPurpose.SHARING, ConsentDecision.DECLINED, "v1")),
    ]
    for name, call, args in calls:
        original = call(world.ctx(OWNER_A, turn_id=f"turn-{name}"), *args)
        with monkeypatch.context() as patch:
            _stale_first_lookup(patch)
            retry = call(world.ctx(OWNER_A, turn_id=f"turn-{name}"), *args)
        assert retry == original, name

    # record_observation: the original moved the issue and saved the answer; the retry replays.
    original = record_observation(
        world.ctx(OWNER_A, turn_id="turn-obs"), issue_id, "onset", "today"
    )
    with monkeypatch.context() as patch:
        _stale_first_lookup(patch)
        assert (
            record_observation(world.ctx(OWNER_A, turn_id="turn-obs"), issue_id, "onset", "today")
            == original
        )


def test_inv5_commit_returns_stored_result_when_a_duplicate_committed_first(world: World) -> None:
    # Both calls pass every pre-check; the original commits first, so the duplicate's OP# put fails.
    ctx = world.ctx(OWNER_A, turn_id="turn-dup")
    args = {
        "category": "AC",
        "nickname": "Bedroom AC",
        "room": None,
        "brand": None,
        "model_claim": None,
    }
    pending = mutations.start(ctx, "register_appliance", args)
    assert not pending.is_replay
    original = register_appliance(ctx, "AC", "Bedroom AC")

    duplicate_record = {
        "PK": keys.household_pk(HH_A),
        "SK": "APPL#would-be-duplicate",
        "version": 1,
    }
    result = mutations.commit(
        ctx, pending, [ctx.table.put_new_op(duplicate_record)], {"other": True}
    )

    assert result == original
    assert world.table.get(keys.household_pk(HH_A), "APPL#would-be-duplicate") is None
