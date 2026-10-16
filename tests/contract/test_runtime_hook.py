from __future__ import annotations

import ast
from pathlib import Path

from app.mcp_server.names import CUSTOMER_TOOLS, TRUSTED_TOOLS
from app.orchestrator.fake_model import TurnScripts, call, say
from app.security.local_issuer import LocalIssuer
from app.store import keys
from app.store.table import Table
from scripts import seed
from tests.contract.live import new_session, serve, turn

ORCHESTRATOR = Path(__file__).resolve().parents[2] / "app" / "orchestrator"


def test_dd1_agent_calls_tools_only_through_loopback_mcp(table: Table, issuer: LocalIssuer) -> None:
    seed.seed_local(table)
    scripts = TurnScripts()
    scripts.queue(
        [
            call("resolve_appliance", reference="bedroom AC"),
            call(
                "report_issue",
                appliance_id="qa-a-ac-bedroom",
                symptom_text="The bedroom AC is not cooling",
                symptom_category="NOT_COOLING",
            ),
            say("I've noted that the bedroom AC is not cooling."),
        ]
    )
    with serve(table, issuer, scripts) as live:
        response = turn(live, new_session(live), "My bedroom AC is not cooling")

    # The domain write carries the turn's correlation ID: it arrived through the MCP server,
    # which only learns it from the X-Correlation-Id header of the loopback HTTP call.
    events = table.query(keys.household_pk("qa-a"), keys.EVENT_PREFIX)
    reported = [e for e in events if e["action"] == "ISSUE_REPORTED"]
    assert [e["correlation_id"] for e in reported] == [response["correlation_id"]]
    assert (
        reported[0]["actor_sub"] == "local-a_owner"
    )  # the user's own token, not a service identity

    # The model was offered exactly the customer tools: never a trusted one (invariant 2).
    offered = set(scripts.models[0].tools_offered)
    assert offered == set(CUSTOMER_TOOLS)
    assert not offered & set(TRUSTED_TOOLS)

    # And the orchestrator has no in-process shortcut: it never imports the domain or the store.
    for source in ORCHESTRATOR.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m.startswith(("app.domain", "app.store")) for m in imported), source.name
