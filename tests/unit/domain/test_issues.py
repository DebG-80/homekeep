from __future__ import annotations

from app.domain.appliances import register_appliance
from app.domain.issues import apply_issue_event, get_issue, report_issue, transition_item
from app.domain.state import IssueEvent
from app.store import keys
from tests.unit.domain.world import HH_A, OWNER_A, VIEW_HELPER_A, World


def _ac(world: World) -> str:
    return register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")["appliance_id"]


def _issues(world: World) -> list[dict]:
    return [i for i in world.items(HH_A, keys.ISSUE_PREFIX) if i["kind"] == "ISSUE"]


def test_at06_replay_yields_one_issue(world: World) -> None:
    appliance_id = _ac(world)
    args = (appliance_id, "The bedroom AC is not cooling", "NOT_COOLING")
    first = report_issue(world.ctx(OWNER_A, turn_id="turn-1"), *args)
    replay = report_issue(world.ctx(OWNER_A, turn_id="turn-1"), *args)

    assert first["outcome"] == "CREATED"
    assert replay == first
    assert len(_issues(world)) == 1
    # Same words in a new turn: the existing case is offered, not duplicated.
    repeat = report_issue(world.ctx(OWNER_A, turn_id="turn-2"), *args)
    assert repeat["outcome"] == "NEEDS_CHOICE"
    assert [i["issue_id"] for i in repeat["active_issues"]] == [first["issue"]["issue_id"]]
    assert len(_issues(world)) == 1
    assert first["issue"]["original_wording"] == "The bedroom AC is not cooling"


def test_at06_confirmed_distinct_symptom_creates_second_issue(world: World) -> None:
    appliance_id = _ac(world)
    first = report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")
    second = report_issue(
        world.ctx(OWNER_A),
        appliance_id,
        "Water is dripping inside",
        "WATER_LEAK",
        confirmed_distinct=True,
    )
    assert second["outcome"] == "CREATED"
    assert second["issue"]["issue_id"] != first["issue"]["issue_id"]
    assert len(_issues(world)) == 2


def test_fr05_active_issue_requires_choice(world: World, expect_error) -> None:
    appliance_id = _ac(world)
    first = report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")
    before = world.snapshot()

    choice = report_issue(world.ctx(OWNER_A), appliance_id, "Still warm air", "NOT_COOLING")
    assert choice["outcome"] == "NEEDS_CHOICE"
    continued = report_issue(
        world.ctx(OWNER_A),
        appliance_id,
        "Still warm air",
        "NOT_COOLING",
        continue_issue_id=first["issue"]["issue_id"],
    )
    assert continued == {"outcome": "CONTINUED", "issue": first["issue"]}
    assert world.snapshot() == before  # asking and continuing write nothing

    expect_error(
        "INVALID_INPUT",
        "NOT_AN_ACTIVE_ISSUE",
        report_issue,
        world.ctx(OWNER_A),
        appliance_id,
        "x",
        "OTHER",
        continue_issue_id="nope",
    )
    expect_error(
        "INVALID_INPUT",
        "UNKNOWN_SYMPTOM_CATEGORY",
        report_issue,
        world.ctx(OWNER_A),
        appliance_id,
        "x",
        "BROKEN",
    )
    expect_error(
        "AUTH_DENIED", None, report_issue, world.ctx(VIEW_HELPER_A), appliance_id, "x", "OTHER"
    )


def test_inv8_technician_completion_never_resolves(world: World, expect_error) -> None:
    appliance_id = _ac(world)
    issue = report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")["issue"]
    item = world.table.get(keys.household_pk(HH_A), keys.issue_sk(issue["issue_id"]))
    world.table.put({**item, "status": "SERVICE_PENDING"})  # a confirmed booking (Slice 3)

    # A household member cannot fire a technician or provider outcome at all.
    for event in (
        IssueEvent.VISIT_COMPLETED,
        IssueEvent.APPOINTMENT_CONFIRMED,
        IssueEvent.BOOKING_ENDED,
    ):
        expect_error(
            "AUTH_DENIED",
            "NOT_A_CUSTOMER_EVENT",
            apply_issue_event,
            world.ctx(OWNER_A),
            issue["issue_id"],
            event,
            1,
        )

    # The transition the Slice 3 staff service will use: completion waits for the customer.
    completed = transition_item(
        world.ctx(OWNER_A), {**item, "status": "SERVICE_PENDING"}, IssueEvent.VISIT_COMPLETED, None
    )
    assert completed["status"] == "AWAITING_CUSTOMER"
    world.table.put(completed)

    # Only the customer's own answer resolves it, and a view-only helper cannot give it.
    expect_error(
        "AUTH_DENIED",
        None,
        apply_issue_event,
        world.ctx(VIEW_HELPER_A),
        issue["issue_id"],
        IssueEvent.CUSTOMER_CONFIRMED_RESOLVED,
        2,
    )
    resolved = apply_issue_event(
        world.ctx(OWNER_A), issue["issue_id"], IssueEvent.CUSTOMER_CONFIRMED_RESOLVED, 2
    )
    assert resolved["status"] == "RESOLVED"


def test_undefined_transition_raises_invalid_input(world: World, expect_error) -> None:
    appliance_id = _ac(world)
    issue = report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")["issue"]

    expect_error(
        "INVALID_INPUT",
        "UNDEFINED_TRANSITION",
        apply_issue_event,
        world.ctx(OWNER_A),
        issue["issue_id"],
        IssueEvent.CUSTOMER_CLOSED,
        1,
    )
    assert get_issue(world.ctx(OWNER_A), issue["issue_id"])["status"] == "OPEN"  # unchanged

    # The safety flag is orthogonal to status: it survives later transitions.
    hazard = apply_issue_event(
        world.ctx(OWNER_A),
        issue["issue_id"],
        IssueEvent.HAZARD_REPORTED,
        1,
        safety_reason="BURNING_SMELL",
    )
    assert (hazard["status"], hazard["safety_flag"], hazard["safety_reason"]) == (
        "SERVICE_NEEDED",
        True,
        "BURNING_SMELL",
    )
    resolved = apply_issue_event(
        world.ctx(OWNER_A), issue["issue_id"], IssueEvent.CUSTOMER_CONFIRMED_RESOLVED, 2
    )
    assert (resolved["status"], resolved["safety_flag"]) == ("RESOLVED", True)
    expect_error(
        "RECORD_CONFLICT",
        "STALE_VERSION",
        apply_issue_event,
        world.ctx(OWNER_A),
        issue["issue_id"],
        IssueEvent.CUSTOMER_CLOSED,
        2,
    )
