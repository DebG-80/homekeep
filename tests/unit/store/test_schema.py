from __future__ import annotations

from pathlib import Path

from app.store.schema import GSI1, TABLE_DEFINITION, TTL_ATTRIBUTE
from app.store.table import Table

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "infra-contract.md"


def _contract_section_3() -> str:
    text = CONTRACT.read_text(encoding="utf-8")
    return text.split("## 3 DynamoDB table", 1)[1].split("\n## ", 1)[0]


def test_table_definition_matches_infra_contract(table: Table) -> None:
    section = _contract_section_3()
    assert "| Partition key | `PK` (String) |" in section
    assert "| Sort key | `SK` (String) |" in section
    assert (
        f"Name `{GSI1}`; partition key `GSI1PK` (String); sort key `GSI1SK` (String); "
        "projection **ALL**"
    ) in section
    assert f"Enabled on attribute `{TTL_ATTRIBUTE}`" in section
    assert "| Capacity mode | On-demand |" in section

    attributes = {
        a["AttributeName"]: a["AttributeType"] for a in TABLE_DEFINITION["AttributeDefinitions"]
    }
    assert attributes == {"PK": "S", "SK": "S", "GSI1PK": "S", "GSI1SK": "S"}
    assert [k["AttributeName"] for k in TABLE_DEFINITION["KeySchema"]] == ["PK", "SK"]
    (index,) = TABLE_DEFINITION["GlobalSecondaryIndexes"]
    assert index["IndexName"] == GSI1
    assert [k["AttributeName"] for k in index["KeySchema"]] == ["GSI1PK", "GSI1SK"]
    assert index["Projection"] == {"ProjectionType": "ALL"}
    assert TABLE_DEFINITION["BillingMode"] == "PAY_PER_REQUEST"

    # ensure_table applied the definition, including TTL.
    ttl = table.client.describe_time_to_live(TableName=table.name)["TimeToLiveDescription"]
    assert ttl["AttributeName"] == TTL_ATTRIBUTE
    assert ttl["TimeToLiveStatus"] == "ENABLED"
