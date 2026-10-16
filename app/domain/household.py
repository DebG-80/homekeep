"""Household and consent (FR-01).

Storage consent is required before anything persistent is created. Its current decision is
denormalised onto the household `META` item, so every persistence transaction can check it with a
ConditionCheck. Declining optional sharing creates no grant and blocks nothing else (AT-02).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.domain import mutations
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.ids import ordered_id
from app.security.authz import Action, authorize
from app.store import keys


class ConsentPurpose(StrEnum):
    STORAGE = "STORAGE"
    SHARING = "SHARING"


class ConsentDecision(StrEnum):
    GRANTED = "GRANTED"
    DECLINED = "DECLINED"


_CONSENT_ATTRIBUTE = {
    ConsentPurpose.STORAGE: "storage_consent",
    ConsentPurpose.SHARING: "sharing_consent",
}


def _meta(ctx: OperationContext) -> dict[str, Any]:
    meta = ctx.table.get(keys.household_pk(ctx.household_id), keys.META)
    if meta is None:
        raise DomainError(ErrorCode.AUTH_DENIED, "HOUSEHOLD_NOT_FOUND")
    return meta


def _view(meta: dict[str, Any]) -> dict[str, Any]:
    # Address and contact details are deliberately not part of this view.
    return {
        "locale": meta.get("locale"),
        "timezone": meta.get("timezone"),
        "storage_consent": meta.get("storage_consent"),
        "sharing_consent": meta.get("sharing_consent"),
        "version": meta["version"],
    }


def get_household(ctx: OperationContext) -> dict[str, Any]:
    authorize(ctx.actor, Action.HOUSEHOLD_READ, ctx.household_id)
    return _view(_meta(ctx))


def require_storage_consent(ctx: OperationContext) -> None:
    """Fast, readable refusal before building a transaction; the transaction re-checks it."""
    if _meta(ctx).get("storage_consent") != ConsentDecision.GRANTED:
        raise DomainError(ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED")


def record_consent(
    ctx: OperationContext,
    purpose: ConsentPurpose,
    decision: ConsentDecision,
    consent_version: str,
) -> dict[str, Any]:
    authorize(ctx.actor, Action.CONSENT_RECORD, ctx.household_id)
    args = {"purpose": purpose.value, "decision": decision.value, "version": consent_version}

    def body(mutation: mutations.Mutation) -> Any:
        meta = _meta(ctx)
        now = iso_utc(ctx.clock.now())
        new_meta = {
            **meta,
            _CONSENT_ATTRIBUTE[purpose]: decision.value,
            f"{_CONSENT_ATTRIBUTE[purpose]}_version": consent_version,
            "updated_at": now,
            "version": meta["version"] + 1,
        }
        consent_sk = keys.consent_sk(purpose.value, now, ordered_id())
        consent_record = {
            "PK": keys.household_pk(ctx.household_id),
            "SK": consent_sk,
            "kind": "CONSENT",
            "purpose": purpose.value,
            "decision": decision.value,
            "consent_version": consent_version,
            "actor_sub": ctx.actor.sub,
            "at": now,
        }
        operations = [
            ctx.table.put_versioned_op(new_meta, meta["version"]),
            ctx.table.put_new_op(consent_record),
            ctx.table.put_op(
                event_item(
                    ctx,
                    action="CONSENT_RECORDED",
                    record_sk=consent_sk,
                    appliance_id=None,
                    prior_version=meta["version"],
                    new_version=new_meta["version"],
                )
            ),
        ]
        try:
            return mutations.commit(ctx, mutation, operations, _view(new_meta))
        except ConflictError as exc:
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    return mutations.run(ctx, "record_consent", args, body)
