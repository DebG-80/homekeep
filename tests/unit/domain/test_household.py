from __future__ import annotations

from app.domain.appliances import register_appliance, resolve_appliance
from app.domain.household import ConsentDecision, ConsentPurpose, get_household, record_consent
from app.store import keys
from tests.unit.domain.world import HH_A, OWNER_A, VIEW_HELPER_A, World, put_household


def test_at01_consent_then_nickname_creates_usable_appliance_with_unknown_fields(
    world: World, expect_error
) -> None:
    put_household(world.table, HH_A, storage=None)  # assisted setup: no consent yet, no documents
    expect_error(
        "CONSENT_REQUIRED", None, register_appliance, world.ctx(OWNER_A), "AC", "Bedroom AC"
    )

    record_consent(world.ctx(OWNER_A), ConsentPurpose.STORAGE, ConsentDecision.GRANTED, "v1")
    created = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")

    assert created["category"] == "AC"
    assert created["nickname"] == "Bedroom AC"
    assert created["room"] is None
    for field in ("brand", "model", "serial"):
        assert created["fields"][field] == {"value": None, "status": "UNKNOWN", "provenance": None}

    stored = world.items(HH_A, keys.APPLIANCE_PREFIX)
    assert len(stored) == 1
    assert stored[0]["fields"] == created["fields"]
    # Usable: the same household can find it again by what the elder calls it.
    assert (
        resolve_appliance(world.ctx(OWNER_A), "bedroom ac")["matches"][0]["appliance_id"]
        == (created["appliance_id"])
    )


def test_at02_declining_sharing_creates_no_grant_and_use_continues(world: World) -> None:
    members_before = world.items(HH_A, keys.MEMBER_PREFIX)

    result = record_consent(
        world.ctx(OWNER_A), ConsentPurpose.SHARING, ConsentDecision.DECLINED, "v1"
    )

    assert result["sharing_consent"] == "DECLINED"
    assert result["storage_consent"] == "GRANTED"
    assert world.items(HH_A, keys.MEMBER_PREFIX) == members_before  # no helper grant appeared
    (consent,) = world.items(HH_A, "CONSENT#SHARING#")
    assert (consent["decision"], consent["actor_sub"]) == ("DECLINED", OWNER_A.sub)
    # Ordinary household use continues.
    assert register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")["version"] == 1
    assert get_household(world.ctx(OWNER_A))["sharing_consent"] == "DECLINED"


def test_fr01_ac2_no_storage_consent_returns_consent_required(world: World, expect_error) -> None:
    put_household(world.table, HH_A, storage=None)
    record_consent(world.ctx(OWNER_A), ConsentPurpose.STORAGE, ConsentDecision.DECLINED, "v1")

    error = expect_error(
        "CONSENT_REQUIRED",
        "STORAGE_CONSENT_NOT_GRANTED",
        register_appliance,
        world.ctx(OWNER_A),
        "AC",
        "Bedroom AC",
    )
    assert error.message == "I need your permission to save this first."  # explains the limit
    assert world.items(HH_A, keys.APPLIANCE_PREFIX) == []  # nothing persistent was created
    # Consent is the owner's decision alone.
    expect_error(
        "AUTH_DENIED",
        None,
        record_consent,
        world.ctx(VIEW_HELPER_A),
        ConsentPurpose.STORAGE,
        ConsentDecision.GRANTED,
        "v1",
    )


def test_fr01_consent_can_change_twice_at_one_fixed_instant(world: World) -> None:
    # Under CLOCK_OVERRIDE (local and test, P1-3) every call shares one instant.
    put_household(world.table, HH_A, storage=None)
    record_consent(world.ctx(OWNER_A), ConsentPurpose.STORAGE, ConsentDecision.DECLINED, "v1")
    changed = record_consent(
        world.ctx(OWNER_A), ConsentPurpose.STORAGE, ConsentDecision.GRANTED, "v1"
    )

    assert changed["storage_consent"] == "GRANTED"
    decisions = [c["decision"] for c in world.items(HH_A, "CONSENT#STORAGE#")]
    assert decisions == ["DECLINED", "GRANTED"]  # both kept, in order
