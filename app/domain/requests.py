"""Service-request records: loading, views, and the index keys they carry (TDD §6.1; G3-1, G3-2).

A request is pending (`GSI1PK = PENDING`, found by the reconciliation sweep), assigned
(`ASSIGNEE#{sub}`, the technician's queue) or neither. Its REF item carries `CASE` for the
coordinator's queue and must be rewritten whenever the request's state changes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domain import refs
from app.domain.context import OperationContext
from app.domain.errors import DomainError, ErrorCode
from app.domain.state import TERMINAL_REQUEST_STATUSES, RequestStatus
from app.store import keys

PENDING_STATES = frozenset(
    {RequestStatus.SUBMISSION_PENDING, RequestStatus.CHANGE_PENDING, RequestStatus.CANCEL_PENDING}
)
WINDOW_WORDS = {"AM": "10 am and 1 pm", "PM": "2 pm and 5 pm"}
ZONE = ZoneInfo("Asia/Kolkata")


def date_words(day_text: str) -> str:
    day = date.fromisoformat(day_text)
    return f"{day:%A}, {day.day} {day:%B}"


def load(ctx: OperationContext, request_id: str) -> dict[str, Any]:
    item = ctx.table.get(keys.household_pk(ctx.household_id), keys.request_sk(request_id))
    if item is None or item.get("kind") != "SR":
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    return item


def all_requests(ctx: OperationContext) -> list[dict[str, Any]]:
    items = ctx.table.query(keys.household_pk(ctx.household_id), keys.REQUEST_PREFIX)
    return [i for i in items if i.get("kind") == "SR"]


def open_request_for_issue(ctx: OperationContext, issue_id: str) -> dict[str, Any] | None:
    for item in all_requests(ctx):
        if item["issue_id"] == issue_id and item["state"] not in TERMINAL_REQUEST_STATUSES:
            return item
    return None


def appointment(
    ctx: OperationContext, request_id: str, appointment_id: str | None
) -> dict[str, Any] | None:
    if not appointment_id:
        return None
    return ctx.table.get(
        keys.household_pk(ctx.household_id), keys.appointment_sk(request_id, appointment_id)
    )


def appointment_view(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "appointment_id": item["appointment_id"],
        "slot_id": item["slot_id"],
        "date": item["date"],
        "date_words": date_words(item["date"]),
        "window": item["window"],
        "window_words": WINDOW_WORDS[item["window"]],
        "status": item["status"],
    }


def missing_details(item: dict[str, Any]) -> list[str]:
    return [field for field in ("address", "contact") if not (item.get(field) or {}).get("value")]


def view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": item["request_id"],
        "issue_id": item["issue_id"],
        "appliance_id": item["appliance_id"],
        "state": item["state"],
        "mode": item["mode"],
        "fee": item["fee"],
        "warranty": item["warranty"],
        # Only whether they are on file: the agent never holds the full address or contact,
        # which are spoken only in the booking read-back (P3-3; I12).
        "address_on_file": bool((item.get("address") or {}).get("value")),
        "contact_on_file": bool((item.get("contact") or {}).get("value")),
        "slot_id": item.get("slot_id"),
        "provider_ref": item.get("provider_ref"),
        "exception": item.get("exception"),
        "updated_at": item["updated_at"],
        "version": item["version"],
    }


def indexed(item: dict[str, Any]) -> dict[str, Any]:
    """The request with the GSI1 keys its state calls for (G3-2)."""
    item = {k: v for k, v in item.items() if k not in ("GSI1PK", "GSI1SK")}
    if item["state"] in PENDING_STATES:
        item["GSI1PK"], item["GSI1SK"] = "PENDING", item["updated_at"]
    elif item.get("assignee_sub") and item["state"] not in TERMINAL_REQUEST_STATUSES:
        item["GSI1PK"], item["GSI1SK"] = (
            f"ASSIGNEE#{item['assignee_sub']}",
            f"{item['state']}#{item['updated_at']}",
        )
    return item


def case_ref(item: dict[str, Any]) -> dict[str, Any]:
    return refs.ref_item(
        item["request_id"],
        item["household_id"],
        "CASE",
        keys.request_sk(item["request_id"]),
        index="CASE",
        sort=f"{item['state']}#{item['updated_at']}",
    )


def as_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
