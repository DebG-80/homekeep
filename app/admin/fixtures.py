"""Fixture records built from `fixtures/` (TDD §9.2): used by the seed, the judges' reset and
the `hk-admin` CLI.

They live in `app/` because the container ships `app/` and `fixtures/` but not `scripts/`, and
the in-app "Reset my demo data" must rebuild a judge household from them (plan G4-6).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from app.domain.appliances import Category, normalise
from app.store import keys

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def load_fixtures() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    households = json.loads((FIXTURES / "households.json").read_text(encoding="utf-8"))
    identities = json.loads((FIXTURES / "identities.json").read_text(encoding="utf-8"))
    return households, identities["identities"]


def in_env(record: dict[str, Any], env: str | None) -> bool:
    return env is None or env in record["envs"]


def local_subjects(identities: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Deterministic subjects for DynamoDB Local; the local token issuer uses the same ones."""
    return {identity["key"]: f"local-{identity['key']}" for identity in identities}


def household_items(
    household: dict[str, Any],
    members: Sequence[tuple[dict[str, Any], str]],
    seeded_at: str,
    consent_version: str,
) -> list[dict[str, Any]]:
    household_id = household["household_id"]
    pk = keys.household_pk(household_id)
    items: list[dict[str, Any]] = [
        {
            "PK": pk,
            "SK": keys.META,
            "kind": "HOUSEHOLD",
            "household_id": household_id,
            "locale": "en-IN",
            "timezone": "Asia/Kolkata",
            "lifecycle": "ACTIVE",
            "resettable": household["resettable"],
            "storage_consent": household["storage_consent"],
            "sharing_consent": household["sharing_consent"],
            **{
                attribute: {"value": household[attribute], "status": "USER_REPORTED"}
                for attribute in ("service_address", "contact_route")
                if household.get(attribute)
            },
            "created_at": seeded_at,
            "updated_at": seeded_at,
            "version": 1,
        }
    ]
    for purpose in ("STORAGE", "SHARING"):
        decision = household[f"{purpose.lower()}_consent"]
        if decision:
            items.append(
                {
                    "PK": pk,
                    "SK": keys.consent_sk(purpose, seeded_at, "seed"),
                    "kind": "CONSENT",
                    "purpose": purpose,
                    "decision": decision,
                    "consent_version": consent_version,
                    "actor_sub": "seed",
                    "at": seeded_at,
                }
            )
    for appliance in household["appliances"]:
        category = Category(appliance["category"])
        nickname_key = normalise(appliance["nickname"])
        unknown = {"value": None, "status": "UNKNOWN", "provenance": None}
        items.append(
            {
                "PK": pk,
                "SK": keys.appliance_sk(appliance["appliance_id"]),
                "kind": "APPLIANCE",
                "appliance_id": appliance["appliance_id"],
                "category": category.value,
                "nickname": appliance["nickname"],
                "nickname_key": nickname_key,
                "room": appliance.get("room"),
                "fields": {
                    "brand": unknown,
                    "model": appliance.get("model", unknown),
                    "serial": unknown,
                },
                "conflicts": [],
                "created_at": seeded_at,
                "updated_at": seeded_at,
                "version": 1,
            }
        )
        items.append(
            {
                "PK": keys.ref_pk(appliance["appliance_id"]),
                "SK": keys.META,
                "kind": "REF",
                "ref_id": appliance["appliance_id"],
                "ref_kind": "APPLIANCE",
                "household_id": household_id,
                "record_sk": keys.appliance_sk(appliance["appliance_id"]),
            }
        )
        items.append(
            {
                "PK": pk,
                "SK": keys.nickname_sk(nickname_key),
                "kind": "NICKNAME",
                "appliance_id": appliance["appliance_id"],
                "nickname": appliance["nickname"],
            }
        )
    for identity, sub in members:
        items.append(
            {
                "PK": pk,
                "SK": keys.member_sk(sub),
                "kind": "MEMBERSHIP",
                "sub": sub,
                # The sign-in name, so the owner can tell helpers apart and revocation can sign
                # the right Cognito user out; the fixture key lets a reset rebuild this item.
                "display_name": identity["username"],
                "identity_key": identity["key"],
                "role": identity["role"],
                "grants": identity["grants"],
                "status": identity["status"],
                "consent_version": consent_version,
                "created_at": seeded_at,
                "version": 1,
            }
        )
        items.append(
            {
                "PK": keys.user_pk(sub),
                "SK": keys.user_household_sk(household_id),
                "kind": "MEMBERSHIP_LOOKUP",
                "household_id": household_id,
            }
        )
    return items


def staff_items(
    identities: Iterable[dict[str, Any]], subjects: dict[str, str]
) -> list[dict[str, Any]]:
    """The staff directory (for assignment) and the demo provider's default technician (G3-3)."""
    items: list[dict[str, Any]] = []
    for identity in identities:
        if identity.get("groups") and identity["key"] in subjects:
            items.append(
                {
                    "PK": keys.staff_pk(subjects[identity["key"]]),
                    "SK": keys.META,
                    "kind": "STAFF",
                    "sub": subjects[identity["key"]],
                    "username": identity["username"],
                    "groups": identity["groups"],
                    "GSI1PK": "STAFF",  # the coordinator's technician list
                    "GSI1SK": identity["username"],
                }
            )
    if "tech_assigned" in subjects:
        items.append(
            {
                "PK": keys.PROVIDER_PK,
                "SK": "CONFIG",
                "kind": "PROVIDER_CONFIG",
                "default_technician_sub": subjects["tech_assigned"],
            }
        )
    return items
