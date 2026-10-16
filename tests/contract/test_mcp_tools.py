from __future__ import annotations

from app.store import keys
from tests.contract.live import LiveServer, call_tool

BEDROOM_AC = "qa-a-ac-bedroom"  # seeded VERIFIED as FL-18i (G2-1)
HALL_AC = "qa-a-ac-hall"  # model unknown


def _ok(envelope: dict) -> dict:
    assert envelope["status"] == "OK", envelope
    assert envelope["correlation_id"]
    return envelope["data"]


def test_mcp_every_customer_tool_returns_the_envelope(live: LiveServer) -> None:
    context = _ok(call_tool(live, "get_context"))
    assert context["storage_consent"] == "GRANTED"
    assert {a["appliance_id"] for a in context["appliances"]} >= {BEDROOM_AC, HALL_AC}
    assert context["local_date"]

    resolved = _ok(call_tool(live, "resolve_appliance", {"reference": "the bedroom AC"}))
    assert [m["appliance_id"] for m in resolved["matches"]] == [BEDROOM_AC]
    _ok(call_tool(live, "register_appliance", {"category": "TV", "nickname": "Bedroom TV"}))
    _ok(
        call_tool(
            live,
            "update_appliance_fact",
            {
                "appliance_id": HALL_AC,
                "field": "brand",
                "value": "Frostline",
                "expected_version": 1,
            },
        )
    )

    reported = _ok(
        call_tool(
            live,
            "report_issue",
            {
                "appliance_id": BEDROOM_AC,
                "symptom_text": "Not cooling at all",
                "symptom_category": "NOT_COOLING",
            },
        )
    )
    issue_id = reported["issue"]["issue_id"]
    issue = _ok(call_tool(live, "get_issue", {"issue_id": issue_id}))
    assert issue["next_question"]["field"] == "onset"  # G2-6
    observed = _ok(
        call_tool(
            live,
            "record_observation",
            {"issue_id": issue_id, "field": "onset", "value": "this morning"},
        )
    )
    assert observed["next_question"]["field"] == "airflow"

    guidance = _ok(call_tool(live, "get_guidance", {"issue_id": issue_id}))
    assert guidance["step"]["speech"]
    assert guidance["evidence"]["document_id"]  # retrieved text only in a typed evidence field
    assert guidance["evidence"]["locator"]
    step_result = _ok(
        call_tool(
            live,
            "record_step_result",
            {
                "issue_id": issue_id,
                "step_id": guidance["step"]["step_id"],
                "result": "UNSUCCESSFUL",
            },
        )
    )
    assert step_result["issue_status"] != "RESOLVED"
    warning = _ok(
        call_tool(
            live, "report_warning_sign", {"sign": "there is smoke coming out", "issue_id": issue_id}
        )
    )
    assert warning["reason"] == "SMOKE"
    assert warning["speech"]

    # A typed error: customer-safe message, support reference = correlation ID, sent header kept.
    other = _ok(
        call_tool(
            live,
            "report_issue",
            {
                "appliance_id": HALL_AC,
                "symptom_text": "Weak air",
                "symptom_category": "WEAK_AIRFLOW",
            },
        )
    )
    refused = call_tool(
        live,
        "get_guidance",
        {"issue_id": other["issue"]["issue_id"]},
        headers={"X-Correlation-Id": "corr-contract-1"},
    )
    assert refused["status"] == "ERROR"
    assert refused["correlation_id"] == "corr-contract-1"
    error = refused["error"]
    assert (error["code"], error["reason"]) == ("NO_APPROVED_GUIDANCE", "UNVERIFIED_MODEL")
    assert error["support_reference"] == "corr-contract-1"
    assert error["message"]
    assert "Traceback" not in str(refused)


def test_nfr04_cross_tenant_call_returns_not_found(live: LiveServer) -> None:
    issue_id = _ok(
        call_tool(
            live,
            "report_issue",
            {
                "appliance_id": BEDROOM_AC,
                "symptom_text": "Not cooling",
                "symptom_category": "NOT_COOLING",
            },
        )
    )["issue"]["issue_id"]

    stolen = call_tool(live, "get_issue", {"issue_id": issue_id}, identity="b_owner")
    assert (stolen["status"], stolen["error"]["code"], stolen["error"]["reason"]) == (
        "ERROR",
        "INVALID_INPUT",
        "NOT_FOUND",
    )
    assert issue_id not in str(stolen["error"])
    # B's search only ever sees B's own appliances (its Study AC matches "AC"), never A's.
    b_matches = _ok(
        call_tool(live, "resolve_appliance", {"reference": "bedroom AC"}, identity="b_owner")
    )["matches"]
    assert [m["appliance_id"] for m in b_matches] == ["qa-b-ac-study"]
    # Membership is read on every call: revoked helpers and staff get no household data.
    for identity in ("a_helper_revoked", "coordinator"):
        denied = call_tool(live, "get_context", identity=identity)
        assert (denied["status"], denied["error"]["code"]) == ("ERROR", "AUTH_DENIED"), identity


def test_inv5_replay_with_same_turn_header_is_idempotent(live: LiveServer) -> None:
    headers = {"X-HK-Turn-Id": "turn-contract-7", "X-HK-Session-Id": "session-contract"}
    args = {"category": "TV", "nickname": "Bedroom TV"}
    first = _ok(call_tool(live, "register_appliance", args, headers=headers))
    again = _ok(call_tool(live, "register_appliance", args, headers=headers))
    assert again == first
    tvs = [
        a
        for a in live.table.query(keys.household_pk("qa-a"), keys.APPLIANCE_PREFIX)
        if a["nickname"] == "Bedroom TV"
    ]
    assert len(tvs) == 1


def test_p2_3_missing_turn_header_still_works(live: LiveServer) -> None:
    # External clients (MCP Inspector) send no X-HK-Turn-Id: the server generates one per call.
    first = _ok(call_tool(live, "register_appliance", {"category": "TV", "nickname": "Study TV"}))
    second = _ok(call_tool(live, "register_appliance", {"category": "TV", "nickname": "Guest TV"}))
    assert first["appliance_id"] != second["appliance_id"]
