"""The turn pipeline (TDD §4.2): T1 authenticate → T3 claim the turn → T4 commands → T5 hazards →
daily cap → T7 agent → T8 output guard → T9 persist and respond. T6 (approvals) is Slice 3.

The deterministic guards run before the daily cap: safety advice and "stop" never wait for
tomorrow. Speech comes from server templates, verbatim hazard text or verbatim catalog steps
whenever those apply; the model's own words are spoken only after the output guard passes them
(CLAUDE.md invariant 6).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import anyio

from app.catalog.hazards import classify
from app.channel import sessions, templates, usage
from app.channel.approval_guard import Pending, accept_playback_end, decide
from app.channel.guards import chunk_speech, command_for, hazard_in, output_guard
from app.channel.trusted_client import call_trusted
from app.domain import approvals
from app.domain.clock import DEFAULT_TIMEZONE
from app.domain.context import OperationContext
from app.domain.errors import DomainError, ErrorCode
from app.domain.requests import WINDOW_WORDS, date_words
from app.logging import log_error, log_event
from app.orchestrator.agent import TurnOutcome, build_model, run_turn
from app.orchestrator.prompt import build_system_prompt
from app.runtime import Runtime
from app.security.actor import Actor
from app.security.membership import resolve_actor
from app.security.tokens import SCOPE_API, VerifiedToken

DEMO_BADGE = "DEMO — simulated service desk"
_ISSUE_TOOLS = (
    "get_issue",
    "record_observation",
    "get_guidance",
    "record_step_result",
    "report_warning_sign",
)
_AGENT_SLACK_SECONDS = 1.0
# Some models (Amazon Nova) write their reasoning into the reply inside <thinking> tags. It is
# never spoken, guarded or stored; an unclosed block runs to the end of the text.
# The session's current appliance and problem, told to the model each turn (it otherwise sees only
# the spoken text). Only server-made IDs and known categories: never the user's words.
_SERVER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_CATEGORIES = {"AC": "AC", "FRIDGE": "fridge", "TV": "TV"}
_SLOT_ID = re.compile(r"(\d{4}-\d{2}-\d{2})#(AM|PM)")
_ORDINALS = ("first", "second", "third")
_THINKING = re.compile(r"<thinking>.*?(?:</thinking>|$)", re.IGNORECASE | re.DOTALL)
_NO_PENDING = {
    "pending_approval_id": None,
    "approval_expires_at": None,
    "approval_prepared_at": None,
    "readback_completed_at": None,
}


@dataclass(frozen=True)
class VoiceContext:
    """What the client reports with a turn (TDD §4.3 rules 2 and 3; FR-21)."""

    channel: str = "text"
    client_state: str | None = None
    speech_started_at: datetime | None = None
    playback_ended_at: datetime | None = None


def _parse(moment: str | None) -> datetime | None:
    return datetime.fromisoformat(moment.replace("Z", "+00:00")) if moment else None


@dataclass(frozen=True)
class Caller:
    token: str
    verified: VerifiedToken
    actor: Actor

    @property
    def household_id(self) -> str:
        if not self.actor.household_id:
            raise DomainError(ErrorCode.AUTH_DENIED, "NO_HOUSEHOLD_SCOPE")
        return self.actor.household_id


def authenticate(runtime: Runtime, token: str | None) -> Caller:
    """T1: verify the access token, then read membership and grants afresh."""
    if not token:
        raise DomainError(ErrorCode.AUTH_DENIED, "NO_TOKEN")
    verified = runtime.verifier.verify(token, SCOPE_API)
    actor = resolve_actor(runtime.table, verified)
    caller = Caller(token, verified, actor)
    _ = caller.household_id  # the conversation API is for household members only
    return caller


def local_prompt_time(now: datetime, timezone: str = DEFAULT_TIMEZONE) -> tuple[str, str]:
    """The household's local date and time, converted once so they always agree (invariant 10)."""
    local = now.astimezone(ZoneInfo(timezone))
    return local.date().isoformat(), local.strftime("%H:%M")


