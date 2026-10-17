"""FastAPI entry point: liveness, the turn API, the staff API, the reconciliation sweep, the MCP
server at /mcp and, in ENV=local, local sign-in.

Run with `uvicorn --factory app.main:create_app`: settings are read when the app is built, so a
misconfigured environment stops startup (G-3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI

from app import local_auth, web
from app.channel import api as channel_api
from app.config import ConfigError, Settings
from app.domain.clock import Clock, clock_from_settings
from app.household import api as household_api
from app.logging import configure_logging
from app.mcp_server.server import build_mcp, build_mcp_app
from app.orchestrator.fake_model import LocalScripts
from app.provider.sweep import run_sweep
from app.runtime import Runtime
from app.security.attestation import Attestor
from app.security.local_issuer import LocalIssuer
from app.security.signout import build_sign_out
from app.security.verifier import build_token_verifier
from app.staff import api as staff_api
from app.store.table import Table


def create_app(
    settings: Settings | None = None,
    *,
    table: Table | None = None,
    issuer: LocalIssuer | None = None,
    clock: Clock | None = None,
    model_factory: Callable[[], Any] | None = None,
    start_sweep: bool = True,
    web_dist: Path | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    if issuer is not None and settings.env != "local":
        raise ConfigError("the local token issuer is allowed only when ENV=local")
    if settings.env == "local" and issuer is None:
        issuer = LocalIssuer()
    local_scripts = None
    if settings.env == "local" and settings.model_provider == "fake" and model_factory is None:
        local_scripts = model_factory = LocalScripts()  # E2E drives the fake model (G4-7)
    runtime = Runtime(
        settings=settings,
        table=table or Table.from_settings(settings),
        clock=clock or clock_from_settings(settings),
        verifier=build_token_verifier(settings, issuer),
        attestor=Attestor(),  # per-process key: valid because there is exactly one worker
        local_issuer=issuer,
        model_factory=model_factory,  # tests inject a scripted model; otherwise per settings
        sign_out=build_sign_out(settings),
    )
    mcp = build_mcp(runtime)
    mcp_app = build_mcp_app(mcp)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = runtime
        async with mcp.session_manager.run(), anyio.create_task_group() as tasks:
            if start_sweep:  # P3-1; tests call sweep_once directly
                tasks.start_soon(run_sweep, runtime.table, runtime.clock, settings.faults_enabled)
            yield
            tasks.cancel_scope.cancel()

    app = FastAPI(
        title="HomeKeep", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        # Liveness only: no AWS calls, so a DynamoDB or Bedrock hiccup never restarts the task.
        return {"status": "ok"}

    app.include_router(channel_api.router())
    app.include_router(staff_api.router())
    app.include_router(household_api.router())
    if issuer is not None:
        app.include_router(local_auth.router(issuer, local_scripts))
    web.install(app, settings, web_dist or web.WEB_DIST, local_sign_in=issuer is not None)
    app.mount("/", mcp_app)  # last: /mcp and the protected-resource metadata
    return app
