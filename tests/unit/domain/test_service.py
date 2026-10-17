from __future__ import annotations

import json

import pytest

from app.domain import approvals, overview, service
from app.domain.appliances import register_appliance
from app.domain.issues import get_issue, report_issue
from app.logging import configure_logging
from app.store import keys
from tests.unit.domain.booking_helpers import ADDRESS, CONTACT, issue, ready_request
from tests.unit.domain.world import HH_A, OWNER_A, World


def test_g3_1_records_write_opaque_refs(world: World) -> None:
    appliance_id = register_appliance(world.ctx(OWNER_A), "AC", "Bedroom AC")["appliance_id"]
    issue_id = report_issue(world.ctx(OWNER_A), appliance_id, "Not cooling", "NOT_COOLING")[
        "issue"
    ]["issue_id"]
    request_id = service.draft_service_request(world.ctx(OWNER_A), issue_id)["request"][
        "request_id"
    ]
    for ref, kind in ((appliance_id, "APPLIANCE"), (issue_id, "ISSUE"), (request_id, "CASE")):
        item = world.table.get(keys.ref_pk(ref), keys.META)
        assert (item["household_id"], item["ref_kind"]) == (HH_A, kind), kind
    assert (
        world.table.get(keys.ref_pk(request_id), keys.META)["GSI1PK"] == "CASE"
    )  # coordinator queue


def test_at12_unknown_model_draft_and_missing_address_blocks_submission_only(
    world: World, expect_error
) -> None:
    issue_id = issue(world)  # unknown model, no invoice
    drafted = service.draft_service_request(world.ctx(OWNER_A), issue_id)
    request = drafted["request"]
    assert (drafted["outcome"], request["state"], request["mode"]) == ("CREATED", "DRAFT", "DEMO")
    assert drafted["missing"] == ["address", "contact"]
    assert get_issue(world.ctx(OWNER_A), issue_id)["status"] == "SERVICE_NEEDED"
    slot = service.list_slots(world.ctx(OWNER_A), request["request_id"])["slots"][0]["slot_id"]
    error = expect_error(
        "INVALID_INPUT",
        "MISSING_SERVICE_DETAILS",
        approvals.prepare_action,
        world.ctx(OWNER_A),
        "SUBMIT",
        request["request_id"],
        slot,
    )
    assert error.details["missing"] == ["address", "contact"]
    # The draft itself is kept and reused: one open request per issue.
    again = service.draft_service_request(world.ctx(OWNER_A), issue_id)
    assert (again["outcome"], again["request"]["request_id"]) == ("EXISTING", request["request_id"])


def test_fr27_fee_and_warranty_unknown_never_free(world: World) -> None:
    request = service.draft_service_request(world.ctx(OWNER_A), issue(world))["request"]
    assert request["fee"] == {
        "amount_paise": None,
        "currency": "INR",
        "status": "UNKNOWN",
    }  # not zero
    assert request["warranty"] == "UNKNOWN"
    slot = service.list_slots(world.ctx(OWNER_A), request["request_id"])["slots"][0]
    assert (slot["fee_paise"], slot["fee_status"]) == (49900, "ESTIMATE")  # labelled illustrative


def test_p3_3_address_captured_by_voice_never_logged(
    world: World, capsys: pytest.CaptureFixture[str], expect_error
) -> None:
    configure_logging("INFO")
    request = ready_request(world)
    stored = world.table.get(keys.household_pk(HH_A), keys.request_sk(request["request_id"]))
    assert stored["address"] == {"value": ADDRESS, "status": "USER_REPORTED"}
    assert stored["contact"] == {"value": CONTACT, "status": "USER_REPORTED"}
    # The agent only learns that they are on file; the full values are spoken only in the
    # booking read-back (I12).
    assert (request["address_on_file"], request["contact_on_file"]) == (True, True)
    assert ADDRESS not in str(request)
    assert CONTACT not in str(request)
    assert ADDRESS not in str(overview.get_context(world.ctx(OWNER_A)))
    meta = world.table.get(keys.household_pk(HH_A), keys.META)
    assert meta["service_address"]["value"] == ADDRESS  # remembered for later requests
    later = service.draft_service_request(world.ctx(OWNER_A), issue(world, "Hall AC"))
    assert later["missing"] == []
    assert later["request"]["address_on_file"] is True
    expect_error(
        "RECORD_CONFLICT",
        "STALE_VERSION",
        service.record_service_details,
        world.ctx(OWNER_A),
        request["request_id"],
        "address",
        "Elsewhere",
        1,
    )
    expect_error(
        "INVALID_INPUT",
        "UNKNOWN_FIELD",
        service.record_service_details,
        world.ctx(OWNER_A),
        request["request_id"],
        "email",
        "x",
        request["version"],
    )
    logged = capsys.readouterr().err
    assert ADDRESS not in logged
    assert CONTACT not in logged
    assert all(json.loads(line) for line in logged.splitlines() if line.strip())
