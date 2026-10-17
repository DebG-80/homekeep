"""Trusted tools: refused without channel attestation (TDD §5.3; invariant 2).

They are listed to every client, but only HomeKeep's own channel can use them: the attestation is
bound to the subject, session, turn, tool and arguments (G3-8). They are never in the agent's
tool filter. The channel calls them only after its deterministic approval guard accepted the
user's answer.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from app.domain import approvals
from app.mcp_server.call import run_tool
from app.runtime import Runtime


def register(mcp: FastMCP, runtime: Runtime) -> None:
    @mcp.tool()
    async def confirm_action(
        pending_ref: str,
        ctx: Context,
        readback_completed_at: str | None = None,
        speech_started_at: str | None = None,
        channel: str = "text",
    ) -> dict[str, Any]:
        """Trusted: approve a prepared action after the user's explicit answer."""
        args = {
            "pending_ref": pending_ref,
            "readback_completed_at": readback_completed_at,
            "speech_started_at": speech_started_at,
            "channel": channel,
        }
        return await run_tool(
            runtime,
            ctx,
            "confirm_action",
            approvals.confirm_action,
            pending_ref,
            readback_completed_at,
            speech_started_at,
            channel,
            trusted=True,
            attested_args=args,
        )

    @mcp.tool()
    async def execute_action(approval_id: str, ctx: Context) -> dict[str, Any]:
        """Trusted: run an approved action once."""
        return await run_tool(
            runtime,
            ctx,
            "execute_action",
            approvals.execute_action,
            approval_id,
            trusted=True,
            attested_args={"approval_id": approval_id},
        )

    @mcp.tool()
    async def cancel_pending_action(ctx: Context, pending_ref: str | None = None) -> dict[str, Any]:
        """Trusted: used only by HomeKeep's own channel when the user says stop or no."""
        return await run_tool(
            runtime,
            ctx,
            "cancel_pending_action",
            approvals.cancel_pending_action,
            pending_ref,
            trusted=True,
            attested_args={"pending_ref": pending_ref},
        )
