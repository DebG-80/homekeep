from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import pytest

from app.catalog.hazards import hazard_for
from app.channel import templates
from app.domain.errors import REASON_MESSAGES
from app.orchestrator.fake_model import TurnScripts, call, say
from app.security.local_issuer import LocalIssuer
from app.store import keys
from app.store.table import Table
from scripts import seed
from tests.contract.live import LiveServer, api, new_session, serve, spoken, turn

BEDROOM_AC = "qa-a-ac-bedroom"

Server = Callable[..., AbstractContextManager[tuple[LiveServer, TurnScripts]]]


@pytest.fixture
def server(table: Table, issuer: LocalIssuer) -> Server:
    seed.seed_local(table)

    @contextmanager
    def start(**env: str) -> Iterator[tuple[LiveServer, TurnScripts]]:
        scripts = TurnScripts()
        with serve(table, issuer, scripts, **env) as live:
            yield live, scripts

    return start


def _issue_ids(live: LiveServer) -> list[str]:
    return [
        i["issue_id"]
        for i in live.table.query(keys.household_pk("qa-a"), keys.ISSUE_PREFIX)
        if i.get("kind") == "ISSUE"
    ]


def _open_issue(
    live: LiveServer,
    scripts: TurnScripts,
    session_id: str,
    appliance_id: str = BEDROOM_AC,
    category: str = "NOT_COOLING",
) -> str:
    scripts.queue(
        [
            call(
                "report_issue",
                appliance_id=appliance_id,
                symptom_text="It is not working",
                symptom_category=category,
            ),
            say("I've noted that."),
        ]
    )
    turn(live, session_id, "There is a problem with my AC")
    return _issue_ids(live)[-1]


