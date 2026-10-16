from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.store import ops
from app.store.table import Table

NOW = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)


def test_inv5_operation_key_is_server_derived_and_canonical() -> None:
    args_a = {"category": "AC", "nickname": "Bedroom AC", "room": None}
    args_b = {"room": None, "nickname": "Bedroom AC", "category": "AC"}  # same args, other order
    key = ops.operation_key("h1", "turn-1", "register_appliance", args_a)

    assert key == ops.operation_key("h1", "turn-1", "register_appliance", args_b)
    assert len(key) == 64  # sha256 hex
    assert int(key, 16) >= 0
    # Every input is part of the key: household, turn, action and arguments.
    assert key != ops.operation_key("h2", "turn-1", "register_appliance", args_a)
    assert key != ops.operation_key("h1", "turn-2", "register_appliance", args_a)
    assert key != ops.operation_key("h1", "turn-1", "report_issue", args_a)
    assert key != ops.operation_key("h1", "turn-1", "register_appliance", {**args_a, "room": "x"})


def test_inv5_replay_returns_stored_result(table: Table) -> None:
    args = {"nickname": "Bedroom AC"}
    key = ops.operation_key("h1", "turn-1", "register_appliance", args)
    hashed = ops.payload_hash(args)
    assert ops.lookup(table, "h1", key, hashed) is None

    result = {"appliance_id": "a1", "version": 1}
    item = ops.operation_item("h1", key, hashed, result, NOW)
    table.put_new(item)

    assert ops.lookup(table, "h1", key, hashed) == result
    assert item["ttl"] == int(NOW.timestamp()) + 14 * 24 * 3600


def test_inv5_same_key_different_payload_returns_record_conflict(table: Table) -> None:
    key = ops.operation_key("h1", "turn-1", "register_appliance", {"nickname": "Bedroom AC"})
    table.put_new(
        ops.operation_item("h1", key, ops.payload_hash({"nickname": "Bedroom AC"}), {}, NOW)
    )

    with pytest.raises(DomainError) as caught:
        ops.lookup(table, "h1", key, ops.payload_hash({"nickname": "Hall AC"}))
    assert caught.value.code is ErrorCode.RECORD_CONFLICT
    assert caught.value.reason == "OPERATION_KEY_REUSED"
