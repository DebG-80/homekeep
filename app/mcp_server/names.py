"""The single source for tool visibility (TDD §5.4; CLAUDE.md invariant 2).

The agent's `tool_filters["allowed"]` is exactly CUSTOMER_TOOLS. TRUSTED_TOOLS are refused
without channel attestation and are never given to the agent.
"""

from __future__ import annotations

CUSTOMER_TOOLS: tuple[str, ...] = (
    "get_context",
    "register_appliance",
    "resolve_appliance",
    "update_appliance_fact",
    "report_issue",
    "get_issue",
    "record_observation",
    "report_warning_sign",
    "get_guidance",
    "record_step_result",
)
TRUSTED_TOOLS: tuple[str, ...] = ("confirm_action", "execute_action", "cancel_pending_action")
