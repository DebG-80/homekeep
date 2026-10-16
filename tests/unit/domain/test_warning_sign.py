from __future__ import annotations

import pytest

from app.catalog.loader import load_catalog
from app.domain.appliances import register_appliance
from app.domain.errors import DomainError
from app.domain.guidance import get_guidance
from app.domain.issues import get_issue, report_issue, report_warning_sign
from app.store import keys
from tests.unit.domain.world import HH_A, OWNER_A, World


def _approved(reason: str) -> str:
    return next(h.speech for h in load_catalog().hazards if h.reason == reason)


def test_at08_warning_sign_sets_flag_and_stops_routine_steps(world: World) -> None:
    appliance_id = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")["appliance_id"]
    item = world.table.get(keys.household_pk(HH_A), keys.appliance_sk(appliance_id))
    verified = {"value": "FL-18i", "status": "VERIFIED", "provenance": {"source": "REVIEWER"}}
    world.table.put({**item, "fields": {**item["fields"], "model": verified}})
    issue_id = report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")[
        "issue"
    ]["issue_id"]
    assert get_guidance(world.ctx(OWNER_A), issue_id)["step"]  # routine guidance was available

    warning = report_warning_sign(
        world.ctx(OWNER_A), "it smells like something is burning", issue_id
    )
    assert warning["reason"] == "BURNING_SMELL"
    assert warning["speech"] == _approved("BURNING_SMELL")  # approved text, verbatim
    issue = get_issue(world.ctx(OWNER_A), issue_id)
    assert (issue["status"], issue["safety_flag"], issue["safety_reason"]) == (
        "SERVICE_NEEDED",
        True,
        "BURNING_SMELL",
    )
    with pytest.raises(DomainError) as caught:
        get_guidance(world.ctx(OWNER_A), issue_id)
    assert caught.value.reason == "SAFETY_FLAG"  # routine checks stop

    # A paraphrase the lexicon misses still gets the approved general escalation.
    paraphrase = report_warning_sign(world.ctx(OWNER_A), "there is a strange scorched odour", None)
    assert (paraphrase["reason"], paraphrase["speech"]) == ("GENERAL", _approved("GENERAL"))
    assert paraphrase["issue"] is None
