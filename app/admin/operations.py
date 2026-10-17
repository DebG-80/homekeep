"""Operator actions behind the hk-admin CLI (TDD §4.10; plan P4-2): catalog publication overlay
and provider fault injection. Each is validated and audited."""

from __future__ import annotations

from app.admin.audit import audit
from app.catalog.loader import load_catalog
from app.catalog.overlay import OVERLAY_PK
from app.domain.clock import Clock, iso_utc
from app.domain.errors import DomainError, ErrorCode
from app.provider.faults import CANCEL_FAULTS, QUOTE_FAULTS, REPLACE_FAULTS, SUBMIT_FAULTS
from app.store import keys
from app.store.table import Table

FAULTS = SUBMIT_FAULTS | QUOTE_FAULTS | REPLACE_FAULTS | CANCEL_FAULTS


def _catalog_item(item_id: str) -> None:
    if item_id not in {item.item_id for item in load_catalog().items}:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_CATALOG_ITEM")


def withdraw_item(table: Table, clock: Clock, item_id: str, reason: str, actor_label: str) -> None:
    """Withdraw every version of a catalog item without a redeploy (FR-23-AC2; AT-24)."""
    _catalog_item(item_id)
    if not reason.strip():
        raise DomainError(ErrorCode.INVALID_INPUT, "REASON_REQUIRED")
    table.put(
        {
            "PK": OVERLAY_PK,
            "SK": f"STATUS#{item_id}",
            "status": "WITHDRAWN",
            "reason": reason.strip()[:500],
            "at": iso_utc(clock.now()),
            "by": actor_label,
        }
    )
    audit(table, clock, "CATALOG_WITHDRAWN", actor_label, item_id=item_id)


def restore_item(table: Table, clock: Clock, item_id: str, actor_label: str) -> None:
    """Remove the overlay: the item's file status applies again."""
    _catalog_item(item_id)
    table.delete(OVERLAY_PK, f"STATUS#{item_id}")
    audit(table, clock, "CATALOG_RESTORED", actor_label, item_id=item_id)


def set_fault(
    table: Table, clock: Clock, household_id: str, fault: str, remaining: int, actor_label: str
) -> None:
    """Inject a demo-provider fault for one household (honoured only when FAULTS_ENABLED)."""
    if fault not in FAULTS:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_FAULT")
    if not 1 <= remaining <= 20:
        raise DomainError(ErrorCode.INVALID_INPUT, "INVALID_COUNT")
    if table.get(keys.household_pk(household_id), keys.META) is None:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    table.put(
        {
            "PK": keys.PROVIDER_PK,
            "SK": keys.fault_sk(household_id),
            "fault": fault,
            "remaining": remaining,
        }
    )
    audit(table, clock, "FAULT_SET", actor_label, target_household=household_id, fault=fault)


def clear_fault(table: Table, clock: Clock, household_id: str, actor_label: str) -> None:
    table.delete(keys.PROVIDER_PK, keys.fault_sk(household_id))
    audit(table, clock, "FAULT_CLEARED", actor_label, target_household=household_id)
