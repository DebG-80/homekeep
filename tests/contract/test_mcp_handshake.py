from __future__ import annotations

import anyio

from tests.contract.live import LiveServer, mcp_session


def test_dd1_initialize_negotiates_2025_11_25_over_streamable_http(live: LiveServer) -> None:
    async def run() -> tuple[str, str, list[str]]:
        async with mcp_session(live.mcp_url, live.token()) as (session, initialized):
            tools = await session.list_tools()
            return (
                initialized.protocolVersion,
                initialized.serverInfo.name,
                [t.name for t in tools.tools],
            )

    version, server_name, tools = anyio.run(run)
    assert version == "2025-11-25"  # the Alexa+ track's spec version (TDD §2, §5.1)
    assert server_name == "HomeKeep"
    assert "get_context" in tools