def _history(session: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"role": m["role"], "content": [{"text": m["text"]}]} for m in session["messages"]]


def _last_assistant(session: dict[str, Any]) -> str | None:
    return next(
        (m["text"] for m in reversed(session["messages"]) if m["role"] == "assistant"), None
    )


def _ok(call: Any) -> dict[str, Any] | None:
    envelope = call.envelope or {}
    return envelope.get("data") if envelope.get("status") == "OK" else None


def speak_agent_outcome(outcome: TurnOutcome) -> tuple[str, dict[str, Any] | None, bool, str]:
    """(speech, citation, guarded, handled_by) for a turn the agent handled.

    Precedence: a reported warning sign (its approved text, even if the call failed or the turn
    then hit a cap) → a server template for a read-back, status, resolution or history → an
    approved step → a guidance refusal → the cap → the guarded model text.
    """
    for call in reversed(outcome.tool_calls):
        if call.name == "report_warning_sign":
            data = _ok(call)
            speech = data["speech"] if data else classify(str(call.input.get("sign", ""))).speech
            return speech, None, False, "AGENT"
    for call in reversed(outcome.tool_calls):
        data = _ok(call)
        if call.name == "prepare_action" and data:  # the server's read-back, verbatim (FR-12)
            return " ".join(templates.render_readback(data["readback"])), None, False, "AGENT"
        if call.name == "list_slots" and data:  # the offer in words, in the remembered order
            return templates.render_slots(data["slots"]), None, False, "AGENT"
        if call.name == "get_service_status" and data:  # the authoritative state (FR-15)
            return " ".join(templates.render_status(data)), None, False, "AGENT"
        if call.name == "confirm_resolution" and data:  # the customer's own answer (FR-17)
            return " ".join(templates.render_resolution(data)), None, False, "AGENT"
        if call.name == "get_history" and data:  # an attributed timeline (FR-18)
            return " ".join(templates.render_history(data)), None, False, "AGENT"
    for call in reversed(outcome.tool_calls):
        if call.name != "get_guidance":
            continue
        data = _ok(call)
        if data:
            step, evidence = data["step"], data["evidence"]
            citation = {
                k: evidence[k] for k in ("document_id", "locator", "catalog_item", "version")
            }
            speech = step["speech"]
            if "?" not in speech:  # a step that already asks needs no follow-up
                speech = f"{speech} {templates.GUIDANCE_FOLLOW_UP}"
            return speech, citation, False, "AGENT"
        error = (call.envelope or {}).get("error") or {}
        if error.get("code") == "NO_APPROVED_GUIDANCE":
            # No approved check: the server states the limit and offers service (FR-08,
            # invariant 7), plus one reviewed observation prompt where the catalog has one.
            details = error.get("details") or {}
            lead = details.get("scope_limit") or error["message"]
            prompts = details.get("generic_prompts") or []
            return " ".join([lead, *prompts[:1]]), None, False, "AGENT"
        break
    if outcome.stop != "END":
        return templates.CYCLE_CAP, None, False, "CAP"
    text = re.sub(r"\s+", " ", _THINKING.sub(" ", outcome.text)).strip()
    if not text:
        return templates.TURN_ERROR, None, False, "AGENT"
    if output_guard(text).blocked:
        return templates.OUTPUT_GUARD_FALLBACK, None, True, "AGENT"
    return text, None, False, "AGENT"


