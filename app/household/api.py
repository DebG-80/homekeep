"""Household API for the web views (TDD §8.6; BRD §11.2; plan G4-3): bearer token with scope
homekeep/api, household members only.

These are the reads the agent gets through MCP, plus the owner's member management and the
judges' reset. The household always comes from the token's membership (invariant 1), and every
call authorises in the domain.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, StringConstraints

from app.admin import purge
from app.channel import pipeline
from app.domain import history, members, overview
from app.domain.context import OperationContext
from app.domain.errors import DomainError
from app.http_errors import bearer, error_response
from app.runtime import Runtime
from app.security.authz import Action, authorize
from app.store import keys

_Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]


class GrantsBody(BaseModel):
    grants: list[Literal["view", "edit", "book", "updates"]]


def _context(runtime: Runtime, authorization: str | None) -> OperationContext:
    caller = pipeline.authenticate(runtime, bearer(authorization))
    return OperationContext(
        actor=caller.actor,
        table=runtime.table,
        clock=runtime.clock,
        correlation_id=f"corr-{uuid.uuid4().hex}",
        turn_id=f"web-{uuid.uuid4().hex}",
        faults_enabled=runtime.settings.faults_enabled,
    )


def household_view(ctx: OperationContext) -> dict[str, Any]:
    meta = ctx.table.get(keys.household_pk(ctx.household_id), keys.META) or {}
    return {
        **overview.get_context(ctx),
        "role": ctx.actor.role.value if ctx.actor.role else None,
        "grants": sorted(g.value for g in ctx.actor.grants),
        "resettable": bool(meta.get("resettable")),
    }


def router() -> APIRouter:
    routes = APIRouter(prefix="/api")

    async def run(
        request: Request, authorization: str | None, operation: Callable[..., Any], *args: Any
    ) -> Any:
        runtime: Runtime = request.app.state.runtime

        def call() -> Any:
            return operation(runtime, _context(runtime, authorization), *args)

        try:
            return await anyio.to_thread.run_sync(call)
        except DomainError as error:
            return error_response(error)

    @routes.get("/household")
    async def get_household(
        request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        return await run(request, authorization, lambda _, ctx: household_view(ctx))

    @routes.get("/appliances/{appliance_id}/history")
    async def get_history(
        appliance_id: _Id, request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        return await run(
            request, authorization, lambda _, ctx: history.get_history(ctx, appliance_id)
        )

    @routes.get("/household/members")
    async def list_members(
        request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        return await run(request, authorization, lambda _, ctx: members.list_members(ctx))

    @routes.post("/household/members/{member_ref}/grants")
    async def set_grants(
        member_ref: _Id,
        body: GrantsBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        return await run(
            request,
            authorization,
            lambda _, ctx: members.set_grants(ctx, member_ref, list(body.grants)),
        )

    @routes.post("/household/members/{member_ref}/revoke")
    async def revoke(
        member_ref: _Id, request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        def operation(runtime: Runtime, ctx: OperationContext) -> dict[str, Any]:
            view, username = members.revoke(ctx, member_ref)
            runtime.sign_out(username)  # after the record changed: access has already ended
            return view

        return await run(request, authorization, operation)

    @routes.post("/household/reset")
    async def reset(request: Request, authorization: str | None = Header(default=None)) -> Any:
        def operation(runtime: Runtime, ctx: OperationContext) -> dict[str, Any]:
            authorize(ctx.actor, Action.HOUSEHOLD_RESET, ctx.household_id)
            report = purge.reset_household(
                runtime.table,
                runtime.clock,
                ctx.household_id,
                actor_label=f"owner:{ctx.actor.sub}",
            )
            return {"reset": True, "released_places": report.released_places}

        return await run(request, authorization, operation)

    return routes
