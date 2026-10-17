from __future__ import annotations

import time

from app.domain import approvals
from app.domain.clock import SystemClock
from app.domain.context import OperationContext
from app.mcp_server.names import CUSTOMER_TOOLS, TRUSTED_TOOLS
from app.security.actor import Actor, ActorKind, Grant, HouseholdRole
from app.security.attestation import Attestor
from app.store import keys
from tests.contract.live import LiveServer, call_tool

SESSION, TURN = "session-trusted", "turn-trusted"
SUB = "local-a_owner"


def _call(live: LiveServer, attest: str | None) -> dict:
    headers = {"X-HK-Session-Id": SESSION, "X-HK-Turn-Id": TURN}
    if attest is not None:
        headers["X-HK-Attest"] = attest
    return call_tool(live, "cancel_pending_action", {}, headers=headers)


def test_inv2_trusted_tool_rejects_missing_stale_or_forged_attestation(live: LiveServer) -> None:
    good = live.attestor.sign(SUB, SESSION, TURN, "cancel_pending_action", {})
    stale = live.attestor.sign(
        SUB, SESSION, TURN, "cancel_pending_action", {}, now=time.time() - 60
    )
    other_process = Attestor().sign(
        SUB, SESSION, TURN, "cancel_pending_action", {}
    )  # a key this server never had
    timestamp, mac = good.split(".")
    tampered = f"{timestamp}.{mac[:-1]}{'0' if mac[-1] != '0' else '1'}"
    wrong_turn = live.attestor.sign(SUB, SESSION, "another-turn", "cancel_pending_action", {})

    for label, attest in [
        ("missing", None),
        ("stale", stale),
        ("other key", other_process),
        ("tampered", tampered),
        ("wrong turn", wrong_turn),
        ("garbage", "nope"),
    ]:
        refused = _call(live, attest)
        assert (refused["status"], refused["error"]["code"]) == ("ERROR", "AUTH_DENIED"), label

    accepted = _call(live, good)
    assert accepted["status"] == "OK"
    assert accepted["data"]["outcome"] == "NOTHING_PENDING"  # nothing was prepared in this session


def test_inv2_trusted_tools_absent_from_customer_filter() -> None:
    assert not set(CUSTOMER_TOOLS) & set(TRUSTED_TOOLS)
    assert {"confirm_action", "execute_action", "cancel_pending_action"} <= set(TRUSTED_TOOLS)
    assert "report_warning_sign" in CUSTOMER_TOOLS  # agent-visible; the channel also calls it


def _approval_state(live: LiveServer, approval_id: str) -> str:
    return live.table.get(keys.household_pk("qa-a"), keys.approval_sk(approval_id))["state"]


def _trusted(live: LiveServer, tool: str, arguments: dict, attest: str | None) -> dict:
    headers = {"X-HK-Session-Id": SESSION, "X-HK-Turn-Id": TURN}
    if attest is not None:
        headers["X-HK-Attest"] = attest
    return call_tool(live, tool, arguments, headers=headers)


def test_inv2_confirm_and_execute_refuse_without_attestation_for_that_call(
    live: LiveServer,
) -> None:
    """Only the channel, after its approval guard, may approve or execute (invariant 2): a
    missing attestation, or one made for another tool or other arguments, changes nothing."""
    owner = Actor(
        sub=SUB,
        kind=ActorKind.HOUSEHOLD,
        household_id="qa-a",
        role=HouseholdRole.OWNER,
        grants=frozenset(Grant),
    )
    ctx = OperationContext(owner, live.table, SystemClock(), "corr-inv2", TURN, SESSION)
    pending = approvals.prepare_action(ctx, "CONSENT_SHARING")["pending_ref"]

    confirm_args = {"pending_ref": pending, "channel": "text"}
    execute_args = {"approval_id": pending}
    sign = live.attestor.sign
    attempts = {
        "confirm_action": (
            confirm_args,
            [
                ("missing", None),
                ("garbage", "nope"),
                ("other tool", sign(SUB, SESSION, TURN, "cancel_pending_action", confirm_args)),
                (
                    "other arguments",
                    sign(SUB, SESSION, TURN, "confirm_action", {"pending_ref": "x"}),
                ),
            ],
        ),
        "execute_action": (
            execute_args,
            [
                ("missing", None),
                ("garbage", "nope"),
                ("other tool", sign(SUB, SESSION, TURN, "confirm_action", execute_args)),
                (
                    "other arguments",
                    sign(SUB, SESSION, TURN, "execute_action", {"approval_id": "x"}),
                ),
            ],
        ),
    }

    for tool, (arguments, forgeries) in attempts.items():
        state_before = _approval_state(live, pending)
        for label, attest in forgeries:
            refused = _trusted(live, tool, arguments, attest)
            assert (refused["status"], refused["error"]["code"]) == ("ERROR", "AUTH_DENIED"), (
                tool,
                label,
            )
            assert _approval_state(live, pending) == state_before, (tool, label)  # nothing moved
        # The same call with the channel's attestation is accepted, so the refusals above
        # were about the attestation and nothing else.
        accepted = _trusted(live, tool, arguments, sign(SUB, SESSION, TURN, tool, arguments))
        assert accepted["status"] == "OK", tool

    assert _approval_state(live, pending) == "EXECUTED"
