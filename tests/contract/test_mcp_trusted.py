from __future__ import annotations

import time

from app.mcp_server.names import CUSTOMER_TOOLS, TRUSTED_TOOLS
from app.security.attestation import Attestor
from tests.contract.live import LiveServer, call_tool

SESSION, TURN = "session-trusted", "turn-trusted"
SUB = "local-a_owner"


def _call(live: LiveServer, attest: str | None) -> dict:
    headers = {"X-HK-Session-Id": SESSION, "X-HK-Turn-Id": TURN}
    if attest is not None:
        headers["X-HK-Attest"] = attest
    return call_tool(live, "cancel_pending_action", {}, headers=headers)


def test_inv2_trusted_tool_rejects_missing_stale_or_forged_attestation(live: LiveServer) -> None:
    good = live.attestor.sign(SUB, SESSION, TURN)
    stale = live.attestor.sign(SUB, SESSION, TURN, now=time.time() - 60)
    other_process = Attestor().sign(SUB, SESSION, TURN)  # a key this server never had
    timestamp, mac = good.split(".")
    tampered = f"{timestamp}.{mac[:-1]}{'0' if mac[-1] != '0' else '1'}"
    wrong_turn = live.attestor.sign(SUB, SESSION, "another-turn")

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
    assert accepted["data"]["outcome"] == "NOTHING_PENDING"  # approvals arrive in Slice 3 (G2-3)


def test_inv2_trusted_tools_absent_from_customer_filter() -> None:
    assert not set(CUSTOMER_TOOLS) & set(TRUSTED_TOOLS)
    assert {"confirm_action", "execute_action", "cancel_pending_action"} <= set(TRUSTED_TOOLS)
    assert "report_warning_sign" in CUSTOMER_TOOLS  # agent-visible; the channel also calls it
