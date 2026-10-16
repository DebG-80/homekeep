"""Focused symptom collection (FR-06): one approved question at a time, every answer saved at once.

"Not sure" is a valid answer: it is stored as UNKNOWN with no invented value, and that field
counts as asked, so a restarted session does not ask it again (AT-07).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from app.domain import appliances, issues, mutations
from app.domain.clock import iso_utc
from app.domain.context import OperationContext
from app.domain.errors import ConflictError, DomainError, ErrorCode
from app.domain.events import event_item
from app.domain.household import require_storage_consent
from app.domain.state import IssueEvent, IssueStatus
from app.security.authz import Action, authorize
from app.store import keys

INTAKE_DIR = Path(__file__).resolve().parents[2] / "catalog_data" / "intake"
_INTAKE_FILES = {appliances.Category.AC.value: "ac.json"}
_UNKNOWN_WORDS = {"unknown", "not sure", "i don't know", "don't know", "dont know", "skip"}


@cache
def intake_definition(category: str) -> dict[str, Any] | None:
    name = _INTAKE_FILES.get(category)
    if name is None:
        return None  # fridge and TV use generic prompts (Slice 2)
    return json.loads((INTAKE_DIR / name).read_text(encoding="utf-8"))


def _intake_for_issue(ctx: OperationContext, issue: dict[str, Any]) -> dict[str, Any] | None:
    appliance = appliances.load(ctx, issue["appliance_id"])
    return intake_definition(appliance["category"])


def next_intake_question(ctx: OperationContext, issue_id: str) -> dict[str, Any] | None:
    """The first approved question with no saved answer (answered or unknown), or None."""
    authorize(ctx.actor, Action.ISSUE_READ, ctx.household_id)
    issue = issues.load(ctx, issue_id)
    intake = _intake_for_issue(ctx, issue)
    if intake is None:
        return None
    saved = {
        o["field"]
        for o in ctx.table.query(
            keys.household_pk(ctx.household_id), keys.observation_prefix(issue_id)
        )
    }
    for question in intake["questions"]:
        if question["field"] not in saved:
            return {"field": question["field"], "question": question["question"]}
    return None


def record_observation(
    ctx: OperationContext,
    issue_id: str,
    field: str,
    value: str | None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Save one answer. `expected_version` is the saved answer's version when changing it, or
    None for a first answer; a stale version is a RECORD_CONFLICT."""
    authorize(ctx.actor, Action.OBSERVATION_WRITE, ctx.household_id)
    args = {
        "issue_id": issue_id,
        "field": field,
        "value": value,
        "expected_version": expected_version,
    }

    def body(mutation: mutations.Mutation) -> Any:
        require_storage_consent(ctx)
        issue = issues.load(ctx, issue_id)
        intake = _intake_for_issue(ctx, issue)
        if intake is None:
            raise DomainError(ErrorCode.INVALID_INPUT, "NO_INTAKE_FOR_CATEGORY")
        if field not in {q["field"] for q in intake["questions"]}:
            raise DomainError(ErrorCode.INVALID_INPUT, "UNKNOWN_FIELD")

        pk = keys.household_pk(ctx.household_id)
        sk = keys.observation_sk(issue_id, field)
        is_unknown = value is None or appliances.normalise(value) in _UNKNOWN_WORDS
        now = iso_utc(ctx.clock.now())
        observation = {
            "PK": pk,
            "SK": sk,
            "kind": "OBSERVATION",
            "issue_id": issue_id,
            "field": field,
            "value": None if is_unknown else value.strip(),
            "status": "UNKNOWN" if is_unknown else "ANSWERED",
            "provenance": {"source": "USER", "actor_sub": ctx.actor.sub, "at": now},
            "intake_version": intake["version"],
            "version": 1 if expected_version is None else expected_version + 1,
        }
        operations = [mutations.storage_consent_check(ctx)]
        if expected_version is None:
            operations.append(ctx.table.put_new_op(observation))
        else:
            operations.append(ctx.table.put_versioned_op(observation, expected_version))
        if issue["status"] == IssueStatus.OPEN.value:
            # The first saved intake answer starts triage (BRD §7.1: OPEN → TRIAGING).
            started = issues.transition_item(ctx, issue, IssueEvent.INTAKE_STARTED, None)
            operations.append(ctx.table.put_versioned_op(started, issue["version"]))
        operations.append(
            ctx.table.put_op(
                event_item(
                    ctx,
                    action="OBSERVATION_RECORDED",
                    record_sk=sk,
                    appliance_id=issue["appliance_id"],
                    prior_version=expected_version,
                    new_version=observation["version"],
                )
            )
        )
        result = {k: observation[k] for k in ("issue_id", "field", "value", "status", "version")}
        try:
            return mutations.commit(ctx, mutation, operations, result)
        except ConflictError as exc:
            if 0 in exc.failed_indexes:
                raise DomainError(
                    ErrorCode.CONSENT_REQUIRED, "STORAGE_CONSENT_NOT_GRANTED"
                ) from exc
            raise DomainError(ErrorCode.RECORD_CONFLICT, "STALE_VERSION") from exc

    return mutations.run(ctx, "record_observation", args, body)
