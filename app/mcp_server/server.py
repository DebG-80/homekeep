"""Builds the FastMCP server and its Starlette app (TDD §5.1, §5.2).

Stateless Streamable HTTP with JSON responses (no session affinity behind the ALB). FastMCP acts
as the OAuth resource server: bearer check, 401 with `resource_metadata`, 403 on missing scope,
and Protected Resource Metadata. Public URLs come from APP_BASE_URL only (G2-9).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Route

from app.mcp_server import tools, trusted
from app.runtime import Runtime
from app.security.tokens import SCOPE_MCP
from app.security.verifier import McpTokenVerifier

PRM_PATH = "/.well-known/oauth-protected-resource"
INSTRUCTIONS = (
    "HomeKeep helps elders in Indian households with appliance problems. Tools act only on the "
    "signed-in household. Service bookings are a demonstration; no real technician visits."
)


def build_mcp(runtime: Runtime) -> FastMCP:
    settings = runtime.settings
    if not settings.app_base_url:  # required in test/demo, defaulted in local
        raise ValueError("APP_BASE_URL is not configured")
    resource = f"{settings.app_base_url}/mcp"
    public_host = urlsplit(settings.app_base_url).netloc
    mcp = FastMCP(
        "HomeKeep",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        token_verifier=McpTokenVerifier(runtime.verifier),
        auth=AuthSettings(
            issuer_url=runtime.verifier.issuer,
            resource_server_url=resource,
            required_scopes=[SCOPE_MCP],
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_host, "127.0.0.1:*", "localhost:*"],
            allowed_origins=list(settings.allowed_origins),
        ),
    )
    tools.register(mcp, runtime)
    trusted.register(mcp, runtime)
    return mcp


def build_mcp_app(mcp: FastMCP) -> Starlette:
    app = mcp.streamable_http_app()
    # G2-2: serve the metadata at TDD §5.2's root path too, alongside RFC 9728's suffixed path.
    suffixed = next(r for r in app.routes if isinstance(r, Route) and r.path.startswith(PRM_PATH))
    app.router.routes.append(
        Route(PRM_PATH, endpoint=suffixed.endpoint, methods=["GET", "OPTIONS"])
    )
    return app
