"""The table definition from docs/infra-contract.md §3.

`ensure_table` exists for DynamoDB Local and moto only. On AWS, Deb provisions the table against
the contract; the application never creates or alters it there.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

GSI1 = "GSI1"
TTL_ATTRIBUTE = "ttl"

TABLE_DEFINITION: dict[str, Any] = {
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": "GSI1PK", "AttributeType": "S"},
        {"AttributeName": "GSI1SK", "AttributeType": "S"},
    ],
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},
        {"AttributeName": "SK", "KeyType": "RANGE"},
    ],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": GSI1,
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }
    ],
    "BillingMode": "PAY_PER_REQUEST",
}


def ensure_table(client: Any, name: str) -> bool:
    """Create the table if it is missing. Returns True when it was created."""
    try:
        client.describe_table(TableName=name)
        return False
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    client.create_table(TableName=name, **TABLE_DEFINITION)
    client.get_waiter("table_exists").wait(TableName=name)
    client.update_time_to_live(
        TableName=name,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": TTL_ATTRIBUTE},
    )
    return True
