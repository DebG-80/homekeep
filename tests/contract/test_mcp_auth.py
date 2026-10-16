from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import anyio
import httpx

from app.mcp_server.names import CUSTOMER_TOOLS, TRUSTED_TOOLS
from app.security.local_issuer import LOCAL_ISSUER
from app.security.tokens import SCOPE_API, SCOPE_MCP
from tests.contract.live import LiveServer, mcp_session

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "contract-test", "version": "1"},
    },
}
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _post(live: LiveServer, token: str | None = None, **headers: str) -> httpx.Response:
    all_headers = {**ACCEPT, **headers}
    if token:
        all_headers["Authorization"] = f"Bearer {token}"
    return httpx.post(live.mcp_url, json=INITIALIZE, headers=all_headers, timeout=10)


def test_nfr04_no_token_gets_401_with_resource_metadata(live: LiveServer) -> None:
    response = _post(live)
    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer")
    match = re.search(r'resource_metadata="([^"]+)"', challenge)
    assert match
    assert match.group(1) == f"{live.base_url}/.well-known/oauth-protected-resource/mcp"


def test_nfr04_prm_names_issuer_and_scope_at_both_paths(live: LiveServer) -> None:
    for path in (
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/oauth-protected-resource",
    ):
        metadata = httpx.get(f"{live.base_url}{path}", timeout=10).json()
        assert metadata["resource"].rstrip("/") == f"{live.base_url}/mcp", path
        assert [s.rstrip("/") for s in metadata["authorization_servers"]] == [LOCAL_ISSUER], path
        assert metadata["scopes_supported"] == [SCOPE_MCP], path


def test_nfr04_wrong_scope_expired_and_unknown_client_refused(live: LiveServer) -> None:
    assert _post(live, live.token(scopes=[SCOPE_API])).status_code == 403  # API scope only
    expired = live.token(now=datetime.now(UTC) - timedelta(hours=2))
    assert _post(live, expired).status_code == 401
    assert _post(live, live.token(client_id="not-a-homekeep-client")).status_code == 401
    id_token = live.token(token_use="id")  # noqa: S106 (a JWT claim value, not a password)
    assert _post(live, id_token).status_code == 401
    assert _post(live, live.token()).status_code == 200


def test_nfr04_disallowed_origin_rejected(live: LiveServer) -> None:
    # DNS-rebinding defence (TDD §5.1): a foreign Origin is refused even with a valid token.
    assert _post(live, live.token(), Origin="https://evil.example").status_code == 403
    assert _post(live, live.token(), Origin=live.base_url).status_code == 200


def test_inv1_tool_schemas_have_no_household_argument(live: LiveServer) -> None:
    async def run() -> dict[str, dict]:
        async with mcp_session(live.mcp_url, live.token()) as (session, _):
            return {t.name: t.inputSchema for t in (await session.list_tools()).tools}

    schemas = anyio.run(run)
    assert set(schemas) == set(CUSTOMER_TOOLS) | {"cancel_pending_action"}
    assert set(TRUSTED_TOOLS) >= {"cancel_pending_action", "confirm_action", "execute_action"}
    for name, schema in schemas.items():
        properties = {p.casefold() for p in schema.get("properties", {})}
        assert not any(re.search(r"household|tenant|\bhh\b|^hh_", p) for p in properties), name
