"""Admin-only fault injection (TDD §4.6): `PROVIDER#demo / FAULT#{household}`.

A fault applies to one household, `remaining` times, and only for the operation it belongs to.
It is honoured only when FAULTS_ENABLED; otherwise the simulator always behaves normally. Tests
write the item directly; an admin API is deferred (P1-1).
"""

from __future__ import annotations

from botocore.exceptions import ClientError

from app.store import keys
from app.store.table import Table, to_dynamo

SUBMIT_FAULTS = frozenset({"ACK_ONLY", "TIMEOUT_AFTER_SUCCESS", "REJECT", "UNAVAILABLE"})
QUOTE_FAULTS = frozenset({"FEE_CHANGE"})
REPLACE_FAULTS = frozenset({"REPLACE_FAIL"})
CANCEL_FAULTS = frozenset({"CANCEL_REFUSE", "CANCEL_TIMEOUT"})


def take_fault(
    table: Table, household_id: str, applicable: frozenset[str], enabled: bool
) -> str | None:
    """Consume one use of this household's fault if it applies to the operation."""
    if not enabled:
        return None
    sk = keys.fault_sk(household_id)
    item = table.get(keys.PROVIDER_PK, sk)
    if not item or item.get("fault") not in applicable or item.get("remaining", 0) <= 0:
        return None
    try:
        table.client.update_item(
            TableName=table.name,
            Key=to_dynamo({"PK": keys.PROVIDER_PK, "SK": sk}),
            UpdateExpression="ADD remaining :minus",
            ConditionExpression="remaining > :zero",
            ExpressionAttributeValues=to_dynamo({":minus": -1, ":zero": 0}),
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return None
        raise
    return str(item["fault"])
