"""Appliance history (FR-18): a chronological, attributed timeline built only from events.

Technician reports and customer statements are labelled by role. Corrections are new events, so
nothing earlier ever disappears. The spoken summary is rendered from these entries by a server
template.
"""

from __future__ import annotations

from typing import Any

from app.domain import appliances
from app.domain.clock import local_date
from app.domain.context import OperationContext
from app.domain.events import list_events
from app.domain.requests import as_utc, date_words
from app.security.authz import Action, authorize


def get_history(ctx: OperationContext, appliance_id: str) -> dict[str, Any]:
    authorize(ctx.actor, Action.HISTORY_READ, ctx.household_id)
    appliance = appliances.load(ctx, appliance_id)
    entries = [
        {
            "at": event["at"],
            "date_words": date_words(local_date(as_utc(event["at"])).isoformat()),
            "action": event["action"],
            "actor_role": event["actor_role"],
            "provenance": event.get("provenance"),
        }
        for event in list_events(ctx, appliance_id)
    ]
    return {"appliance": appliance["nickname"], "appliance_id": appliance_id, "entries": entries}
