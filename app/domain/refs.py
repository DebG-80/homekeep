"""Opaque record references (G3-1): `REF#{id} / META → {household_id, kind}`.

Staff and the system never take a household ID from input (invariant 1). They act on a record's
opaque ID and resolve its household here. Each REF item is written in the same transaction as the
record it names. Its GSI1 keys drive the coordinator's case queue (`CASE`) and safety list
(`SAFETY`).
"""

from __future__ import annotations

from typing import Any

from app.domain.errors import DomainError, ErrorCode
from app.store import keys
from app.store.table import Table


def ref_item(
    opaque_id: str,
    household_id: str,
    kind: str,
    record_sk: str,
    *,
    index: str | None = None,
    sort: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "PK": keys.ref_pk(opaque_id),
        "SK": keys.META,
        "kind": "REF",
        "ref_id": opaque_id,
        "ref_kind": kind,
        "household_id": household_id,
        "record_sk": record_sk,
    }
    if index:
        item["GSI1PK"] = index
        item["GSI1SK"] = sort or opaque_id
    return item


def resolve(table: Table, opaque_id: str, kind: str) -> dict[str, Any]:
    item = table.get(keys.ref_pk(opaque_id), keys.META)
    if item is None or item.get("ref_kind") != kind:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    return item
