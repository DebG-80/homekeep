from __future__ import annotations

from app.domain.appliances import register_appliance
from app.domain.issues import get_issue, report_issue
from app.domain.observations import next_intake_question, record_observation
from tests.unit.domain.world import OWNER_A, World


def _ac_issue(world: World) -> str:
    appliance_id = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")["appliance_id"]
    return report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")["issue"][
        "issue_id"
    ]


def test_at07_skipped_and_answered_fields_not_reasked_after_restart(world: World) -> None:
    issue_id = _ac_issue(world)
    assert next_intake_question(world.ctx(OWNER_A), issue_id)["field"] == "onset"

    record_observation(world.ctx(OWNER_A), issue_id, "onset", "not sure")  # skipped
    assert next_intake_question(world.ctx(OWNER_A), issue_id)["field"] == "airflow"
    record_observation(world.ctx(OWNER_A), issue_id, "airflow", "Only a little air")

    # Restart: a brand-new session and context rebuilt only from stored records.
    restarted = world.ctx(OWNER_A)
    upcoming = next_intake_question(restarted, issue_id)
    assert upcoming["field"] == "display_code"  # neither onset nor airflow is asked again
    issue = get_issue(restarted, issue_id)
    assert issue["status"] == "TRIAGING"  # the first saved answer started triage
    answers = {o["field"]: (o["value"], o["status"]) for o in issue["observations"]}
    assert answers == {"onset": (None, "UNKNOWN"), "airflow": ("Only a little air", "ANSWERED")}


def test_fr06_unknown_answer_recorded_without_invented_value(world: World, expect_error) -> None:
    issue_id = _ac_issue(world)
    for field, answer in (("onset", "I don't know"), ("airflow", None)):
        saved = record_observation(world.ctx(OWNER_A), issue_id, field, answer)
        assert (saved["value"], saved["status"]) == (None, "UNKNOWN")

    expect_error(
        "INVALID_INPUT",
        "UNKNOWN_FIELD",
        record_observation,
        world.ctx(OWNER_A),
        issue_id,
        "refrigerant_level",
        "low",
    )
    fridge = register_appliance(world.ctx(OWNER_A), "fridge", "Kitchen fridge")["appliance_id"]
    fridge_issue = report_issue(world.ctx(OWNER_A), fridge, "Not cold", "NOT_COOLING")["issue"][
        "issue_id"
    ]
    assert (
        next_intake_question(world.ctx(OWNER_A), fridge_issue) is None
    )  # generic prompts: Slice 2
    expect_error(
        "INVALID_INPUT",
        "NO_INTAKE_FOR_CATEGORY",
        record_observation,
        world.ctx(OWNER_A),
        fridge_issue,
        "onset",
        "today",
    )


def test_nfr05_stale_expected_version_returns_record_conflict(world: World, expect_error) -> None:
    issue_id = _ac_issue(world)
    assert record_observation(world.ctx(OWNER_A), issue_id, "airflow", "none")["version"] == 1
    assert (
        record_observation(world.ctx(OWNER_A), issue_id, "airflow", "weak", expected_version=1)[
            "version"
        ]
        == 2
    )

    # Two writers both holding version 1: the second must not overwrite the first.
    expect_error(
        "RECORD_CONFLICT",
        "STALE_VERSION",
        record_observation,
        world.ctx(OWNER_A),
        issue_id,
        "airflow",
        "strong",
        expected_version=1,
    )
    expect_error(
        "RECORD_CONFLICT",
        "STALE_VERSION",
        record_observation,
        world.ctx(OWNER_A),
        issue_id,
        "airflow",
        "strong",
    )
    answers = {
        o["field"]: o["value"] for o in get_issue(world.ctx(OWNER_A), issue_id)["observations"]
    }
    assert answers == {"airflow": "weak"}
