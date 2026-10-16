from __future__ import annotations

import pytest

from app.domain import guidance
from app.domain.appliances import register_appliance
from app.domain.errors import DomainError
from app.domain.guidance import get_guidance, record_step_result
from app.domain.issues import apply_issue_event, get_issue, report_issue
from app.domain.observations import record_observation
from app.domain.state import IssueEvent
from app.store import keys
from tests.unit.domain.world import HH_A, OWNER_A, World


def _ac(
    world: World, model: str | None, status: str = "VERIFIED", nickname: str = "Bedroom AC"
) -> str:
    appliance_id = register_appliance(world.ctx(OWNER_A), "AC", nickname)["appliance_id"]
    if model is not None:
        item = world.table.get(keys.household_pk(HH_A), keys.appliance_sk(appliance_id))
        field = {
            "value": model,
            "status": status,
            "provenance": {"source": "REVIEWER", "document_id": "doc-1"},
        }
        world.table.put({**item, "fields": {**item["fields"], "model": field}})
    return appliance_id


def _issue(world: World, appliance_id: str, category: str = "NOT_COOLING") -> str:
    return report_issue(world.ctx(OWNER_A), appliance_id, "It is not working right", category)[
        "issue"
    ]["issue_id"]


def _refusal(world: World, issue_id: str) -> DomainError:
    with pytest.raises(DomainError) as caught:
        get_guidance(world.ctx(OWNER_A), issue_id)
    assert caught.value.code.value == "NO_APPROVED_GUIDANCE"
    assert caught.value.details["offer"] == "SERVICE"
    return caught.value


def test_at04_guessed_model_cannot_unlock_guidance(world: World) -> None:
    appliance_id = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC", model_claim="FL-18i")[
        "appliance_id"
    ]
    refusal = _refusal(world, _issue(world, appliance_id))
    assert refusal.reason == "UNVERIFIED_MODEL"
    assert refusal.details[
        "generic_prompts"
    ]  # unknown-model mode: reviewed observation prompts only
    assert "step" not in refusal.details


def test_at04_verified_model_returns_step_with_citation(world: World) -> None:
    issue_id = _issue(world, _ac(world, "FL-18i"))
    result = get_guidance(world.ctx(OWNER_A), issue_id)
    assert result["step"]["step_id"]
    assert result["step"]["speech"]
    evidence = result["evidence"]
    assert evidence["catalog_item"] == "frostline-fl-18i"
    assert evidence["version"] == "v2"  # never the withdrawn v1
    assert evidence["document_id"]
    assert evidence["locator"]
    assert evidence["excerpt"]


def test_at04_conflicting_sources_return_no_model_step(world: World) -> None:
    appliance_id = _ac(world, "FL-24x")
    issue_id = _issue(world, appliance_id, "ERROR_CODE")
    record_observation(world.ctx(OWNER_A), issue_id, "display_code", "E4")
    assert (
        _refusal(world, issue_id).reason == "CONFLICTING_SOURCES"
    )  # the two manuals disagree on E4

    agreed = _issue(world, _ac(world, "FL-24x", nickname="Hall AC"), "ERROR_CODE")
    record_observation(world.ctx(OWNER_A), agreed, "display_code", "E1")
    assert get_guidance(world.ctx(OWNER_A), agreed)["step"]["step_id"]  # both manuals agree on E1

    # An open conflict on the appliance's own model record also blocks model-specific steps.
    disputed = _ac(world, "FL-18i", nickname="Guest AC")
    item = world.table.get(keys.household_pk(HH_A), keys.appliance_sk(disputed))
    world.table.put(
        {**item, "conflicts": [{"field": "model", "value": "FL-24x", "status": "USER_REPORTED"}]}
    )
    assert _refusal(world, _issue(world, disputed)).reason == "CONFLICTING_SOURCES"


def test_at24_withdrawn_item_blocks_new_steps(world: World) -> None:
    issue_id = _issue(world, _ac(world, "FL-18i"))
    first = get_guidance(world.ctx(OWNER_A), issue_id)["step"]["step_id"]
    record_step_result(world.ctx(OWNER_A), issue_id, first, "UNSUCCESSFUL")

    world.table.put(
        {
            "PK": "CATALOG",
            "SK": "STATUS#frostline-fl-18i",
            "status": "WITHDRAWN",
            "reason": "TEST",
        }
    )
    assert _refusal(world, issue_id).reason == "WITHDRAWN"
    # The case keeps the source history of the step already given.
    (step,) = get_issue(world.ctx(OWNER_A), issue_id)["steps"]
    assert (step["step_id"], step["catalog_version"]) == (first, "v2")


def _next_step(world: World, issue_id: str) -> str | None:
    try:
        return get_guidance(world.ctx(OWNER_A), issue_id)["step"]["step_id"]
    except DomainError as refusal:
        if refusal.reason != "STEPS_EXHAUSTED":
            raise
        return None


def test_at09_already_tried_records_and_advances(world: World) -> None:
    issue_id = _issue(world, _ac(world, "FL-18i"))
    seen: list[str] = []
    while (step := _next_step(world, issue_id)) is not None:
        assert step not in seen  # "already tried that" never repeats the step
        seen.append(step)
        saved = record_step_result(world.ctx(OWNER_A), issue_id, step, "COMPLETED")
        assert saved["issue_status"] != "RESOLVED"  # completing a check is not a repair
    assert len(seen) >= 2
    assert _refusal(world, issue_id).reason == "STEPS_EXHAUSTED"  # then service is offered


def test_at09_retrieval_failure_offers_service_without_guidance(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    issue_id = _issue(world, _ac(world, "FL-18i"))

    def broken() -> None:
        raise OSError("catalog unreadable")

    monkeypatch.setattr(guidance, "load_catalog", broken)
    refusal = _refusal(world, issue_id)
    assert refusal.reason == "RETRIEVAL_FAILURE"
    assert "step" not in refusal.details


def test_inv7_safety_flag_blocks_guidance_even_when_verified(world: World) -> None:
    issue_id = _issue(world, _ac(world, "FL-18i"))
    apply_issue_event(world.ctx(OWNER_A), issue_id, IssueEvent.HAZARD_REPORTED, 1, "BURNING_SMELL")
    assert _refusal(world, issue_id).reason == "SAFETY_FLAG"
