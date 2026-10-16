"""Cognito access-token verification (TDD §4.2 T1, §5.2; contract §5.5).

Only RS256 access tokens from the configured issuer and app clients are accepted, and only if
they carry the scope the route needs. Every failure is AUTH_DENIED with a reason; the token
itself is never logged or echoed.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import jwt

from app.config import Settings
from app.domain.errors import DomainError, ErrorCode

SCOPE_API = "homekeep/api"
SCOPE_MCP = "homekeep/mcp"
_ALGORITHM = "RS256"


def _deny(reason: str) -> DomainError:
    return DomainError(ErrorCode.AUTH_DENIED, reason)


class JwksSource(Protocol):
    def signing_key(self, kid: str) -> Any: ...


class StaticJwks:
    """A fixed key set: the local test issuer's JWKS (G1-5)."""

    def __init__(self, jwks: Mapping[str, Any]) -> None:
        self._keys = {key.key_id: key for key in jwt.PyJWKSet.from_dict(dict(jwks)).keys}

    def signing_key(self, kid: str) -> Any:
        if kid not in self._keys:
            raise _deny("UNKNOWN_KEY")
        return self._keys[kid].key


class RemoteJwks:
    """Cognito's JWKS, fetched on first use and cached by PyJWT."""

    def __init__(self, url: str, timeout_seconds: int = 3) -> None:
        # A short timeout: a slow JWKS fetch must not eat the 20 s turn budget (G2-7).
        self._client = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=timeout_seconds)

    def signing_key(self, kid: str) -> Any:
        try:
            return self._client.get_signing_key(kid).key
        except jwt.PyJWKClientConnectionError as exc:
            raise _deny("JWKS_UNAVAILABLE") from exc  # an outage, not a bad token
        except jwt.PyJWKClientError as exc:
            raise _deny("UNKNOWN_KEY") from exc


@dataclass(frozen=True)
class VerifiedToken:
    sub: str
    client_id: str
    scopes: frozenset[str]
    groups: frozenset[str]


class AccessTokenVerifier:
    def __init__(
        self,
        issuer: str,
        allowed_client_ids: Collection[str],
        jwks: JwksSource,
        leeway_seconds: int = 30,
    ) -> None:
        self.issuer = issuer
        self.allowed_client_ids = frozenset(allowed_client_ids)
        self._jwks = jwks
        self._leeway = leeway_seconds

    @classmethod
    def for_cognito(cls, settings: Settings) -> AccessTokenVerifier:
        if not (settings.cognito_issuer and settings.cognito_jwks_url):
            raise ValueError("COGNITO_USER_POOL_ID is not configured")
        clients = [c for c in (settings.cognito_web_client_id, settings.cognito_mcp_client_id) if c]
        return cls(settings.cognito_issuer, clients, RemoteJwks(settings.cognito_jwks_url))

    def verify(self, token: str, required_scope: str | None) -> VerifiedToken:
        """`required_scope=None` skips the scope check; the MCP transport checks scope itself so a
        valid token without `homekeep/mcp` gets 403 insufficient_scope rather than 401."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise _deny("MALFORMED_TOKEN") from exc
        if header.get("alg") != _ALGORITHM:
            raise _deny("UNSUPPORTED_ALGORITHM")
        kid = header.get("kid")
        if not kid:
            raise _deny("UNKNOWN_KEY")
        key = self._jwks.signing_key(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[_ALGORITHM],
                issuer=self.issuer,
                leeway=self._leeway,
                # Cognito access tokens carry no `aud`; client_id is checked below instead.
                options={
                    "require": ["exp", "iat", "iss", "sub", "token_use", "client_id"],
                    "verify_aud": False,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise _deny("TOKEN_EXPIRED") from exc
        except jwt.InvalidIssuerError as exc:
            raise _deny("WRONG_ISSUER") from exc
        except jwt.PyJWTError as exc:
            raise _deny("INVALID_TOKEN") from exc

        if claims["token_use"] != "access":  # noqa: S105 (a JWT claim value, not a password)
            raise _deny("WRONG_TOKEN_USE")
        if claims["client_id"] not in self.allowed_client_ids:
            raise _deny("UNKNOWN_CLIENT")
        scopes = frozenset(str(claims.get("scope", "")).split())
        if required_scope is not None and required_scope not in scopes:
            raise _deny("MISSING_SCOPE")
        groups = claims.get("cognito:groups") or []
        return VerifiedToken(
            sub=str(claims["sub"]),
            client_id=str(claims["client_id"]),
            scopes=scopes,
            groups=frozenset(str(g) for g in groups),
        )
