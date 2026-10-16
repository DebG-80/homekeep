from __future__ import annotations

from app.orchestrator.fake_model import TurnScripts, call, say
from app.security.local_issuer import LocalIssuer
from app.store import keys
from app.store.table import Table
from scripts import seed
from tests.contract.live import api, new_session, serve, turn


def test_at11_restart_resumes_issue_with_steps_from_records(
    table: Table, issuer: LocalIssuer
) -> None:
    seed.seed_local(table)
    scripts = TurnScripts()
    with serve(table, issuer, scripts) as first_run:
        session_id = new_session(first_run)
        scripts.queue(
            [
                call(
                    "report_issue",
                    appliance_id="qa-a-ac-bedroom",
                    symptom_text="Not cooling",
                    symptom_category="NOT_COOLING",
                ),
                say("Noted."),
            ]
        )
        turn(first_run, session_id, "My bedroom AC is not cooling")
        issue_id = next(
            i["issue_id"]
            for i in table.query(keys.household_pk("qa-a"), keys.ISSUE_PREFIX)
            if i.get("kind") == "ISSUE"
        )
        scripts.queue(
            [
                call("record_observation", issue_id=issue_id, field="onset", value="yesterday"),
                call("get_guidance", issue_id=issue_id),
                say("Noted."),
            ]
        )
        turn(first_run, session_id, "It started yesterday")
        step_id = scripts.models[-1].results("get_guidance")[-1]["data"]["step"]["step_id"]
        scripts.queue(
            [
                call(
                    "record_step_result", issue_id=issue_id, step_id=step_id, result="UNSUCCESSFUL"
                ),
                say("Noted."),
            ]
        )
        turn(first_run, session_id, "I tried that, no change")

    # A brand-new process (new attestation key, new in-memory state) over the same table.
    with serve(table, issuer, scripts) as second_run:
        state = api(second_run, "GET", f"/api/sessions/{session_id}/state").json()
        assert state["active_issue_id"] == issue_id
        assert len(state["messages"]) == 6  # three user turns and three replies
        scripts.queue([call("get_context"), say("Welcome back.")])
        turn(second_run, session_id, "Let's continue with the AC problem")
        again = api(second_run, "GET", f"/api/sessions/{session_id}/state").json()

    context = scripts.models[-1].results("get_context")[-1]["data"]
    (resumed,) = [i for i in context["open_issues"] if i["issue_id"] == issue_id]
    assert resumed["status"] == "TRIAGING"
    assert resumed["next_question"]["field"] == "airflow"  # onset is not asked again
    assert again["session_id"] == session_id
    assert len(again["messages"]) == 8
    steps = table.query(keys.household_pk("qa-a"), keys.step_prefix(issue_id))
    assert [(s["step_id"], s["result"]) for s in steps] == [(step_id, "UNSUCCESSFUL")]
