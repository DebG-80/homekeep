"""A real HomeKeep server on a free loopback port, and an MCP client to talk to it.

Contract tests go over real HTTP: MCP Streamable HTTP, OAuth bearer checks and the Origin
check all run exactly as they would behind the ALB. moto patches botocore process-wide, so the
server thread's DynamoDB calls land in the same in-memory table as the test's.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import Settings
from app.main import create_app
from app.security.attestation import Attestor
from app.security.local_issuer import LOCAL_CLIENT_ID, LocalIssuer
from app.security.tokens import SCOPE_API, SCOPE_MCP
from app.store.table import Table


@dataclass
class LiveServer:
    base_url: str
    table: Table
    issuer: LocalIssuer
    settings: Settings
    attestor: Attestor

    @property
    def mcp_url(self) -> str:
        return f"{self.base_url}/mcp"

    def token(self, identity: str = "a_owner", **kwargs: Any) -> str:
        """A token for a seeded fixture identity (subject `local-<key>`)."""
        kwargs.setdefault("client_id", LOCAL_CLIENT_ID)
        kwargs.setdefault("scopes", [SCOPE_API, SCOPE_MCP])
        return self.issuer.mint(f"local-{identity}", **kwargs)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def serve(
    table: Table, issuer: LocalIssuer, model_factory: Any = None, **env: str
) -> Iterator[LiveServer]:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    settings = Settings.from_env(
        {
            "ENV": "local",
            "DYNAMODB_ENDPOINT_URL": "http://dynamodb.invalid",  # unused: the table is injected
            "TABLE_NAME": table.name,
            "APP_BASE_URL": base_url,
            "MCP_LOOPBACK_URL": f"{base_url}/mcp",
            "MODEL_PROVIDER": "fake",
            **env,
        }
    )
    app = create_app(settings, table=table, issuer=issuer, model_factory=model_factory)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("live server did not start")
        time.sleep(0.02)
    try:
        yield LiveServer(base_url, table, issuer, settings, app.state.runtime.attestor)
    finally:
        server.should_exit = True
        thread.join(10)


@asynccontextmanager
async def mcp_session(
    url: str, token: str | None = None, headers: dict[str, str] | None = None
) -> AsyncIterator[tuple[ClientSession, Any]]:
    all_headers = dict(headers or {})
    if token:
        all_headers["Authorization"] = f"Bearer {token}"
    async with (
        httpx.AsyncClient(headers=all_headers, timeout=30) as http,
        streamable_http_client(url, http_client=http) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        initialized = await session.initialize()
        yield session, initialized


def envelope(result: Any) -> dict[str, Any]:
    """The HomeKeep result envelope carried by an MCP tool result."""
    if result.structuredContent is not None:
        content = result.structuredContent
        return content.get("result", content) if set(content) == {"result"} else content
    return json.loads(result.content[0].text)


def call_tool(
    server: LiveServer,
    tool: str,
    arguments: dict[str, Any] | None = None,
    *,
    identity: str = "a_owner",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        async with mcp_session(server.mcp_url, server.token(identity), headers) as (session, _):
            return envelope(await session.call_tool(tool, arguments or {}))

    return anyio.run(run)


def api(
    server: LiveServer, method: str, path: str, identity: str = "a_owner", **kwargs: Any
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {server.token(identity)}"}
    return httpx.request(method, f"{server.base_url}{path}", headers=headers, timeout=60, **kwargs)


def new_session(server: LiveServer, identity: str = "a_owner") -> str:
    response = api(server, "POST", "/api/sessions", identity)
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def turn(
    server: LiveServer,
    session_id: str,
    text: str,
    turn_id: str | None = None,
    identity: str = "a_owner",
) -> dict[str, Any]:
    import uuid

    body = {
        "session_id": session_id,
        "turn_id": turn_id or f"turn-{uuid.uuid4().hex[:12]}",
        "text": text,
    }
    response = api(server, "POST", "/api/turns", identity, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def spoken(response: dict[str, Any]) -> str:
    return " ".join(response["speech"])
