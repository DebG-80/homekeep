"""The demo provider simulator (TDD §4.6; plan G3-4).

Slots are generated for any date (10:00 to 13:00 and 14:00 to 17:00, Asia/Kolkata), so the
demo never runs out before 20 November. Taking a slot is a conditional counter, so two people
racing for the last place get exactly one success (AT-15). Every request is stored by operation
key, so a repeat returns the original result (AT-14). Faults come from `faults.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.clock import Clock, iso_utc
from app.domain.errors import ConflictError
from app.provider.faults import (
    CANCEL_FAULTS,
    QUOTE_FAULTS,
    REPLACE_FAULTS,
    SUBMIT_FAULTS,
    take_fault,
)
from app.store import keys
from app.store.table import Table

PROVIDER_NAME = "HomeKeep Demo Service Desk"
ZONE = ZoneInfo("Asia/Kolkata")
WINDOWS: dict[str, tuple[time, time, int]] = {
    "AM": (time(10, 0), time(13, 0), 2),
    "PM": (time(14, 0), time(17, 0), 1),  # one place per afternoon: a contested last slot
}
FEE_PAISE = 49_900  # illustrative ESTIMATE (FR-27)
CHANGED_FEE_PAISE = 59_900


class ProviderTimeout(Exception):
    """The provider did the work but its reply was lost (TIMEOUT_AFTER_SUCCESS, CANCEL_TIMEOUT)."""


class ProviderUnavailable(Exception):
    """The provider could not be reached; nothing was recorded."""


class PlaceUnavailable(Exception):
    """A slot change could not be made: the slot is full, or there was no place to release."""


@dataclass(frozen=True)
class Slot:
    slot_id: str
    date: str
    window: str
    start_utc: str
    end_utc: str
    capacity: int
    available: bool
    fee_paise: int
    fee_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_slot(slot_id: str) -> tuple[date, str]:
    day_text, _, window = slot_id.partition("#")
    if window not in WINDOWS:
        raise ValueError(f"unknown slot {slot_id}")
    return date.fromisoformat(day_text), window


class DemoProvider:
    def __init__(self, table: Table, clock: Clock, faults_enabled: bool) -> None:
        self.table = table
        self.clock = clock
        self.faults_enabled = faults_enabled

    # --- inventory -------------------------------------------------------------------------

    def _slot(self, day: date, window: str) -> Slot:
        start, end, capacity = WINDOWS[window]
        slot_id = f"{day.isoformat()}#{window}"
        taken = (self.table.get(keys.PROVIDER_PK, keys.slot_sk(slot_id)) or {}).get("taken", 0)
        start_at = datetime.combine(day, start, tzinfo=ZONE)
        return Slot(
            slot_id=slot_id,
            date=day.isoformat(),
            window=window,
            start_utc=iso_utc(start_at),
            end_utc=iso_utc(datetime.combine(day, end, tzinfo=ZONE)),
            capacity=capacity,
            available=taken < capacity and start_at > self.clock.now(),
            fee_paise=FEE_PAISE,
            fee_status="ESTIMATE",
        )

    def slot(self, slot_id: str) -> Slot:
        day, window = parse_slot(slot_id)
        return self._slot(day, window)

    def list_slots(self, from_date: date, days: int) -> list[Slot]:
        now = self.clock.now()
        slots = []
        for offset in range(days):
            day = from_date + timedelta(days=offset)
            for window in WINDOWS:
                slot = self._slot(day, window)
                if datetime.fromisoformat(slot.start_utc.replace("Z", "+00:00")) > now:
                    slots.append(slot)
        return slots

    def quote(self, household_id: str, slot_id: str) -> int:
        """The fee for this slot now. FEE_CHANGE makes it differ from what was read back."""
        self.slot(slot_id)
        if take_fault(self.table, household_id, QUOTE_FAULTS, self.faults_enabled):
            return CHANGED_FEE_PAISE
        return FEE_PAISE

    def _take_op(self, slot_id: str) -> dict[str, Any]:
        """One more place in the slot, unless it is full (conditional counter)."""
        day, window = parse_slot(slot_id)
        expires = datetime.combine(day, time(23, 59), tzinfo=ZONE) + timedelta(days=30)
        return self.table.update_op(
            keys.PROVIDER_PK,
            keys.slot_sk(slot_id),
            "ADD #count :one SET #ttl = :ttl",
            {":one": 1, ":limit": WINDOWS[window][2], ":ttl": int(expires.timestamp())},
            {"#count": "taken", "#ttl": "ttl"},
            condition="attribute_not_exists(#count) OR #count < :limit",
        )

    def release_op(self, slot_id: str) -> dict[str, Any]:
        """Give one place back, unless none is taken (for a transaction)."""
        return self.table.update_op(
            keys.PROVIDER_PK,
            keys.slot_sk(slot_id),
            "ADD #count :minus",
            {":minus": -1, ":zero": 0},
            {"#count": "taken"},
            condition="#count > :zero",
        )

    def release_place(self, slot_id: str) -> bool:
        """Give one place back (a reset or purge of a household that held it). False if the
        slot had no place taken."""
        try:
            self.table.transact([self.release_op(slot_id)])
        except ConflictError:
            return False
        return True

    # --- requests ---------------------------------------------------------------------------

    def _existing(self, operation_key: str) -> dict[str, Any] | None:
        return self.table.get(keys.PROVIDER_PK, keys.provider_request_sk(operation_key))

    def status(self, operation_key: str) -> dict[str, Any] | None:
        """What the provider recorded for this operation, or None if it never arrived."""
        return self._existing(operation_key)

    def _item(self, operation_key: str, kind: str, **fields: Any) -> dict[str, Any]:
        return {
            "PK": keys.PROVIDER_PK,
            "SK": keys.provider_request_sk(operation_key),
            "kind": kind,
            "operation_key": operation_key,
            "at": iso_utc(self.clock.now()),
            **fields,
        }

    def _record(
        self,
        operation_key: str,
        kind: str,
        places: tuple[dict[str, Any], ...] = (),
        **fields: Any,
    ) -> dict[str, Any]:
        """Write the record and its slot changes in one transaction, so a place is never taken
        or released without its record (I4). A repeat of the same operation gets the original
        record. `PlaceUnavailable` means a slot change's condition failed (the slot is full)."""
        record = self._item(operation_key, kind, **fields)
        try:
            self.table.transact([*places, self.table.put_new_op(record)])
        except ConflictError as exc:
            existing = self._existing(operation_key)
            if existing is not None:
                return existing  # a repeat of the same operation: the original result
            if any(i < len(places) for i in exc.failed_indexes):
                raise PlaceUnavailable(operation_key) from exc
            raise
        return record

    def submit(self, household_id: str, operation_key: str, slot_id: str) -> dict[str, Any]:
        existing = self.status(operation_key)
        if existing is not None:
            return existing
        fault = take_fault(self.table, household_id, SUBMIT_FAULTS, self.faults_enabled)
        if fault == "UNAVAILABLE":
            raise ProviderUnavailable(PROVIDER_NAME)
        if fault == "REJECT":
            return self._record(
                operation_key, "SUBMIT", status="REJECTED", reason="NOT_SERVICEABLE"
            )
        try:
            record = self._record(
                operation_key,
                "SUBMIT",
                (self._take_op(slot_id),),
                status="REQUESTED" if fault == "ACK_ONLY" else "CONFIRMED",
                provider_ref=f"DEMO-{uuid.uuid4().hex[:8].upper()}",
                slot_id=slot_id,
                fee_paise=FEE_PAISE,
            )
        except PlaceUnavailable:
            record = self._record(operation_key, "SUBMIT", status="REJECTED", reason="SLOT_TAKEN")
        if fault == "TIMEOUT_AFTER_SUCCESS":
            raise ProviderTimeout(operation_key)
        return record

    def settle(self, operation_key: str, status: str) -> dict[str, Any]:
        """The provider's answer to an acknowledged (REQUESTED) booking, entered by a
        coordinator. A rejection gives its place back in the same write."""
        record = self._existing(operation_key)
        if record is None:
            raise LookupError(operation_key)
        if record["status"] == status:
            return record  # already settled this way
        settled = {**record, "status": status, "settled_at": iso_utc(self.clock.now())}
        places = (self.release_op(record["slot_id"]),) if status == "REJECTED" else ()
        self.table.transact(
            [
                *places,
                self.table.put_if_op(
                    settled,
                    "#status = :requested",
                    {":requested": "REQUESTED"},
                    {"#status": "status"},
                ),
            ]
        )
        return settled

    def replace(
        self, household_id: str, operation_key: str, old_slot: str, new_slot: str
    ) -> dict[str, Any]:
        existing = self.status(operation_key)
        if existing is not None:
            return existing
        if take_fault(self.table, household_id, REPLACE_FAULTS, self.faults_enabled):
            return self._record(operation_key, "REPLACE", status="FAILED", reason="REPLACE_FAIL")
        try:
            record = self._record(
                operation_key,
                "REPLACE",
                (self._take_op(new_slot), self.release_op(old_slot)),
                status="REPLACED",
                slot_id=new_slot,
            )
        except PlaceUnavailable:
            record = self._record(operation_key, "REPLACE", status="FAILED", reason="SLOT_TAKEN")
        return record

    def cancel(self, household_id: str, operation_key: str, slot_id: str | None) -> dict[str, Any]:
        existing = self.status(operation_key)
        if existing is not None:
            return existing
        fault = take_fault(self.table, household_id, CANCEL_FAULTS, self.faults_enabled)
        if fault == "CANCEL_REFUSE":
            return self._record(operation_key, "CANCEL", status="REFUSED", reason="TOO_LATE")
        places = (self.release_op(slot_id),) if slot_id else ()
        try:
            record = self._record(operation_key, "CANCEL", places, status="CANCELLED")
        except PlaceUnavailable:  # nothing to release (already free): cancel all the same
            record = self._record(operation_key, "CANCEL", status="CANCELLED")
        if fault == "CANCEL_TIMEOUT":
            raise ProviderTimeout(operation_key)
        return record
