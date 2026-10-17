"""Thin DynamoDB wrapper: typed items in, typed items out, conditional failures as ConflictError.

Every write that can lose an update is conditional (TDD §6.2): new items use
attribute_not_exists, existing items carry `version` and are written only if it still matches.
Several items that must change together go through one TransactWriteItems call.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
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
    def __init__(
        self, client: Any | None, name: str, client_factory: Callable[[], Any] | None = None
    ) -> None:
        if client is None and client_factory is None:
            raise ValueError("a Table needs a client or a client factory")
        self._client = client
        self._client_factory = client_factory
        self.name = name

    @property
    def client(self) -> Any:
        """Created on first use, so building the app makes no AWS call (liveness stays cheap)."""
        if self._client is None and self._client_factory is not None:
            self._client = self._client_factory()
        return self._client

    @classmethod
    def from_settings(cls, settings: Settings) -> Table:
        if not settings.table_name:
            raise ValueError("TABLE_NAME is not configured")

        def factory() -> Any:
            return boto3.client(
                "dynamodb",
                region_name=settings.aws_region,
                endpoint_url=settings.dynamodb_endpoint_url,  # set only when ENV=local
            )

        return cls(None, settings.table_name, factory)

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

    def increment_below(self, pk: str, sk: str, *, attribute: str, limit: int, ttl: int) -> bool:
        """Atomically add one to a counter unless it has reached `limit`. False when it has."""
        try:
            self.client.update_item(
                TableName=self.name,
                Key=to_dynamo({"PK": pk, "SK": sk}),
                UpdateExpression="ADD #count :one SET #ttl = :ttl",
                ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
                ExpressionAttributeNames={"#count": attribute, "#ttl": "ttl"},
                ExpressionAttributeValues=to_dynamo({":one": 1, ":limit": limit, ":ttl": ttl}),
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

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

    def put_if_op(
        self,
        item: Mapping[str, Any],
        expression: str,
        values: Mapping[str, Any],
        names: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """A put guarded by an arbitrary condition (for example, a claim still in progress)."""
        put: dict[str, Any] = {
            **self.put_op(item)["Put"],
            "ConditionExpression": expression,
            "ExpressionAttributeValues": to_dynamo(values),
        }
        if names:
            put["ExpressionAttributeNames"] = dict(names)
        return {"Put": put}

    def update_op(
        self,
        pk: str,
        sk: str,
        expression: str,
        values: Mapping[str, Any],
        names: Mapping[str, str] | None = None,
        condition: str | None = None,
    ) -> dict[str, Any]:
        """An update inside a transaction (for example, a counter that must stay below a limit)."""
        update: dict[str, Any] = {
            "TableName": self.name,
            "Key": to_dynamo({"PK": pk, "SK": sk}),
            "UpdateExpression": expression,
            "ExpressionAttributeValues": to_dynamo(values),
        }
        if names:
            update["ExpressionAttributeNames"] = dict(names)
        if condition:
            update["ConditionExpression"] = condition
        return {"Update": update}

    def delete_op(self, pk: str, sk: str, expected_version: int | None = None) -> dict[str, Any]:
        delete: dict[str, Any] = {"TableName": self.name, "Key": to_dynamo({"PK": pk, "SK": sk})}
        if expected_version is not None:  # only if nobody changed (or deleted) it meanwhile
            delete["ConditionExpression"] = "#version = :expected"
            delete["ExpressionAttributeNames"] = {"#version": "version"}
            delete["ExpressionAttributeValues"] = to_dynamo({":expected": expected_version})
        return {"Delete": delete}

    def query_index(self, index: str, pk: str, *, forward: bool = False) -> list[dict[str, Any]]:
        """All items under one GSI partition, newest first by default (queues, sweep)."""
        kwargs: dict[str, Any] = {
            "TableName": self.name,
            "IndexName": index,
            "KeyConditionExpression": "GSI1PK = :pk",
            "ExpressionAttributeValues": to_dynamo({":pk": pk}),
            "ScanIndexForward": forward,
        }
        items: list[dict[str, Any]] = []
        while True:
            response = self.client.query(**kwargs)
            items.extend(from_dynamo(item) for item in response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def delete(self, pk: str, sk: str) -> None:
        self.client.delete_item(TableName=self.name, Key=to_dynamo({"PK": pk, "SK": sk}))

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
