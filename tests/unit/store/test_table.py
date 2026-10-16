from __future__ import annotations

import pytest

from app.domain.errors import ConflictError, ErrorCode
from app.store.table import Table


def _item(sk: str, version: int = 1, **extra: object) -> dict[str, object]:
    return {"PK": "HH#h1", "SK": sk, "version": version, **extra}


def test_round_trip_keeps_types(table: Table) -> None:
    item = _item("APPL#a1", nested={"value": None, "status": "UNKNOWN"}, aliases=["ac"], flag=True)
    table.put_new(item)
    assert table.get("HH#h1", "APPL#a1") == item
    assert table.query("HH#h1", "APPL#") == [item]
    assert table.get("HH#h1", "APPL#missing") is None


def test_nfr05_put_new_rejects_existing_item(table: Table) -> None:
    table.put_new(_item("APPL#a1", nickname="Bedroom AC"))
    with pytest.raises(ConflictError) as caught:
        table.put_new(_item("APPL#a1", nickname="Overwritten"))
    assert caught.value.code is ErrorCode.RECORD_CONFLICT
    assert caught.value.reason == "ALREADY_EXISTS"
    assert table.get("HH#h1", "APPL#a1")["nickname"] == "Bedroom AC"


def test_nfr05_stale_version_update_returns_record_conflict(table: Table) -> None:
    table.put_new(_item("APPL#a1", room="bedroom"))
    table.put_versioned(_item("APPL#a1", version=2, room="hall"), expected_version=1)

    # A second writer still holding version 1 must not overwrite version 2 (no lost update).
    with pytest.raises(ConflictError) as caught:
        table.put_versioned(_item("APPL#a1", version=2, room="kitchen"), expected_version=1)
    assert caught.value.code is ErrorCode.RECORD_CONFLICT
    assert caught.value.reason == "STALE_VERSION"
    assert table.get("HH#h1", "APPL#a1") == _item("APPL#a1", version=2, room="hall")

    with pytest.raises(ValueError, match="expected_version \\+ 1"):
        table.put_versioned(_item("APPL#a1", version=5), expected_version=2)


def test_nfr05_cancelled_transaction_maps_to_record_conflict(table: Table) -> None:
    table.put_new(_item("NICK#bedroom ac"))
    operations = [
        table.put_new_op(_item("APPL#a2")),
        table.put_new_op(_item("NICK#bedroom ac")),  # already taken
        table.put_op(_item("EVT#a2#t#e1")),
    ]
    with pytest.raises(ConflictError) as caught:
        table.transact(operations)
    assert caught.value.code is ErrorCode.RECORD_CONFLICT
    assert caught.value.failed_indexes == (1,)
    # All or nothing: neither the appliance nor the event was written.
    assert table.get("HH#h1", "APPL#a2") is None
    assert table.get("HH#h1", "EVT#a2#t#e1") is None

    table.put_new(_item("META", storage_consent="GRANTED"))
    check = table.condition_op(
        "HH#h1", "META", "#c = :granted", {":granted": "DECLINED"}, {"#c": "storage_consent"}
    )
    with pytest.raises(ConflictError) as caught:
        table.transact([check, table.put_new_op(_item("APPL#a3"))])
    assert caught.value.failed_indexes == (0,)
