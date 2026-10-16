"""Appliances: minimal registration, scoped resolution and per-field provenance (FR-02, FR-03).

Only category and a confirmed nickname are required; everything else may stay unknown. A
nickname sentinel written in the same transaction prevents silent duplicates. Model and brand
claims from the user are USER_REPORTED and never unlock model-specific guidance by themselves;
verification arrives with the catalog in Slice 2 (G1-3).
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from app.domain import mutations
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.household import require_storage_consent
from app.domain.ids import new_id
from app.security.authz import Action, authorize
from app.store import keys

NICKNAME_MAX = 80  # BRD §8.2


class Category(StrEnum):
    AC = "AC"
    REFRIGERATOR = "REFRIGERATOR"
    TELEVISION = "TELEVISION"


class FieldStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    USER_REPORTED = "USER_REPORTED"
    DOCUMENT_SUPPORTED = "DOCUMENT_SUPPORTED"
    VERIFIED = "VERIFIED"


# Words people use for each category (FR-02: "fridge" for refrigerator, "TV" for television).
CATEGORY_ALIASES: dict[Category, tuple[str, ...]] = {
    Category.AC: ("ac", "a/c", "air conditioner", "aircon"),
    Category.REFRIGERATOR: ("fridge", "refrigerator"),
    Category.TELEVISION: ("tv", "television", "telly"),
}
FACT_FIELDS = ("brand", "model", "serial")
_UNKNOWN_WORDS = {"unknown", "not sure", "i don't know", "dont know", "don't know"}
_STRONG_STATUSES = {FieldStatus.DOCUMENT_SUPPORTED.value, FieldStatus.VERIFIED.value}


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def parse_category(text: str) -> Category:
    word = normalise(text)
    for category, aliases in CATEGORY_ALIASES.items():
        if word == category.value.casefold() or word in aliases:
            return category
    raise DomainError(ErrorCode.INVALID_INPUT, "UNSUPPORTED_CATEGORY")


def _mentions(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![\w/]){re.escape(phrase)}(?![\w/])", text) is not None


def _unknown_field() -> dict[str, Any]:
    return {"value": None, "status": FieldStatus.UNKNOWN.value, "provenance": None}


def _user_field(ctx: OperationContext, value: str | None) -> dict[str, Any]:
    if value is None or normalise(value) in _UNKNOWN_WORDS:
        return _unknown_field()
    return {
        "value": value.strip(),
        "status": FieldStatus.USER_REPORTED.value,
        "provenance": {
            "source": "USER",
            "actor_sub": ctx.actor.sub,
            "at": iso_utc(ctx.clock.now()),
        },
    }


def view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "appliance_id": item["appliance_id"],
        "category": item["category"],
        "nickname": item["nickname"],
        "room": item.get("room"),
        "fields": item["fields"],
        "conflicts": item.get("conflicts", []),
        "version": item["version"],
    }


def _all(ctx: OperationContext) -> list[dict[str, Any]]:
    return ctx.table.query(keys.household_pk(ctx.household_id), keys.APPLIANCE_PREFIX)


def load(ctx: OperationContext, appliance_id: str) -> dict[str, Any]:
    """This household's appliance, or NOT_FOUND. Another household's ID is simply not found."""
    item = ctx.table.get(keys.household_pk(ctx.household_id), keys.appliance_sk(appliance_id))
    if item is None:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    return item


def register_appliance(
    ctx: OperationContext,
    category: str,
    nickname: str,
    room: str | None = None,
    brand: str | None = None,
    model_claim: str | None = None,
) -> dict[str, Any]:
    authorize(ctx.actor, Action.APPLIANCE_WRITE, ctx.household_id)
    parsed = parse_category(category)
    nickname = re.sub(r"\s+", " ", nickname).strip()
    if not nickname:
        raise DomainError(ErrorCode.INVALID_INPUT, "NICKNAME_REQUIRED")
    if len(nickname) > NICKNAME_MAX:
        raise DomainError(ErrorCode.INVALID_INPUT, "NICKNAME_TOO_LONG")
    args = {
        "category": parsed.value,
        "nickname": nickname,
        "room": room,
        "brand": brand,
        "model_claim": model_claim,
    }

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)

        nickname_key = normalise(nickname)
        pk = keys.household_pk(ctx.household_id)
        existing = ctx.table.get(pk, keys.nickname_sk(nickname_key))
        if existing is not None:
            raise _duplicate(existing)

        appliance_id = new_id()
        now = iso_utc(ctx.clock.now())
        item = {
            "PK": pk,
            "SK": keys.appliance_sk(appliance_id),
            "kind": "APPLIANCE",
            "appliance_id": appliance_id,
            "category": parsed.value,
            "nickname": nickname,
            "nickname_key": nickname_key,
            "room": room.strip() if room else None,
            "fields": {
                "brand": _user_field(ctx, brand),
                "model": _user_field(ctx, model_claim),
                "serial": _unknown_field(),
            },
            "conflicts": [],
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }
        sentinel = {
            "PK": pk,
            "SK": keys.nickname_sk(nickname_key),
            "kind": "NICKNAME",
            "appliance_id": appliance_id,
            "nickname": nickname,
        }
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_new_op(item),
            ctx.table.put_new_op(sentinel),
            ctx.table.put_op(
                event_item(
                    ctx,
                    action="APPLIANCE_REGISTERED",
                    record_sk=item["SK"],
                    appliance_id=appliance_id,
                    prior_version=None,
                    new_version=1,
                )
            ),
        ]
        try:
            return mutations.commit(ctx, mutation, operations, view(item))
        except ConflictError as exc:
            if 0 in exc.failed_indexes:
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            if 2 in exc.failed_indexes:  # another turn took the nickname meanwhile
                taken = ctx.table.get(pk, keys.nickname_sk(nickname_key))
                raise _duplicate(taken or sentinel) from exc
            raise

    return mutations.run(ctx, "register_appliance", args, body)


def _duplicate(sentinel: dict[str, Any]) -> DomainError:
    # G1-4: needs a clarified nickname, so INVALID_INPUT with the existing appliance's reference.
    return DomainError(
        ErrorCode.INVALID_INPUT,
        "DUPLICATE_NICKNAME",
        {"existing_appliance_id": sentinel["appliance_id"], "nickname": sentinel["nickname"]},
    )


def resolve_appliance(
    ctx: OperationContext, reference: str, room: str | None = None
) -> dict[str, Any]:
    """0, 1 or many matches inside this household. Ambiguity is returned, never guessed."""
    authorize(ctx.actor, Action.APPLIANCE_READ, ctx.household_id)
    text = normalise(reference)
    appliances = _all(ctx)

    matches = [a for a in appliances if a["nickname_key"] == text]
    if not matches:
        categories = {
            category
            for category, aliases in CATEGORY_ALIASES.items()
            if any(_mentions(text, alias) for alias in aliases)
        }
        matches = [
            a
            for a in appliances
            if a["category"] in categories or _mentions(text, a["nickname_key"])
        ]
    room_words = normalise(room) if room else None
    if room_words is None and len(matches) > 1:
        # "the bedroom AC": a room named inside the reference narrows the candidates.
        spoken = [a for a in matches if a.get("room") and _mentions(text, normalise(a["room"]))]
        matches = spoken or matches
    elif room_words is not None:
        matches = [a for a in matches if a.get("room") and normalise(a["room"]) == room_words]

    return {
        "matches": [view(a) for a in matches],
        "needs_clarification": len(matches) > 1,
    }


def update_appliance_fact(
    ctx: OperationContext,
    appliance_id: str,
    field: str,
    value: str | None,
    expected_version: int,
) -> dict[str, Any]:
    """A user correction. It never overwrites document-backed or verified values: it records a
    visible conflict instead (FR-03)."""
    authorize(ctx.actor, Action.APPLIANCE_WRITE, ctx.household_id)
    if field not in FACT_FIELDS:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_FIELD")
    args = {
        "appliance_id": appliance_id,
        "field": field,
        "value": value,
        "expected_version": expected_version,
    }

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        item = load(ctx, appliance_id)
        if item["version"] != expected_version:
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION")

        claim = _user_field(ctx, value)
        current = item["fields"][field]
        fields = dict(item["fields"])
        conflicts = list(item.get("conflicts", []))
        if current["status"] in _STRONG_STATUSES:
            # A document-backed or verified value stands. Only a different, known claim is
            # recorded, as a visible conflict; repeating it or "not sure" changes nothing.
            if claim["value"] is not None and claim["value"] != current["value"]:
                conflicts.append({"field": field, **claim})
        else:
            fields[field] = claim
        updated = {
            **item,
            "fields": fields,
            "conflicts": conflicts,
            "updated_at": iso_utc(ctx.clock.now()),
            "version": item["version"] + 1,
        }
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_versioned_op(updated, expected_version),
            ctx.table.put_op(
                event_item(
                    ctx,
                    action="APPLIANCE_FACT_UPDATED",
                    record_sk=item["SK"],
                    appliance_id=appliance_id,
                    prior_version=expected_version,
                    new_version=updated["version"],
                )
            ),
        ]
        try:
            return mutations.commit(ctx, mutation, operations, view(updated))
        except ConflictError as exc:
            if 0 in exc.failed_indexes:
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    return mutations.run(ctx, "update_appliance_fact", args, body)
