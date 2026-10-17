"""A real HomeKeep server on a free loopback port, in this process (TDD §12.1).

Used by the contract tests and by the eval and load runners: the turn API, MCP Streamable HTTP,
OAuth bearer checks and the Origin check run exactly as they do behind the ALB. The table is
injected (moto in tests, DynamoDB Local for evals).
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import uvicorn

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
    table: Table,
    issuer: LocalIssuer,
    model_factory: Any = None,
    clock: Any = None,
    web_dist: Any = None,
    **env: str,
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
    app = create_app(
        settings,
        table=table,
        issuer=issuer,
        model_factory=model_factory,
        clock=clock,
        start_sweep=False,
        web_dist=web_dist,
    )
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
