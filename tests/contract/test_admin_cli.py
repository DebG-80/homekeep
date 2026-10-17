"""AT-24 end to end: a catalog item withdrawn with `hk-admin` is refused over MCP, and a case's
earlier steps keep their source history (FR-23-AC2)."""

from __future__ import annotations

import io

from scripts import hk_admin
from tests.contract.live import LiveServer, call_tool

BEDROOM_AC = "qa-a-ac-bedroom"  # seeded VERIFIED as FL-18i


def _new_issue(live: LiveServer) -> str:
    reported = call_tool(
        live,
        "report_issue",
        {
            "appliance_id": BEDROOM_AC,
            "symptom_text": "It is not cooling",
            "symptom_category": "NOT_COOLING",
            "confirmed_distinct": True,
        },
    )
    return reported["data"]["issue"]["issue_id"]


def test_at24_withdrawn_item_refused_over_mcp_history_kept(live: LiveServer) -> None:
    issue_id = _new_issue(live)
    step = call_tool(live, "get_guidance", {"issue_id": issue_id})
    assert step["status"] == "OK"
    step_id = step["data"]["step"]["step_id"]
    recorded = call_tool(
        live,
        "record_step_result",
        {"issue_id": issue_id, "step_id": step_id, "result": "UNSUCCESSFUL"},
    )
    assert recorded["status"] == "OK"

    out = io.StringIO()
    code = hk_admin.main(
        ["--target", "local", "catalog", "withdraw", "frostline-fl-18i", "--reason", "Recalled"],
        out=out,
        table=live.table,
    )
    assert code == 0, out.getvalue()

    refused = call_tool(live, "get_guidance", {"issue_id": _new_issue(live)})
    assert (refused["status"], refused["error"]["reason"]) == ("ERROR", "WITHDRAWN")
    detail = call_tool(live, "get_issue", {"issue_id": issue_id})["data"]
    assert [s["step_id"] for s in detail["steps"]] == [step_id]  # nothing erased

    assert (
        hk_admin.main(
            ["--target", "local", "catalog", "restore", "frostline-fl-18i"],
            out=out,
            table=live.table,
        )
        == 0
    )
    assert call_tool(live, "get_guidance", {"issue_id": _new_issue(live)})["status"] == "OK"
