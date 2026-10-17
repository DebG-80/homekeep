"""Judge reset and test-household purge (FR-24; AT-25; TDD §9.2; plan G4-6).

Everything a household owns is found from its own partition: the records under `HH#{id}`, the
opaque references named by those records, the membership lookups of its members, its manual
review items and its fault item. Nothing is found by scanning the table, so no other household
can be touched. Slot places its bookings still hold are given back first.

A reset keeps the memberships (the judge stays signed in) and rebuilds the household from its
fixture. A purge removes everything and returns the sign-in names to sign out of Cognito. Both
are audited in the `OPS` partition, outside the household (BRD §11.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.admin.audit import audit
from app.admin.fixtures import household_items, load_fixtures
from app.domain.clock import Clock, iso_utc
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.ids import ordered_id
from app.domain.state import RequestStatus
from app.provider.simulator import DemoProvider
from app.store import keys
from app.store.table import Table

R = RequestStatus
# States in which the provider holds a place for the request's slot.
_HOLDING = frozenset({R.REQUESTED, R.CONFIRMED, R.IN_PROGRESS})
# Kept by a reset: the judge stays signed in, and the daily turn cap is not reset (NFR-12).
_KEPT_BY_RESET = (keys.MEMBER_PREFIX, "USAGE#")


@dataclass
class ResetReport:
    deleted: int = 0
    released_places: int = 0
    restored: int = 0


@dataclass
class PurgeReport:
    deleted: int = 0
    released_places: int = 0
    signed_out: list[str] = field(default_factory=list)


def _refs(items: list[dict[str, Any]]) -> list[str]:
    """The opaque IDs this household's records published as `REF#` items."""
    ids_by_kind = {"APPLIANCE": "appliance_id", "ISSUE": "issue_id", "SR": "request_id"}
    found = [item[ids_by_kind[item["kind"]]] for item in items if item.get("kind") in ids_by_kind]
    found += [item["SK"].removeprefix("HOLD#") for item in items if item.get("kind") == "HOLD"]
    return found


def _places(provider: DemoProvider, request: dict[str, Any], now: str) -> list[str]:
    """The slots whose places this request still holds at the provider."""
    state = RequestStatus(request["state"])
    slot_id = request.get("slot_id")
    if state in _HOLDING and slot_id:
        return [slot_id]
    if state is R.CANCEL_PENDING and slot_id:
        record = provider.status(request["cancel_op"]) if request.get("cancel_op") else None
        if record and record["status"] == "CANCELLED":
            return []  # the provider already gave the place back; its reply was lost
        return [slot_id]
    if state is R.COMPLETED and slot_id and provider.slot(slot_id).start_utc > now:
        return [slot_id]  # a demo visit marked done ahead of time: free the place again
    if state is R.SUBMISSION_PENDING and request.get("op_key"):
        record = provider.status(request["op_key"])
        if record and record["status"] in ("CONFIRMED", "REQUESTED"):
            return [record["slot_id"]]
    if state is R.CHANGE_PENDING and request.get("change_op"):
        record = provider.status(request["change_op"])
        if record and record["status"] == "REPLACED":
            return [record["slot_id"]]  # the provider already moved the place
        return [slot_id] if slot_id else []
    return []


def _release_places(table: Table, clock: Clock, items: list[dict[str, Any]]) -> int:
    """Give back each request's places together with deleting the request, conditional on its
    version: a second reset or purge racing this one finds the request gone and releases
    nothing, so the shared slot inventory is never over-credited (AT-15)."""
    provider = DemoProvider(table, clock, faults_enabled=False)
    now = iso_utc(clock.now())
    released = 0
    for request in (i for i in items if i.get("kind") == "SR"):
        places = _places(provider, request, now)
        if not places:
            continue
        try:
            table.transact(
                [
                    *(provider.release_op(slot_id) for slot_id in places),
                    table.delete_op(request["PK"], request["SK"], request["version"]),
                ]
            )
        except ConflictError:
            continue  # already released by a concurrent reset, or the request moved on
        released += len(places)
    return released


