"""Trusted tools: refused without channel attestation (TDD §5.3; invariant 2).

They are listed to every client but only HomeKeep's own channel can use them, and they are never
in the agent's tool filter. `confirm_action` and `execute_action` arrive in Slice 3 with the
approval ledger; until then `cancel_pending_action` finds nothing to cancel (G2-3).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from app.domain.context import OperationContext
from app.mcp_server.call import run_tool
from app.runtime import Runtime
from app.security.authz import Action, authorize


def _cancel_pending(ctx: OperationContext, pending_ref: str | None) -> dict[str, Any]:
    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)
    return {"outcome": "NOTHING_PENDING", "pending_ref": pending_ref}


def register(mcp: FastMCP, runtime: Runtime) -> None:
    @mcp.tool()
    async def cancel_pending_action(ctx: Context, pending_ref: str | None = None) -> dict[str, Any]:
        """Trusted: used only by HomeKeep's own channel when the user says stop or no."""
        return await run_tool(
            runtime, ctx, "cancel_pending_action", _cancel_pending, pending_ref, trusted=True
        )
