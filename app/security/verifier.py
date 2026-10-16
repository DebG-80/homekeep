"""Which token issuer the app trusts, and the adapter FastMCP's auth middleware calls.

ENV=local trusts the in-memory local issuer (P2-2); test and demo trust Cognito only, and the
local issuer can never be injected there.
"""

from __future__ import annotations

import anyio
from mcp.server.auth.provider import AccessToken

from app.config import ConfigError, Settings
from app.domain.errors import DomainError
from app.security.local_issuer import LOCAL_CLIENT_ID, LocalIssuer
from app.security.tokens import AccessTokenVerifier, StaticJwks, VerifiedToken


def build_token_verifier(
    settings: Settings, local_issuer: LocalIssuer | None
) -> AccessTokenVerifier:
    if settings.env == "local":
        if local_issuer is None:
            raise ConfigError("ENV=local needs the local token issuer")
        return AccessTokenVerifier(
            local_issuer.issuer, [LOCAL_CLIENT_ID], StaticJwks(local_issuer.jwks)
        )
    if local_issuer is not None:
        raise ConfigError("the local token issuer is allowed only when ENV=local")
    return AccessTokenVerifier.for_cognito(settings)


class McpTokenVerifier:
    """FastMCP `TokenVerifier`: None means 401. Scope is checked by FastMCP itself (403)."""

    def __init__(self, verifier: AccessTokenVerifier) -> None:
        self._verifier = verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            verified = await anyio.to_thread.run_sync(self._verifier.verify, token, None)
        except DomainError:
            return None
        return AccessToken(
            token=token,
            client_id=verified.client_id,
            scopes=sorted(verified.scopes),
            subject=verified.sub,
            claims={"groups": sorted(verified.groups)},
        )


def verified_from(access: AccessToken) -> VerifiedToken:
    claims = access.claims or {}
    return VerifiedToken(
        sub=access.subject or "",
        client_id=access.client_id,
        scopes=frozenset(access.scopes),
        groups=frozenset(claims.get("groups", [])),
    )
