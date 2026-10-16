from __future__ import annotations

import pytest

from app.domain.appliances import register_appliance, resolve_appliance, update_appliance_fact
from app.domain.errors import DomainError
from app.domain.events import list_events
from app.domain.household import get_household
from app.domain.issues import apply_issue_event, get_issue, report_issue
from app.domain.observations import next_intake_question, record_observation
from app.domain.state import IssueEvent
from tests.unit.domain.world import HH_A, OWNER_A, OWNER_B, TECHNICIAN, World


def test_nfr04_household_b_cannot_read_or_mutate_household_a(world: World) -> None:
    appliance_id = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")["appliance_id"]
    issue_id = report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")[
        "issue"
    ]["issue_id"]
    record_observation(world.ctx(OWNER_A), issue_id, "onset", "yesterday")
    a_before = world.items(HH_A)

    b = world.ctx(OWNER_B)
    attempts = [
        (get_issue, (issue_id,)),
        (report_issue, (appliance_id, "Not cooling", "NOT_COOLING")),
        (update_appliance_fact, (appliance_id, "model", "FL-18i", 1)),
        (record_observation, (issue_id, "airflow", "none")),
        (apply_issue_event, (issue_id, IssueEvent.SERVICE_REQUESTED, 2)),
        (next_intake_question, (issue_id,)),
    ]
    for call, args in attempts:
        with pytest.raises(DomainError) as caught:
            call(b, *args)
        # Not found in B's own household: no existence oracle and none of A's identifiers.
        assert (caught.value.code.value, caught.value.reason) == ("INVALID_INPUT", "NOT_FOUND"), (
            call
        )
        assert HH_A not in repr(caught.value.details)
        assert appliance_id not in repr(caught.value.details)

    # Reads that search come back empty rather than leaking A's records.
    assert resolve_appliance(b, "Bedroom AC")["matches"] == []
    assert list_events(b, appliance_id) == []
    assert get_household(b)["version"] == 1  # B sees only B

    # Staff have no household scope in this slice, so every household entry point refuses them.
    for call, args in [*attempts, (resolve_appliance, ("Bedroom AC",)), (get_household, ())]:
        with pytest.raises(DomainError) as caught:
            call(world.ctx(TECHNICIAN), *args)
        assert caught.value.code.value == "AUTH_DENIED"

    assert world.items(HH_A) == a_before  # A is untouched
