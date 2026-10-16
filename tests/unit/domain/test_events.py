from __future__ import annotations

from app.domain.appliances import register_appliance, update_appliance_fact
from app.domain.events import list_events
from app.domain.household import ConsentDecision, ConsentPurpose, record_consent
from app.domain.issues import apply_issue_event, report_issue
from app.domain.observations import record_observation
from app.domain.state import IssueEvent
from app.store import keys
from tests.unit.domain.world import HH_A, OWNER_A, VIEW_HELPER_A, World


def test_fr28_every_mutation_appends_one_event_with_correlation_and_versions(world: World) -> None:
    def events() -> list[dict]:
        return world.items(HH_A, keys.EVENT_PREFIX)

    def mutate(correlation: str, call, *args, **kwargs):
        before = len(events())
        result = call(world.ctx(OWNER_A, correlation_id=correlation), *args, **kwargs)
        new = [e for e in events() if e["correlation_id"] == correlation]
        assert len(events()) == before + 1, call.__name__
        assert len(new) == 1, call.__name__
        assert new[0]["actor_sub"] == OWNER_A.sub
        assert new[0]["actor_role"] == "OWNER"
        assert new[0]["result"] == "OK"
        return result, new[0]

    _, consent = mutate(
        "c-1", record_consent, ConsentPurpose.SHARING, ConsentDecision.DECLINED, "v1"
    )
    assert (consent["action"], consent["prior_version"], consent["new_version"]) == (
        "CONSENT_RECORDED",
        1,
        2,
    )

    appliance, registered = mutate("c-2", register_appliance, "AC", "Bedroom AC")
    appliance_id = appliance["appliance_id"]
    assert (registered["action"], registered["prior_version"], registered["new_version"]) == (
        "APPLIANCE_REGISTERED",
        None,
        1,
    )
    _, fact = mutate("c-3", update_appliance_fact, appliance_id, "brand", "Frostline", 1)
    assert (fact["prior_version"], fact["new_version"]) == (1, 2)

    issue, reported = mutate("c-4", report_issue, appliance_id, "Not cooling", "NOT_COOLING")
    issue_id = issue["issue"]["issue_id"]
    assert reported["action"] == "ISSUE_REPORTED"
    _, observed = mutate("c-5", record_observation, issue_id, "onset", "yesterday")
    assert observed["action"] == "OBSERVATION_RECORDED"
    _, hazard = mutate(
        "c-6", apply_issue_event, issue_id, IssueEvent.HAZARD_REPORTED, 2, "BURNING_SMELL"
    )
    assert (hazard["action"], hazard["prior_version"], hazard["new_version"]) == (
        "ISSUE_HAZARD_REPORTED",
        2,
        3,
    )

    # The appliance timeline is chronological and readable with a view grant.
    timeline = list_events(world.ctx(VIEW_HELPER_A), appliance_id)
    assert [e["correlation_id"] for e in timeline] == ["c-2", "c-3", "c-4", "c-5", "c-6"]
    assert list_events(world.ctx(OWNER_A), None)[0]["correlation_id"] == "c-1"
