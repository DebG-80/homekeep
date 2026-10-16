"""Thin DynamoDB wrapper: typed items in, typed items out, conditional failures as ConflictError.

Every write that can lose an update is conditional (TDD §6.2): new items use
attribute_not_exists, existing items carry `version` and are written only if it still matches.
Several items that must change together go through one TransactWriteItems call.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from app.config import Settings
from app.domain.errors import ConflictError

_SERIALIZER = TypeSerializer()
_DESERIALIZER = TypeDeserializer()
_NEW = "attribute_not_exists(PK)"
_REASONS_IN_MESSAGE = re.compile(r"\[([^\]]*)\]")


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else value
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def to_dynamo(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _SERIALIZER.serialize(value) for key, value in item.items()}


def from_dynamo(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _plain(_DESERIALIZER.deserialize(value)) for key, value in item.items()}


def _cancellation_codes(error: ClientError) -> list[str]:
    reasons = error.response.get("CancellationReasons")
    if reasons:
        return [reason.get("Code", "None") for reason in reasons]
    # Some emulators only put the reasons in the message: "... [ConditionalCheckFailed, None]".
    match = _REASONS_IN_MESSAGE.search(error.response.get("Error", {}).get("Message", ""))
    return [code.strip() for code in match.group(1).split(",")] if match else []


class Table:
    def __init__(self, client: Any, name: str) -> None:
        self.client = client
        self.name = name

    @classmethod
    def from_settings(cls, settings: Settings) -> Table:
        if not settings.table_name:
            raise ValueError("TABLE_NAME is not configured")
        client = boto3.client(
            "dynamodb",
            region_name=settings.aws_region,
            endpoint_url=settings.dynamodb_endpoint_url,  # set only when ENV=local
        )
        return cls(client, settings.table_name)

    # --- reads -------------------------------------------------------------------------------

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.name, Key=to_dynamo({"PK": pk, "SK": sk}), ConsistentRead=True
        )
        item = response.get("Item")
        return from_dynamo(item) if item else None

    def query(self, pk: str, sk_prefix: str = "", *, forward: bool = True) -> list[dict[str, Any]]:
        condition = "PK = :pk"
        values: dict[str, Any] = {":pk": pk}
        if sk_prefix:
            condition += " AND begins_with(SK, :prefix)"
            values[":prefix"] = sk_prefix
        kwargs: dict[str, Any] = {
            "TableName": self.name,
            "KeyConditionExpression": condition,
            "ExpressionAttributeValues": to_dynamo(values),
            "ScanIndexForward": forward,
            "ConsistentRead": True,
        }
        items: list[dict[str, Any]] = []
        while True:
            response = self.client.query(**kwargs)
            items.extend(from_dynamo(item) for item in response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    # --- single-item writes ------------------------------------------------------------------

    def put(self, item: Mapping[str, Any]) -> None:
        """Unconditional write. Only for seeding fixtures; domain code uses the guarded forms."""
        self.client.put_item(TableName=self.name, Item=to_dynamo(item))

    def put_new(self, item: Mapping[str, Any]) -> None:
        self._put_conditionally(self.put_new_op(item)["Put"], "ALREADY_EXISTS")

    def put_versioned(self, item: Mapping[str, Any], expected_version: int) -> None:
        self._put_conditionally(
            self.put_versioned_op(item, expected_version)["Put"], "STALE_VERSION"
        )

    def _put_conditionally(self, request: dict[str, Any], reason: str) -> None:
        try:
            self.client.put_item(**request)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConflictError((0,), reason) from exc
            raise

    # --- transactions ------------------------------------------------------------------------

    def put_op(self, item: Mapping[str, Any]) -> dict[str, Any]:
        return {"Put": {"TableName": self.name, "Item": to_dynamo(item)}}

    def put_new_op(self, item: Mapping[str, Any]) -> dict[str, Any]:
        return {"Put": {**self.put_op(item)["Put"], "ConditionExpression": _NEW}}

    def put_versioned_op(self, item: Mapping[str, Any], expected_version: int) -> dict[str, Any]:
        if item.get("version") != expected_version + 1:
            raise ValueError("a versioned write must set version to expected_version + 1")
        return {
            "Put": {
                **self.put_op(item)["Put"],
                "ConditionExpression": "#version = :expected",
                "ExpressionAttributeNames": {"#version": "version"},
                "ExpressionAttributeValues": to_dynamo({":expected": expected_version}),
            }
        }

    def condition_op(
        self,
        pk: str,
        sk: str,
        expression: str,
        values: Mapping[str, Any],
        names: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        check: dict[str, Any] = {
            "TableName": self.name,
            "Key": to_dynamo({"PK": pk, "SK": sk}),
            "ConditionExpression": expression,
            "ExpressionAttributeValues": to_dynamo(values),
        }
        if names:
            check["ExpressionAttributeNames"] = dict(names)
        return {"ConditionCheck": check}

    def transact(self, operations: Sequence[dict[str, Any]]) -> None:
        """All-or-nothing write. A failed condition raises ConflictError naming the failed ops."""
        try:
            self.client.transact_write_items(TransactItems=list(operations))
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            codes = _cancellation_codes(exc)
            failed = tuple(i for i, code in enumerate(codes) if code not in ("None", ""))
            if any(code == "ConditionalCheckFailed" for code in codes):
                raise ConflictError(failed) from exc
            if any(code == "TransactionConflict" for code in codes):
                raise ConflictError(failed, "TRANSACTION_CONFLICT") from exc
            raise