def _session_updates(outcome: TurnOutcome | None) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for call in outcome.tool_calls if outcome else []:
        data = _ok(call)
        if call.name == "report_issue" and data and data.get("issue"):
            updates["active_issue_id"] = data["issue"]["issue_id"]
        elif call.name in _ISSUE_TOOLS and call.input.get("issue_id") and data is not None:
            updates["active_issue_id"] = call.input["issue_id"]
        if call.name == "draft_service_request" and data and data.get("request"):
            updates["active_request_id"] = data["request"]["request_id"]
        elif call.name in _REQUEST_TOOLS and call.input.get("request_id") and data is not None:
            updates["active_request_id"] = call.input["request_id"]
        if call.name == "list_slots" and data:
            spoken = data["slots"][: templates.MAX_SLOTS_SPOKEN]
            updates["offered_slots"] = [slot["slot_id"] for slot in spoken]
        appliance = _appliance_in(call, data)
        if appliance:
            updates["active_appliance"] = appliance
        if call.name == "get_guidance" and data:
            updates["last_step_id"] = data["step"]["step_id"]
        if call.name == "prepare_action" and data:  # a new read-back awaits the user's answer
            updates.update(
                pending_approval_id=data["pending_ref"],
                approval_expires_at=data["expires_at"],
                approval_prepared_at=data["prepared_at"],
                readback_completed_at=None,
            )
    return updates


def _appliance_in(call: Any, data: dict[str, Any] | None) -> dict[str, Any] | None:
    """The appliance a call settled on: one registered, a single match, or the saved appliance a
    duplicate registration points to."""
    if call.name == "register_appliance" and data:
        return {"appliance_id": data["appliance_id"], "category": data["category"]}
    if call.name == "resolve_appliance" and data and len(data.get("matches", [])) == 1:
        match = data["matches"][0]
        return {"appliance_id": match["appliance_id"], "category": match["category"]}
    if call.name == "register_appliance":
        details = ((call.envelope or {}).get("error") or {}).get("details") or {}
        if details.get("existing_appliance_id"):
            category = str(call.input.get("category", ""))
            return {"appliance_id": details["existing_appliance_id"], "category": category}
    if call.name == "report_issue" and data and call.input.get("appliance_id"):
        return {"appliance_id": call.input["appliance_id"], "category": ""}
    return None


_REQUEST_TOOLS = ("record_service_details", "list_slots", "prepare_action", "get_service_status")


def session_context(session: dict[str, Any]) -> str:
    """Lines added to the system prompt about what this conversation is already about."""
    lines = []
    appliance = session.get("active_appliance") or {}
    appliance_id = str(appliance.get("appliance_id") or "")
    if _SERVER_ID.fullmatch(appliance_id):
        category = _CATEGORIES.get(str(appliance.get("category", "")).upper())
        what = f"the {category}" if category else "an appliance"
        lines.append(
            f"This conversation is about {what} with appliance_id {appliance_id}. Use that "
            "appliance_id for report_issue and its other tools; don't ask for its name again "
            "unless the user talks about a different appliance."
        )
    issue_id = str(session.get("active_issue_id") or "")
    if _SERVER_ID.fullmatch(issue_id):
        lines.append(f"The open problem being discussed has issue_id {issue_id}.")
    request_id = str(session.get("active_request_id") or "")
    if _SERVER_ID.fullmatch(request_id):
        lines.append(f"The demo visit request has request_id {request_id}.")
    offered = []
    for ordinal, slot_id in zip(_ORDINALS, session.get("offered_slots") or [], strict=False):
        match = _SLOT_ID.fullmatch(str(slot_id))
        if not match:
            continue
        try:
            day = date_words(match.group(1))
        except ValueError:  # date-shaped but not a date
            continue
        words = f"{day}, between {WINDOW_WORDS[match.group(2)]}"
        offered.append(f"{ordinal}: slot_id {slot_id} ({words})")
    if offered:
        lines.append(
            "Visit times read out to the user, in order: "
            + "; ".join(offered)
            + ". When the user picks one (by number, day or time), call prepare_action with "
            "kind SUBMIT, this request_id and that slot_id. Never say yourself that a visit is "
            "booked."
        )
    return "\n".join(lines)


def _response(
    session_id: str,
    turn_id: str,
    correlation_id: str,
    speech: str,
    handled_by: str,
    *,
    speech_rate: str = "normal",
    guarded: bool = False,
    citation: dict[str, Any] | None = None,
    awaiting_approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "correlation_id": correlation_id,
        "speech": chunk_speech(speech),
        "speech_rate": speech_rate,
        "handled_by": handled_by,
        "guarded": guarded,
        "display": {"citation": citation, "demo_badge": DEMO_BADGE},
        # Present when this turn spoke a read-back: the client reports when its playback ended.
        "awaiting_approval": awaiting_approval,
    }