def _delete_outside(table: Table, household_id: str, items: list[dict[str, Any]]) -> int:
    """References, manual-review items and the fault item that belong to this household."""
    deleted = 0
    for ref_id in _refs(items):
        ref = table.get(keys.ref_pk(ref_id), keys.META)
        if ref is not None and ref["household_id"] == household_id:  # belt and braces
            table.delete(ref["PK"], ref["SK"])
            deleted += 1
    for manual in table.query(keys.OPS_PK, "MANUAL#"):
        if manual.get("household_id") == household_id:
            table.delete(manual["PK"], manual["SK"])
            deleted += 1
    if table.get(keys.PROVIDER_PK, keys.fault_sk(household_id)) is not None:
        table.delete(keys.PROVIDER_PK, keys.fault_sk(household_id))
        deleted += 1
    return deleted


def _meta(table: Table, household_id: str) -> dict[str, Any]:
    meta = table.get(keys.household_pk(household_id), keys.META)
    if meta is None:
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_FOUND")
    return meta


def reset_household(
    table: Table, clock: Clock, household_id: str, *, actor_label: str
) -> ResetReport:
    """Restore a resettable (judge) household to its seed, keeping its members signed in."""
    meta = _meta(table, household_id)
    if not meta.get("resettable"):
        raise DomainError(ErrorCode.INVALID_INPUT, "NOT_RESETTABLE")
    pk = keys.household_pk(household_id)
    items = table.query(pk)
    report = ResetReport(released_places=_release_places(table, clock, items))
    report.deleted = _delete_outside(table, household_id, items)
    memberships = [i for i in items if i.get("kind") == "MEMBERSHIP"]
    for item in items:
        # META stays until the fixture overwrites it, so a reset that stops midway can simply
        # be run again; memberships and the day's turn count are kept.
        if item["SK"] == keys.META or item["SK"].startswith(_KEPT_BY_RESET):
            continue
        table.delete(item["PK"], item["SK"])
        report.deleted += 1

    households, identities = load_fixtures()
    fixture = next(h for h in households["households"] if h["household_id"] == household_id)
    by_key = {identity["key"]: identity for identity in identities}
    members = [
        (by_key[m["identity_key"]], m["sub"])
        for m in memberships
        if m.get("identity_key") in by_key
    ]
    for item in household_items(
        fixture, members, households["seeded_at"], households["consent_version"]
    ):
        if item["kind"] == "MEMBERSHIP_LOOKUP":
            continue  # kept: the member is still linked to this household
        table.put(item)  # memberships too: the seed's role, grants and status come back
        report.restored += 1
    now = iso_utc(clock.now())
    table.put_new(
        {
            "PK": pk,
            "SK": keys.event_sk(None, now, ordered_id()),
            "kind": "EVENT",
            "at": now,
            "actor_sub": actor_label,
            "actor_role": actor_label.split(":")[0].upper(),
            "action": "HOUSEHOLD_RESET",
            "result": "OK",
            "record": keys.META,
            "appliance_id": None,
            "provenance": "CUSTOMER" if actor_label.startswith("owner") else "OPERATOR",
        }
    )
    audit(
        table,
        clock,
        "HOUSEHOLD_RESET",
        actor_label,
        target_household=household_id,
        deleted=report.deleted,
        released_places=report.released_places,
    )
    return report


def purge_household(
    table: Table, clock: Clock, household_id: str, *, actor_label: str
) -> PurgeReport:
    """Remove a test household completely and revoke its members' access (FR-24-AC1)."""
    _meta(table, household_id)
    items = table.query(keys.household_pk(household_id))
    report = PurgeReport(released_places=_release_places(table, clock, items))
    report.deleted = _delete_outside(table, household_id, items)
    for member in (i for i in items if i.get("kind") == "MEMBERSHIP"):
        table.delete(keys.user_pk(member["sub"]), keys.user_household_sk(household_id))
        report.deleted += 1
        report.signed_out.append(member.get("display_name") or member["sub"])
    for item in items:
        table.delete(item["PK"], item["SK"])
        report.deleted += 1
    audit(
        table,
        clock,
        "HOUSEHOLD_PURGED",
        actor_label,
        target_household=household_id,
        deleted=report.deleted,
        released_places=report.released_places,
    )
    return report
