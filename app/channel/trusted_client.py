"""The channel's attested MCP client (TDD §5.3). Never given to the agent.

It calls tools over the same loopback MCP endpoint with an `X-HK-Attest` header the per-process
attestor signs for this subject, session and turn.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.security.attestation import Attestor


async def call_trusted(
    *,
    url: str,
    attestor: Attestor,
    token: str,
    sub: str,
    session_id: str,
    turn_id: str,
    correlation_id: str,
    tool: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-HK-Turn-Id": turn_id,
        "X-HK-Session-Id": session_id,
        "X-Correlation-Id": correlation_id,
        "X-HK-Attest": attestor.sign(sub, session_id, turn_id),
    }
    async with (
        httpx.AsyncClient(headers=headers, timeout=15) as http,
        streamable_http_client(url, http_client=http) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(tool, arguments)
    if result.structuredContent is not None:
        content = result.structuredContent
        return content.get("result", content) if set(content) == {"result"} else content
    return json.loads(result.content[0].text)
