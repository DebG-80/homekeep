"""Operation keys and the idempotency ledger (TDD §5.5, CLAUDE.md invariant 5).

The key is derived server-side from the household, the turn and the canonical arguments, so a
transport retry of the same turn maps to the same key. `OP#{key}` stores the payload hash and the
result: a replay returns that result, and the same key with a different payload is a conflict.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from app.domain.errors import DomainError, ErrorCode
from app.store import keys
from app.store.table import Table

OPERATION_TTL = timedelta(days=14)  # BRD §7.3 asks for at least 7


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(args: Any) -> str:
    return _sha256(canonical_json(args))


def operation_key(household_id: str, turn_id: str, action: str, args: Any) -> str:
    return _sha256("|".join((household_id, turn_id, action, canonical_json(args))))


def operation_item(
    household_id: str, key: str, hashed_payload: str, result: Any, now: datetime
) -> dict[str, Any]:
    return {
        "PK": keys.household_pk(household_id),
        "SK": keys.operation_sk(key),
        "kind": "OPERATION",
        "payload_hash": hashed_payload,
        # Stored as canonical JSON text so the replayed result is byte-for-byte the original.
        "result": canonical_json(result),
        "created_at": now.isoformat(),
        "ttl": int((now + OPERATION_TTL).timestamp()),
    }


def lookup(table: Table, household_id: str, key: str, hashed_payload: str) -> Any | None:
    """The stored result for this operation, or None if it has not run yet."""
    item = table.get(keys.household_pk(household_id), keys.operation_sk(key))
    if item is None:
        return None
    if item["payload_hash"] != hashed_payload:
        raise DomainError(ErrorCode.RECORD_CONFLICT, "OPERATION_KEY_REUSED")
    return json.loads(item["result"])