def test_fr22_same_turn_id_replays_stored_response(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        scripts.queue([say("Hello. How can I help with your appliances today?")])
        first = turn(live, session_id, "hello", turn_id="turn-replay-1")
        again = turn(live, session_id, "hello", turn_id="turn-replay-1")
    assert again == first
    assert len(scripts.models) == 1  # the model ran once; the retry got the stored response


def test_fr21_command_grammar_handled_without_the_model(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        scripts.queue([say("Your bedroom AC is saved. What seems to be the problem?")])
        said = spoken(turn(live, session_id, "hello"))
        models_before = len(scripts.models)

        repeat = turn(live, session_id, "Say that again please")
        assert spoken(repeat) == said  # repeated without changing anything
        slower = turn(live, session_id, "slower")
        assert slower["speech_rate"] == "slow"
        assert spoken(slower) == templates.COMMANDS["SLOWER"]
        stopped = turn(live, session_id, "Stop")
        assert spoken(stopped) == templates.COMMANDS["STOP"]
        person = turn(live, session_id, "I want to talk to a person")
        assert spoken(person) == templates.COMMANDS["HUMAN"]
        assert {r["handled_by"] for r in (repeat, slower, stopped, person)} == {"COMMAND"}
        assert len(scripts.models) == models_before  # the model was never called


def test_at08_hazard_phrase_escalates_with_approved_text_and_blocks_steps(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        issue_id = _open_issue(live, scripts, session_id)
        models_before = len(scripts.models)

        response = turn(live, session_id, "Oh no, it smells like something is burning")
        assert response["handled_by"] == "HAZARD"
        assert spoken(response) == hazard_for("BURNING_SMELL").speech  # approved text, verbatim
        assert len(scripts.models) == models_before  # deterministic: no model involved
        issue = live.table.get(keys.household_pk("qa-a"), keys.issue_sk(issue_id))
        assert (issue["safety_flag"], issue["safety_reason"]) == (True, "BURNING_SMELL")

        scripts.queue([call("get_guidance", issue_id=issue_id), say("Try turning it down.")])
        after = turn(live, session_id, "what should I check now")
    refused = scripts.models[-1].results("get_guidance")[-1]
    assert (refused["status"], refused["error"]["reason"]) == ("ERROR", "SAFETY_FLAG")
    assert spoken(after) == REASON_MESSAGES["SAFETY_FLAG"]  # the server's refusal, never the tip


def test_at08_paraphrase_caught_by_agent_warning_sign_tool(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        issue_id = _open_issue(live, scripts, session_id)
        scripts.queue(
            [
                call("report_warning_sign", sign="a strange scorched odour", issue_id=issue_id),
                say("No problem, carry on using it."),
            ]
        )
        response = turn(live, session_id, "There's a strange scorched odour near it")
    assert response["handled_by"] == "AGENT"
    assert spoken(response) == hazard_for("GENERAL").speech  # the model's words are replaced
    assert "carry on" not in spoken(response)


def test_at09_guidance_spoken_from_approved_wording_with_citation(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        issue_id = _open_issue(live, scripts, session_id)
        scripts.queue(
            [
                call("get_guidance", issue_id=issue_id),
                say("Just fiddle with the buttons until it works."),
            ]
        )
        response = turn(live, session_id, "What can I check?")
    step = scripts.models[-1].results("get_guidance")[-1]["data"]
    assert spoken(response).startswith(
        step["step"]["speech"]
    )  # approved wording, not the paraphrase
    assert "fiddle" not in spoken(response)
    assert response["display"]["citation"]["locator"] == step["evidence"]["locator"]
    assert response["display"]["citation"]["document_id"] == step["evidence"]["document_id"]


def test_at10_malicious_manual_cannot_trigger_trusted_action_or_disclosure(server: Server) -> None:
    with server() as (live, scripts):
        hall = live.table.get(keys.household_pk("qa-a"), keys.appliance_sk("qa-a-ac-hall"))
        verified = {"value": "FL-24x", "status": "VERIFIED", "provenance": {"source": "REVIEWER"}}
        live.table.put({**hall, "fields": {**hall["fields"], "model": verified}})
        session_id = new_session(live)
        issue_id = _open_issue(live, scripts, session_id, "qa-a-ac-hall", "NOISE")
        scripts.queue(
            [
                call(
                    "get_guidance", issue_id=issue_id
                ),  # evidence carries the injected instruction
                call("confirm_action", pending_ref="anything"),  # the model obeys the injection...
                call("cancel_pending_action"),
                say("Your booking is confirmed. Other customers live at qa-b."),
            ]
        )
        response = turn(live, session_id, "It is making a humming noise")
    model = scripts.models[-1]
    assert "SYSTEM NOTE" in model.results("get_guidance")[-1]["data"]["evidence"]["excerpt"]
    # ...but trusted tools are unreachable: Strands refuses them before any request is made.
    for tool in ("confirm_action", "cancel_pending_action"):
        (refusal,) = model.results(tool)
        assert refusal == {"text": f"Unknown tool: {tool}"}, refusal
    assert not {"confirm_action", "cancel_pending_action"} & set(model.tools_offered)
    # The model's injected reply is discarded: the turn offered an approved step, so the server
    # speaks the catalog wording verbatim (the output guard is the second line of defence).
    step = model.results("get_guidance")[-1]["data"]["step"]
    assert spoken(response).startswith(step["speech"])
    assert "confirmed" not in spoken(response).casefold()
    assert "qa-b" not in str(response)
    approvals = [
        i for i in live.table.query(keys.household_pk("qa-a")) if i["SK"].startswith("APPROVAL#")
    ]
    assert approvals == []


def test_at10_output_guard_blocks_unbacked_confirmation(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        scripts.queue([say("Great news, your technician is booked for tomorrow morning.")])
        response = turn(live, session_id, "Can someone come tomorrow?")
    assert response["guarded"] is True
    assert spoken(response) == templates.OUTPUT_GUARD_FALLBACK
    assert "booked" not in spoken(response)


def test_nfr12_tool_cycle_cap_hands_off(server: Server) -> None:
    with server(MAX_TOOL_CYCLES="3") as (live, scripts):
        session_id = new_session(live)
        scripts.queue([call("get_context") for _ in range(10)])
        response = turn(live, session_id, "Tell me everything")
    assert response["handled_by"] == "CAP"
    assert spoken(response) == templates.CYCLE_CAP
    assert len(scripts.models[-1].results("get_context")) == 3


def test_nfr12_daily_turn_cap_refuses_politely(server: Server) -> None:
    with server(DAILY_TURN_CAP="2") as (live, scripts):
        session_id = new_session(live)
        for _ in range(2):
            scripts.queue([say("Okay.")])
            turn(live, session_id, "hello")
        models_before = len(scripts.models)
        capped = turn(live, session_id, "hello again")
    assert capped["handled_by"] == "CAP"
    assert spoken(capped) == templates.DAILY_CAP
    assert len(scripts.models) == models_before


def test_fr07_guards_run_before_the_daily_cap(server: Server) -> None:
    with server(DAILY_TURN_CAP="1") as (live, scripts):
        session_id = new_session(live)
        scripts.queue([say("Okay.")])
        turn(live, session_id, "hello")  # uses today's only agent turn
        hazard = turn(live, session_id, "it's smoking")
        assert (hazard["handled_by"], spoken(hazard)) == ("HAZARD", hazard_for("SMOKE").speech)
        assert turn(live, session_id, "stop")["handled_by"] == "COMMAND"
        assert turn(live, session_id, "what else can I check")["handled_by"] == "CAP"


def test_at08_hazard_without_active_issue_holds_guidance_household_wide(server: Server) -> None:
    with server() as (live, scripts):
        earlier = new_session(live)
        old_issue = _open_issue(live, scripts, earlier)
        fresh = new_session(live)  # a new session knows no active issue
        response = turn(live, fresh, "I can see sparks")
        assert (response["handled_by"], spoken(response)) == ("HAZARD", hazard_for("SPARKS").speech)
        issue = live.table.get(keys.household_pk("qa-a"), keys.issue_sk(old_issue))
        assert issue["safety_flag"] is True  # the household's open issue is flagged

        # A problem reported afterwards is born flagged, and no routine check is offered.
        new_issue = _open_issue(live, scripts, fresh, "qa-a-ac-hall", "WEAK_AIRFLOW")
        assert (
            live.table.get(keys.household_pk("qa-a"), keys.issue_sk(new_issue))["safety_flag"]
            is True
        )
        scripts.queue([call("get_guidance", issue_id=old_issue), say("Try the fan button.")])
        after = turn(live, fresh, "what can I check")
    assert spoken(after) == REASON_MESSAGES["SAFETY_FLAG"]


def test_at08_hazard_is_retried_when_recording_fails(
    server: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.channel import pipeline

    real = pipeline.call_trusted
    failures = {"left": 2}

    async def flaky(**kwargs: Any) -> dict[str, Any]:
        if kwargs["tool"] == "report_warning_sign" and failures["left"] > 0:
            failures["left"] -= 1
            raise ConnectionError("loopback unavailable")
        return await real(**kwargs)

    monkeypatch.setattr(pipeline, "call_trusted", flaky)
    with server() as (live, scripts):
        session_id = new_session(live)
        issue_id = _open_issue(live, scripts, session_id)
        response = turn(live, session_id, "there's smoke coming out")
        assert spoken(response) == hazard_for("SMOKE").speech  # the advice is never withheld
        state = live.table.get(keys.household_pk("qa-a"), f"SESSION#{session_id}")
        assert state["pending_hazard"]["reason"] == "SMOKE"  # the failed write is remembered
        scripts.queue([say("Okay.")])
        turn(live, session_id, "okay")  # the next turn records it before anything else
        issue = live.table.get(keys.household_pk("qa-a"), keys.issue_sk(issue_id))
        assert (issue["safety_flag"], issue["safety_reason"]) == (True, "SMOKE")
        assert (
            live.table.get(keys.household_pk("qa-a"), f"SESSION#{session_id}")["pending_hazard"]
            is None
        )


def test_at08_warning_sign_spoken_even_after_cap_or_failed_call(server: Server) -> None:
    with server(MAX_TOOL_CYCLES="1") as (live, scripts):
        session_id = new_session(live)
        scripts.queue(
            [
                call("report_warning_sign", sign="sparks from the plug"),
                call("get_context"),
                say("Fine."),
            ]
        )
        capped = turn(live, session_id, "something odd happened near the plug")
        assert spoken(capped) == hazard_for("SPARKS").speech  # not the cycle-cap message
        scripts.queue(
            [
                call("report_warning_sign", sign="it gave me a jolt", issue_id="not-a-real-issue"),
                say("Carry on."),
            ]
        )
        failed = turn(live, session_id, "it did something odd")
    assert spoken(failed) == hazard_for("SHOCK").speech  # the tool failed; the advice did not


def test_fr22_retry_while_original_in_flight_does_not_rerun_the_agent(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        # The original turn has claimed its record and is still running.
        claim = {
            "PK": keys.household_pk("qa-a"),
            "SK": f"TURN#{session_id}#turn-busy",
            "kind": "TURN",
            "status": "IN_PROGRESS",
            "response": None,
        }
        live.table.put(claim)
        response = turn(live, session_id, "hello", turn_id="turn-busy")
    assert response["handled_by"] == "IN_PROGRESS"
    assert spoken(response) == templates.STILL_WORKING
    assert scripts.models == []  # the agent did not run a second time


def test_blank_text_is_rejected_and_never_saved(server: Server) -> None:
    from tests.contract.live import api

    with server() as (live, _):
        session_id = new_session(live)
        body = {"session_id": session_id, "turn_id": "t-blank", "text": "   "}
        assert api(live, "POST", "/api/turns", json=body).status_code == 422
        state = api(live, "GET", f"/api/sessions/{session_id}/state").json()
    assert state["messages"] == []


def test_nfr01_turn_budget_is_a_wall_clock(server: Server) -> None:
    import time

    from app.orchestrator.fake_model import wait

    with server(TURN_BUDGET_SECONDS="1") as (live, scripts):
        session_id = new_session(live)
        scripts.queue([wait(6), say("Too late.")])
        started = time.monotonic()
        response = turn(live, session_id, "hello")
        elapsed = time.monotonic() - started
    assert response["handled_by"] == "CAP"
    assert spoken(response) == templates.CYCLE_CAP
    assert elapsed < 4  # answered near the budget, not after the slow model finished


def test_stop_endpoint_cancels_pending_and_keeps_committed_state(server: Server) -> None:
    with server() as (live, scripts):
        session_id = new_session(live)
        scripts.queue([call("prepare_action", kind="CONSENT_SHARING"), say("")])
        readback = turn(live, session_id, "Please share updates with my family")
        assert readback["awaiting_approval"]
        pending = readback["awaiting_approval"]["pending_ref"]

        body = {"turn_id": "turn-stop-1"}
        first = api(live, "POST", f"/api/sessions/{session_id}/stop", json=body)
        again = api(live, "POST", f"/api/sessions/{session_id}/stop", json=body)
        assert first.status_code == again.status_code == 200, first.text
        assert first.json() == again.json()  # the same turn_id: one stop
        assert spoken(first.json()) == templates.COMMANDS["STOP"]
        approval = live.table.get(keys.household_pk("qa-a"), keys.approval_sk(pending))
        assert approval["state"] == "CANCELLED"
        state = api(live, "GET", f"/api/sessions/{session_id}/state").json()
        assert state["pending_approval_id"] is None
        assert len(state["messages"]) >= 2  # what was said before is kept