async def handle_turn(
    runtime: Runtime,
    caller: Caller,
    session_id: str,
    turn_id: str,
    text: str,
    voice: VoiceContext | None = None,
) -> dict[str, Any]:
    table, settings = runtime.table, runtime.settings
    household_id = caller.household_id
    started = time.monotonic()
    now = runtime.clock.now()
    session = await anyio.to_thread.run_sync(
        sessions.load_session, table, household_id, session_id, caller.verified.sub
    )

    # T3: claim the turn first, so a retry never runs it twice (FR-22, invariant 5).
    stale_after = timedelta(seconds=2 * settings.turn_budget_seconds + 10)
    existing = await anyio.to_thread.run_sync(
        lambda: sessions.claim_turn(table, session, turn_id, now, stale_after)
    )
    correlation_id = f"corr-{uuid.uuid4().hex}"
    if existing is not None:
        if existing.get("status", "DONE") == "DONE" and existing.get("response") is not None:
            return existing["response"]
        return _response(
            session_id, turn_id, correlation_id, templates.STILL_WORKING, "IN_PROGRESS"
        )

    try:
        response, updates = await _run_turn(
            runtime, caller, session, turn_id, text, correlation_id, now, voice or VoiceContext()
        )
    except Exception:
        await anyio.to_thread.run_sync(sessions.release_turn, table, session, turn_id)
        raise
    committed = await anyio.to_thread.run_sync(
        sessions.commit_turn, table, session, turn_id, response, updates, now
    )
    log_event(
        "TURN",
        correlation_id=correlation_id,
        sub=caller.verified.sub,
        action=response["handled_by"],
        result="GUARDED" if response["guarded"] else "OK",
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return committed


async def _run_turn(
    runtime: Runtime,
    caller: Caller,
    session: dict[str, Any],
    turn_id: str,
    text: str,
    correlation_id: str,
    now: datetime,
    voice: VoiceContext,
) -> tuple[dict[str, Any], dict[str, Any]]:
    table, settings = runtime.table, runtime.settings
    session_id = session["session_id"]
    updates: dict[str, Any] = {}
    speech_rate = session.get("speech_rate", "normal")
    citation: dict[str, Any] | None = None
    guarded = False

    # A hazard whose recording failed earlier is recorded before anything else.
    pending = session.get("pending_hazard")
    if pending:
        recorded = await _record_hazard(
            runtime, caller, session_id, turn_id, correlation_id, pending
        )
        updates["pending_hazard"] = None if recorded else pending

    # The client tells us when the read-back finished playing (TDD §4.3 rule 2).
    pending_ref = session.get("pending_approval_id")
    readback_at = session.get("readback_completed_at")
    playback_end = accept_playback_end(  # only a report that can be true (I8)
        _parse(session.get("approval_prepared_at")) if pending_ref else None,
        voice.playback_ended_at,
        voice.client_state,
        runtime.clock.now(),
    )
    if pending_ref and not readback_at and playback_end:
        readback_at = updates["readback_completed_at"] = playback_end.isoformat()

    command = command_for(text)
    hazard = None if command else hazard_in(text)
    if command:  # T4
        handled_by = "COMMAND"
        if command == "REPEAT":
            speech = _last_assistant(session) or templates.NOTHING_TO_REPEAT
        else:
            speech = templates.COMMANDS[command]
        if command == "SLOWER":
            speech_rate = updates["speech_rate"] = "slow"
        if command == "STOP":
            await _trusted(
                runtime, caller, session_id, turn_id, correlation_id, "cancel_pending_action", {}
            )
            updates.update(_NO_PENDING)
    elif hazard:  # T5: the approved text is spoken whatever happens to the write
        handled_by, speech = "HAZARD", hazard.speech
        report = {"sign": text, "reason": hazard.reason, "issue_id": session.get("active_issue_id")}
        if not await _record_hazard(runtime, caller, session_id, turn_id, correlation_id, report):
            updates["pending_hazard"] = report  # surfaced in the log and retried next turn
    elif pending_ref and (
        approval := await _approval_turn(
            runtime, caller, session, turn_id, correlation_id, text, voice, readback_at
        )
    ):  # T6: only the deterministic guard decides (invariant 2)
        handled_by, speech = "APPROVAL", approval
        updates.update(_NO_PENDING)
    elif not await anyio.to_thread.run_sync(
        usage.take_turn, table, caller.household_id, now, settings.daily_turn_cap
    ):
        speech, handled_by = templates.DAILY_CAP, "CAP"  # only model turns count
    else:  # T7, then T8
        outcome = await _agent_turn(runtime, caller, session, turn_id, text, correlation_id)
        if outcome is None:
            speech, handled_by = templates.TURN_ERROR, "AGENT"
        else:
            speech, citation, guarded, handled_by = speak_agent_outcome(outcome)
            if guarded:
                log_event(
                    "OUTPUT_GUARD",
                    correlation_id=correlation_id,
                    sub=caller.verified.sub,
                    result="BLOCKED",
                )
            updates.update(_session_updates(outcome))

    updates["new_messages"] = [
        {"role": "user", "text": text},
        {"role": "assistant", "text": speech},
    ]
    response = _response(
        session_id,
        turn_id,
        correlation_id,
        speech,
        handled_by,
        speech_rate=speech_rate,
        guarded=guarded,
        citation=citation,
        awaiting_approval=(
            {
                "pending_ref": updates["pending_approval_id"],
                "expires_at": updates["approval_expires_at"],
            }
            if updates.get("pending_approval_id")
            else None
        ),
    )
    return response, updates


async def _approval_turn(
    runtime: Runtime,
    caller: Caller,
    session: dict[str, Any],
    turn_id: str,
    correlation_id: str,
    text: str,
    voice: VoiceContext,
    readback_at: str | None,
) -> str | None:
    """T6. The reply to an answer about the pending action, or None when the utterance is not
    an answer (it then goes to the agent and the action stays pending)."""
    pending_ref = session["pending_approval_id"]
    pending = Pending(
        pending_ref=pending_ref,
        expires_at=_parse(session.get("approval_expires_at")) or runtime.clock.now(),
        readback_completed_at=_parse(readback_at),
    )
    decision = decide(
        text,
        pending=pending,
        channel=voice.channel,
        client_state=voice.client_state,
        speech_started_at=voice.speech_started_at,
        now=runtime.clock.now(),
        last_spoken=_last_assistant(session),
    )
    session_id = session["session_id"]
    if decision.kind == "DECLINE":
        await _trusted(
            runtime,
            caller,
            session_id,
            turn_id,
            correlation_id,
            "cancel_pending_action",
            {"pending_ref": pending_ref},
        )
        return templates.APPROVAL_DECLINED
    if decision.kind == "NONE":
        return templates.APPROVAL_EXPIRED if decision.reason == "EXPIRED" else None
    confirmed = await _trusted(
        runtime,
        caller,
        session_id,
        turn_id,
        correlation_id,
        "confirm_action",
        {
            "pending_ref": pending_ref,
            "readback_completed_at": readback_at,
            "speech_started_at": voice.speech_started_at.isoformat()
            if voice.speech_started_at
            else None,
            "channel": voice.channel,
        },
    )
    if confirmed.get("status") != "OK":
        error = confirmed.get("error") or {}
        if error.get("code") == "APPROVAL_EXPIRED":
            return templates.APPROVAL_EXPIRED
        if error.get("reason") == "FEE_CHANGED":
            fee = (error.get("details") or {}).get("fee_paise")
            return " ".join(templates.render_outcome({"outcome": "FEE_CHANGED", "fee_paise": fee}))
        return templates.APPROVAL_REFUSED
    executed = await _trusted(
        runtime,
        caller,
        session_id,
        turn_id,
        correlation_id,
        "execute_action",
        {"approval_id": confirmed["data"]["approval_id"]},
    )
    if executed.get("status") != "OK":
        # Never assume: read what was actually recorded (reconciling first). Nothing sent is
        # said as nothing sent; an unknown provider answer is pending, never "booked" (I2).
        approval_id = confirmed["data"]["approval_id"]
        try:
            result = await anyio.to_thread.run_sync(
                _outcome_after_failure,
                runtime,
                caller,
                session_id,
                turn_id,
                correlation_id,
                approval_id,
            )
        except Exception as exc:
            log_error("OUTCOME_UNKNOWN", exc, correlation_id=correlation_id)
            result = {"outcome": "PENDING"}
        return " ".join(templates.render_outcome(result))
    return " ".join(templates.render_outcome(executed["data"]))


def _outcome_after_failure(
    runtime: Runtime,
    caller: Caller,
    session_id: str,
    turn_id: str,
    correlation_id: str,
    approval_id: str,
) -> dict[str, Any]:
    ctx = OperationContext(
        actor=caller.actor,
        table=runtime.table,
        clock=runtime.clock,
        correlation_id=correlation_id,
        turn_id=turn_id,
        session_id=session_id,
        faults_enabled=runtime.settings.faults_enabled,
    )
    return approvals.outcome_after_failure(ctx, approval_id)


async def _agent_turn(
    runtime: Runtime,
    caller: Caller,
    session: dict[str, Any],
    turn_id: str,
    text: str,
    correlation_id: str,
) -> TurnOutcome | None:
    settings = runtime.settings
    prompt = build_system_prompt(*local_prompt_time(runtime.clock.now()))
    context = session_context(session)
    if context:
        prompt = f"{prompt}\n\nWhere this conversation stands:\n{context}"
    factory = runtime.model_factory or (lambda: build_model(settings))

    def work() -> TurnOutcome:
        return run_turn(
            settings=settings,
            model_factory=factory,
            token=caller.token,
            turn_id=turn_id,
            session_id=session["session_id"],
            correlation_id=correlation_id,
            system_prompt=prompt,
            history=_history(session),
            user_text=text,
        )

    # A real wall clock (TDD §4.2 T7): the reply goes out at the budget even if a model or tool
    # call is still running; that thread finishes on its own and its hook stops any further step.
    with anyio.move_on_after(settings.turn_budget_seconds + _AGENT_SLACK_SECONDS):
        try:
            return await anyio.to_thread.run_sync(work, abandon_on_cancel=True)
        except Exception as exc:
            log_error("AGENT_FAILED", exc, correlation_id=correlation_id)
            return None
    log_event("TURN_BUDGET", correlation_id=correlation_id, result="EXCEEDED")
    return TurnOutcome(text="", tool_calls=[], stop="BUDGET")


async def _record_hazard(
    runtime: Runtime,
    caller: Caller,
    session_id: str,
    turn_id: str,
    correlation_id: str,
    report: dict[str, Any],
) -> bool:
    """Record a hazard through the trusted client, with one immediate retry."""
    arguments = {"sign": report["sign"], "issue_id": report.get("issue_id")}
    for _ in range(2):
        envelope = await _trusted(
            runtime, caller, session_id, turn_id, correlation_id, "report_warning_sign", arguments
        )
        if envelope.get("status") == "OK":
            return True
    log_event("HAZARD_NOT_RECORDED", correlation_id=correlation_id, error_code=report["reason"])
    return False


async def _trusted(
    runtime: Runtime,
    caller: Caller,
    session_id: str,
    turn_id: str,
    correlation_id: str,
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        return await call_trusted(
            url=runtime.settings.mcp_loopback_url,
            attestor=runtime.attestor,
            token=caller.token,
            sub=caller.verified.sub,
            session_id=session_id,
            turn_id=turn_id,
            correlation_id=correlation_id,
            tool=tool,
            arguments={k: v for k, v in arguments.items() if v is not None},
        )
    except Exception as exc:  # the deterministic reply still goes out; the log has the type
        log_error("TRUSTED_CALL_FAILED", exc, correlation_id=correlation_id, action=tool)
        return {}
