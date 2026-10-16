"""Session and turn API (TDD §3.4 F1): bearer token with scope homekeep/api."""

from __future__ import annotations

import re
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints

from app.channel import pipeline, sessions
from app.domain.errors import DomainError, ErrorCode
from app.runtime import Runtime

_STATUS = {ErrorCode.AUTH_DENIED: 401, ErrorCode.INVALID_INPUT: 404}


class TurnRequest(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    turn_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    speech_started_at: str | None = None
    playback_ended_at: str | None = None


def _bearer(authorization: str | None) -> str | None:
    match = re.match(r"^Bearer\s+(\S+)$", authorization or "")
    return match.group(1) if match else None


def _error(error: DomainError) -> JSONResponse:
    status = _STATUS.get(error.code, 400)
    if error.code is ErrorCode.INVALID_INPUT and error.reason != "NOT_FOUND":
        status = 400
    body = {"error": {"code": error.code.value, "reason": error.reason, "message": error.message}}
    return JSONResponse(body, status_code=status)


def router() -> APIRouter:
    routes = APIRouter(prefix="/api")

    def runtime_of(request: Request) -> Runtime:
        return request.app.state.runtime

    async def caller_of(request: Request, authorization: str | None) -> pipeline.Caller:
        runtime = runtime_of(request)
        return await anyio.to_thread.run_sync(
            pipeline.authenticate, runtime, _bearer(authorization)
        )

    @routes.post("/sessions")
    async def start_session(
        request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        try:
            caller = await caller_of(request, authorization)
            runtime = runtime_of(request)
            session = await anyio.to_thread.run_sync(
                sessions.create_session,
                runtime.table,
                caller.household_id,
                caller.verified.sub,
                runtime.clock.now(),
            )
        except DomainError as error:
            return _error(error)
        return {"session_id": session["session_id"]}

    @routes.post("/turns")
    async def post_turn(
        body: TurnRequest, request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        try:
            caller = await caller_of(request, authorization)
            return await pipeline.handle_turn(
                runtime_of(request), caller, body.session_id, body.turn_id, body.text
            )
        except DomainError as error:
            return _error(error)

    @routes.get("/sessions/{session_id}/state")
    async def session_state(
        session_id: str, request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        try:
            caller = await caller_of(request, authorization)
            session = await anyio.to_thread.run_sync(
                sessions.load_session, runtime_of(request).table, caller.household_id, session_id
            )
        except DomainError as error:
            return _error(error)
        keys = (
            "session_id",
            "active_issue_id",
            "last_step_id",
            "pending_approval_id",
            "messages",
            "speech_rate",
        )
        return {k: session.get(k) for k in keys}

    return routes
