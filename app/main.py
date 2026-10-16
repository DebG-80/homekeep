"""FastAPI entry point. Slice 0 serves only the liveness check."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Fail fast: an environment that breaks the contract stops startup (G-3).
        app.state.settings = settings or Settings.from_env()
        yield

    app = FastAPI(title="HomeKeep", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        # Liveness only: no AWS calls, so a DynamoDB or Bedrock hiccup never restarts the task.
        return {"status": "ok"}

    return app


app = create_app()
