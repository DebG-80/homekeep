"""Evidence-only guidance (FR-08, FR-09; CLAUDE.md invariant 7).

A model-specific step is given only when every condition holds: the appliance's model is
VERIFIED with no open conflict, a catalog item for that exact model is PUBLISHED (file status plus
the runtime overlay), the sources agree on this symptom, and the issue has no safety flag.
Otherwise the answer is NO_APPROVED_GUIDANCE with a reason, and service is offered. Recording a
step's outcome never resolves the issue.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.catalog.loader import CatalogItem, Step, load_catalog
from app.catalog.overlay import effective_status
from app.domain import appliances, issues, mutations
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.household import require_storage_consent
from app.domain.ids import ordered_id
from app.security.authz import Action, authorize
from app.store import keys


class StepResult(StrEnum):
    NOT_TRIED = "NOT_TRIED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    UNSUCCESSFUL = "UNSUCCESSFUL"


def _refuse(reason: str, **details: Any) -> DomainError:
    return DomainError(ErrorCode.NO_APPROVED_GUIDANCE, reason, {"offer": "SERVICE", **details})


def _generic_prompts(category: str) -> list[str]:
    try:
        return list(load_catalog().generic_prompts.prompts.get(category, ()))
    except Exception:  # the prompts are a courtesy; their absence must not hide the refusal
        return []


def recorded_steps(ctx: OperationContext, issue_id: str) -> list[dict[str, Any]]:
    items = ctx.table.query(keys.household_pk(ctx.household_id), keys.step_prefix(issue_id))
    return [
        {k: item[k] for k in ("step_id", "result", "catalog_item", "catalog_version", "at")}
        for item in items
    ]


def _symptom_key(ctx: OperationContext, issue: dict[str, Any]) -> str:
    if issue["symptom_category"] != "ERROR_CODE":
        return issue["symptom_category"]
    observation = ctx.table.get(
        keys.household_pk(ctx.household_id), keys.observation_sk(issue["issue_id"], "display_code")
    )
    code = (observation or {}).get("value")
    if not code:
        raise _refuse("NO_STEP_FOR_SYMPTOM", needs_observation="display_code")
    return f"E:{code.strip().upper()}"


def _published_item(ctx: OperationContext, model: str, key: str) -> CatalogItem:
    try:
        catalog = load_catalog()
        items = catalog.items_for_model(model)
        statuses = {(i.item_id, i.version): effective_status(ctx.table, i) for i in items}
        conflicts = catalog.conflicting_keys(model)
    except DomainError:
        raise
    except Exception as exc:  # catalog or overlay unreadable: never guess (AT-09)
        raise _refuse("RETRIEVAL_FAILURE") from exc
    published = [i for i in items if statuses[(i.item_id, i.version)] == "PUBLISHED"]
    if not published:
        was_published = any(i.status == "PUBLISHED" for i in items)
        raise _refuse("WITHDRAWN" if was_published else "NOT_PUBLISHED")
    if key in conflicts:
        raise _refuse("CONFLICTING_SOURCES")
    covering = [i for i in published if i.steps_for(key)]
    if not covering:
        raise _refuse("NO_STEP_FOR_SYMPTOM")
    return covering[0]


def get_guidance(ctx: OperationContext, issue_id: str) -> dict[str, Any]:
    authorize(ctx.actor, Action.ISSUE_READ, ctx.household_id)
    issue = issues.load(ctx, issue_id)
    appliance = appliances.load(ctx, issue["appliance_id"])
    category = appliance["category"]
    if issue["safety_flag"] or issues.household_safety_hold(ctx):
        raise _refuse("SAFETY_FLAG")
    if category != appliances.Category.AC.value:
        scope = load_catalog().generic_prompts.scope_limit.get(category)
        raise _refuse("SCOPE_LIMIT", generic_prompts=_generic_prompts(category), scope_limit=scope)
    model = appliance["fields"]["model"]
    if model["status"] != appliances.FieldStatus.VERIFIED.value or not model["value"]:
        raise _refuse("UNVERIFIED_MODEL", generic_prompts=_generic_prompts(category))
    if any(c.get("field") == "model" for c in appliance.get("conflicts", [])):
        raise _refuse("CONFLICTING_SOURCES")

    key = _symptom_key(ctx, issue)
    item = _published_item(ctx, model["value"], key)
    done = {s["step_id"] for s in recorded_steps(ctx, issue_id)}
    step = next((s for s in item.steps_for(key) if s.step_id not in done), None)
    if step is None:
        raise _refuse("STEPS_EXHAUSTED")
    return _offer(issue_id, item, step)


def _offer(issue_id: str, item: CatalogItem, step: Step) -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "step": {"step_id": step.step_id, "speech": step.speech, "helper_only": step.helper_only},
        # Retrieved text is evidence, never instructions: it travels only in this typed field.
        "evidence": {
            "catalog_item": item.item_id,
            "version": item.version,
            "document_id": item.document_id,
            "locator": step.locator,
            "excerpt": step.evidence,
            "reviewer": item.reviewer,
            "review_date": item.review_date,
        },
    }


def _catalog_step(step_id: str) -> tuple[CatalogItem, Step]:
    for item in load_catalog().items:
        for step in item.all_steps():
            if step.step_id == step_id:
                return item, step
    raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_STEP")


def record_step_result(
    ctx: OperationContext, issue_id: str, step_id: str, result: str
) -> dict[str, Any]:
    authorize(ctx.actor, Action.OBSERVATION_WRITE, ctx.household_id)
    try:
        outcome = StepResult(result)
    except ValueError:
        raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_STEP_RESULT") from None
    args = {"issue_id": issue_id, "step_id": step_id, "result": outcome.value}

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        issue = issues.load(ctx, issue_id)
        item, _ = _catalog_step(step_id)
        now = iso_utc(ctx.clock.now())
        sk = keys.step_sk(issue_id, now, ordered_id(), step_id)
        record = {
            "PK": keys.household_pk(ctx.household_id),
            "SK": sk,
            "kind": "STEP",
            "issue_id": issue_id,
            "step_id": step_id,
            "result": outcome.value,
            "catalog_item": item.item_id,
            "catalog_version": item.version,  # source version kept with the outcome (FR-09)
            "symptom_category": issue["symptom_category"],
            "actor_sub": ctx.actor.sub,
            "at": now,
        }
        operations = [
            mutations.storage_consent_check(ctx),
            ctx.table.put_new_op(record),
            ctx.table.put_new_op(
                event_item(
                    ctx,
                    action="STEP_RESULT_RECORDED",
                    record_sk=sk,
                    appliance_id=issue["appliance_id"],
                    prior_version=None,
                    new_version=None,
                )
            ),
        ]
        # The issue's status is untouched: completing a check is not a repair (FR-09-AC2).
        result_view = {
            "issue_id": issue_id,
            "step_id": step_id,
            "result": outcome.value,
            "issue_status": issue["status"],
        }
        try:
            return mutations.commit(ctx, mutation, operations, result_view)
        except ConflictError as exc:
            if 0 in exc.failed_indexes:
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            raise

    return mutations.run(ctx, "record_step_result", args, body)
