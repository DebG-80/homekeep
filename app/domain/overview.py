"""Read models composed from several domain modules (G2-6): the household context and an
issue's full detail, including the next approved intake question."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from app.domain import appliances, approvals, booking, guidance, issues, observations, requests
from app.domain.clock import DEFAULT_TIMEZONE
from app.domain.context import OperationContext
from app.domain.household import get_household
from app.domain.state import TERMINAL_REQUEST_STATUSES
from app.security.authz import Action, authorize
from app.store import keys


def _open_requests(ctx: OperationContext) -> list[dict[str, Any]]:
    """Open service requests, each pending one reconciled first (TDD §4.6 reconcile-on-read)."""
    found = []
    for item in requests.all_requests(ctx):
        if item["state"] in requests.PENDING_STATES and booking.reconcile(ctx, item) is not None:
            item = requests.load(ctx, item["request_id"])
        if item["state"] not in TERMINAL_REQUEST_STATUSES:
            found.append(requests.view(item))
    return found


def get_context(ctx: OperationContext) -> dict[str, Any]:
    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)
    household = get_household(ctx)
    pk = keys.household_pk(ctx.household_id)
    open_issues = [
        {**issues.view(i), "next_question": observations.next_intake_question(ctx, i["issue_id"])}
        for i in ctx.table.query(pk, keys.ISSUE_PREFIX)
        if i.get("kind") == "ISSUE" and i["status"] in issues.ACTIVE_ISSUE_STATUSES
    ]
    zone = household.get("timezone") or DEFAULT_TIMEZONE
    local_now = ctx.clock.now().astimezone(ZoneInfo(zone))
    return {
        "storage_consent": household["storage_consent"],
        "sharing_consent": household["sharing_consent"],
        "appliances": [appliances.view(a) for a in ctx.table.query(pk, keys.APPLIANCE_PREFIX)],
        "open_issues": open_issues,
        "service_requests": _open_requests(ctx),
        "pending_approval": approvals.pending_for_session(ctx),
        "timezone": zone,
        "local_date": local_now.date().isoformat(),
        "local_time": local_now.strftime("%H:%M"),
    }


def issue_detail(ctx: OperationContext, issue_id: str) -> dict[str, Any]:
    detail = issues.get_issue(ctx, issue_id)
    return {
        **detail,
        "steps": guidance.recorded_steps(ctx, issue_id),
        "next_question": observations.next_intake_question(ctx, issue_id),
    }


def record_observation_and_next(
    ctx: OperationContext,
    issue_id: str,
    field: str,
    value: str | None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    saved = observations.record_observation(ctx, issue_id, field, value, expected_version)
    return {**saved, "next_question": observations.next_intake_question(ctx, issue_id)}
