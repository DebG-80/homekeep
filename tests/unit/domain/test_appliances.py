from __future__ import annotations

from app.domain.appliances import register_appliance, resolve_appliance, update_appliance_fact
from app.store import keys
from tests.unit.domain.world import EDIT_HELPER_A, HH_A, OWNER_A, VIEW_HELPER_A, World


def test_at03_fridge_and_tv_aliases_resolve(world: World) -> None:
    fridge = register_appliance(world.ctx(OWNER_A), "fridge", "Kitchen fridge", room="kitchen")
    tv = register_appliance(world.ctx(EDIT_HELPER_A), "TV", "Living room TV")
    assert (fridge["category"], tv["category"]) == ("REFRIGERATOR", "TELEVISION")

    for reference, expected in (
        ("the fridge", fridge),
        ("my refrigerator", fridge),
        ("the TV", tv),
        ("television", tv),
    ):
        result = resolve_appliance(world.ctx(VIEW_HELPER_A), reference)
        assert [m["appliance_id"] for m in result["matches"]] == [expected["appliance_id"]], (
            reference
        )
        assert result["needs_clarification"] is False


def test_at03_two_acs_require_room_clarification_without_mutation(world: World) -> None:
    bedroom = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC", room="bedroom")
    hall = register_appliance(world.ctx(OWNER_A), "air conditioner", "Hall AC", room="hall")
    before = world.snapshot()

    ambiguous = resolve_appliance(world.ctx(OWNER_A), "my AC")
    assert ambiguous["needs_clarification"] is True
    assert {m["appliance_id"] for m in ambiguous["matches"]} == {
        bedroom["appliance_id"],
        hall["appliance_id"],
    }

    by_room = resolve_appliance(world.ctx(OWNER_A), "my AC", room="bedroom")
    assert [m["appliance_id"] for m in by_room["matches"]] == [bedroom["appliance_id"]]
    spoken_room = resolve_appliance(world.ctx(OWNER_A), "the AC in the hall")
    assert [m["appliance_id"] for m in spoken_room["matches"]] == [hall["appliance_id"]]
    assert resolve_appliance(world.ctx(OWNER_A), "the washing machine")["matches"] == []

    assert world.snapshot() == before  # resolution never mutates


def test_at03_duplicate_nickname_never_overwrites(world: World, expect_error) -> None:
    original = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC", room="bedroom")

    for variant in ("Bedroom AC", "  bedroom   ac "):
        error = expect_error(
            "INVALID_INPUT",
            "DUPLICATE_NICKNAME",
            register_appliance,
            world.ctx(OWNER_A),
            "AC",
            variant,
            room="guest room",
        )
        assert error.details["existing_appliance_id"] == original["appliance_id"]

    (stored,) = world.items(HH_A, keys.APPLIANCE_PREFIX)
    assert stored["room"] == "bedroom"  # untouched
    # FR-02-AC2: a second, distinct AC is fine with a clarified nickname.
    second = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC 2", room="bedroom")
    assert second["appliance_id"] != original["appliance_id"]
    assert len(world.items(HH_A, keys.APPLIANCE_PREFIX)) == 2


def test_fr02_ac2_replay_returns_same_appliance(world: World) -> None:
    first = register_appliance(world.ctx(OWNER_A, turn_id="turn-7"), "AC", "Bedroom AC")
    again = register_appliance(world.ctx(OWNER_A, turn_id="turn-7"), "AC", "Bedroom AC")

    assert again == first
    assert len(world.items(HH_A, keys.APPLIANCE_PREFIX)) == 1
    assert len(world.items(HH_A, keys.EVENT_PREFIX)) == 1  # the replay wrote nothing
    # The key covers the arguments (TDD §5.5), so one turn can register two different appliances
    # ("I have a bedroom AC and a hall AC"). Key reuse with another payload is tested in store.
    other = register_appliance(world.ctx(OWNER_A, turn_id="turn-7"), "AC", "Hall AC")
    assert other["appliance_id"] != first["appliance_id"]
    assert len(world.items(HH_A, keys.APPLIANCE_PREFIX)) == 2


def test_fr03_user_reported_model_stays_unverified_and_conflicts_kept(
    world: World, expect_error
) -> None:
    created = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC", model_claim="FL-18i")
    assert created["fields"]["model"]["status"] == "USER_REPORTED"  # "I think it is model X"
    assert created["fields"]["model"]["provenance"]["actor_sub"] == OWNER_A.sub

    corrected = update_appliance_fact(
        world.ctx(OWNER_A), created["appliance_id"], "model", "FL-24x", 1
    )
    assert corrected["fields"]["model"]["value"] == "FL-24x"
    assert corrected["fields"]["model"]["status"] == "USER_REPORTED"
    assert corrected["version"] == 2

    # A reviewer-verified value (Slice 2 sets these) is never overwritten by a user claim.
    item = world.table.get(keys.household_pk(HH_A), keys.appliance_sk(created["appliance_id"]))
    verified = {"value": "FL-18i", "status": "VERIFIED", "provenance": {"source": "REVIEWER"}}
    world.table.put({**item, "fields": {**item["fields"], "model": verified}})
    claimed = update_appliance_fact(
        world.ctx(OWNER_A), created["appliance_id"], "model", "Something else", 2
    )
    assert claimed["fields"]["model"] == verified
    assert claimed["conflicts"][0]["field"] == "model"
    assert claimed["conflicts"][0]["value"] == "Something else"
    assert claimed["conflicts"][0]["status"] == "USER_REPORTED"

    expect_error(
        "RECORD_CONFLICT",
        "STALE_VERSION",
        update_appliance_fact,
        world.ctx(OWNER_A),
        created["appliance_id"],
        "brand",
        "Frostline",
        2,
    )
    expect_error(
        "AUTH_DENIED",
        None,
        update_appliance_fact,
        world.ctx(VIEW_HELPER_A),
        created["appliance_id"],
        "brand",
        "Frostline",
        3,
    )


def test_fr03_repeating_or_unknown_claim_never_downgrades_verified_value(world: World) -> None:
    created = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")
    item = world.table.get(keys.household_pk(HH_A), keys.appliance_sk(created["appliance_id"]))
    verified = {"value": "FL-18i", "status": "VERIFIED", "provenance": {"source": "REVIEWER"}}
    world.table.put({**item, "fields": {**item["fields"], "model": verified}})

    # Saying the verified model again changes nothing; it must not become USER_REPORTED.
    same = update_appliance_fact(world.ctx(OWNER_A), created["appliance_id"], "model", "FL-18i", 1)
    assert same["fields"]["model"] == verified
    assert same["conflicts"] == []
    # "Not sure" about a verified value is not a competing claim.
    unsure = update_appliance_fact(
        world.ctx(OWNER_A), created["appliance_id"], "model", "not sure", 2
    )
    assert unsure["fields"]["model"] == verified
    assert unsure["conflicts"] == []
