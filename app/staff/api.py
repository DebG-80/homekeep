"""Staff API (TDD §4.10; plan P3-2): bearer token with scope homekeep/api and a staff group.

Routes take only opaque record references; the household is resolved from the reference
(G3-1). The domain checks role and assignment on every call. The Ops page stays deferred (P1-1).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field, StringConstraints

from app.domain import staff
from app.domain.context import OperationContext
from app.domain.errors import DomainError, ErrorCode
from app.http_errors import bearer, error_response
from app.runtime import Runtime
from app.security.actor import ActorKind
from app.security.membership import resolve_actor
from app.security.tokens import SCOPE_API

_Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]
_Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


class EventBody(BaseModel):
    event_id: _Id
    type: Literal[
        "VISIT_STARTED",
        "WORK_NOTE",
        "VISIT_COMPLETED",
        "NO_SHOW",
        "PROVIDER_CONFIRMED",
        "PROVIDER_REJECTED",
    ]
    expected_version: int = Field(ge=1)
    summary: _Text | None = None


class AssignBody(BaseModel):
    technician_sub: _Id


class NoteBody(BaseModel):
    note: _Text = ""


class EvidenceBody(BaseModel):
    evidence: _Text


class VerifyModelBody(BaseModel):
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    document_id: _Id


def _context(runtime: Runtime, token: str | None) -> OperationContext:
    if not token:
        raise DomainError(ErrorCode.AUTH_DENIED, "NO_TOKEN")
    verified = runtime.verifier.verify(token, SCOPE_API)
    actor = resolve_actor(runtime.table, verified)
    if actor.kind is not ActorKind.STAFF:
        raise DomainError(ErrorCode.AUTH_DENIED, "NOT_STAFF")
    return OperationContext(
        actor=actor,
        table=runtime.table,
        clock=runtime.clock,
        correlation_id=f"corr-{uuid.uuid4().hex}",
        turn_id=f"staff-{uuid.uuid4().hex}",
        faults_enabled=runtime.settings.faults_enabled,
    )


def router() -> APIRouter:
    routes = APIRouter(prefix="/api/staff")

    async def run(
        request: Request,
        authorization: str | None,
        operation: Callable[..., Any],
        *args: Any,
    ) -> Any:
        runtime: Runtime = request.app.state.runtime

        def call() -> Any:
            return operation(_context(runtime, bearer(authorization)), *args)

        try:
            return await anyio.to_thread.run_sync(call)
        except DomainError as error:
            return error_response(error)

    @routes.get("/queue")
    async def queue(request: Request, authorization: str | None = Header(default=None)) -> Any:
        return await run(request, authorization, staff.queue)

    @routes.get("/cases/{case_id}")
    async def case_view(
        case_id: _Id, request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        return await run(request, authorization, staff.case_view, case_id)

    @routes.post("/cases/{case_id}/events")
    async def post_event(
        case_id: _Id,
        body: EventBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        return await run(
            request,
            authorization,
            staff.post_event,
            case_id,
            body.event_id,
            body.type,
            body.expected_version,
            body.summary,
        )

    @routes.post("/cases/{case_id}/assign")
    async def assign(
        case_id: _Id,
        body: AssignBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        return await run(request, authorization, staff.assign, case_id, body.technician_sub)

    @routes.get("/technicians")
    async def technicians(
        request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        return await run(request, authorization, staff.technicians)

    @routes.get("/manual")
    async def manual(request: Request, authorization: str | None = Header(default=None)) -> Any:
        return await run(request, authorization, staff.manual_items)

    @routes.post("/manual/{item_id}/resolve")
    async def resolve_manual(
        item_id: _Id,
        body: NoteBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        return await run(request, authorization, staff.resolve_manual, item_id, body.note)

    @routes.get("/safety")
    async def safety(request: Request, authorization: str | None = Header(default=None)) -> Any:
        return await run(request, authorization, staff.safety_items)

    @routes.post("/issues/{issue_id}/clear-safety")
    async def clear_safety(
        issue_id: _Id,
        body: EvidenceBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        return await run(request, authorization, staff.clear_issue_safety, issue_id, body.evidence)

    @routes.post("/safety-holds/{hold_id}/clear")
    async def clear_hold(
        hold_id: _Id,
        body: EvidenceBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        return await run(request, authorization, staff.clear_safety_hold, hold_id, body.evidence)

    @routes.post("/appliances/{appliance_id}/verify-model")
    async def verify_model(
        appliance_id: _Id,
        body: VerifyModelBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        return await run(
            request, authorization, staff.verify_model, appliance_id, body.model, body.document_id
        )

    return routes
