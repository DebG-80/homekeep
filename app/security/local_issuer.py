"""A local RS256 token issuer shaped like Cognito's access tokens (G1-5).

Used by tests in Slice 1. Slice 2 may serve it for ENV=local only; it must never be reachable
when ENV=demo. The private key exists only in this process's memory.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

LOCAL_ISSUER = "https://local-issuer.homekeep.invalid"
LOCAL_CLIENT_ID = "homekeep-local"


class LocalIssuer:
    def __init__(self, issuer: str = LOCAL_ISSUER, kid: str = "local-1") -> None:
        self.issuer = issuer
        self.kid = kid
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @property
    def jwks(self) -> dict[str, Any]:
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._private_key.public_key()))
        return {"keys": [{**public, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def mint(
        self,
        sub: str,
        *,
        client_id: str,
        scopes: Iterable[str],
        groups: Iterable[str] = (),
        token_use: str = "access",  # noqa: S107 (a JWT claim value, not a password)
        issuer: str | None = None,
        now: datetime | None = None,
        expires_in: timedelta = timedelta(hours=1),
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        issued = now or datetime.now(UTC)
        claims: dict[str, Any] = {
            "sub": sub,
            "iss": issuer or self.issuer,
            "client_id": client_id,
            "token_use": token_use,
            "scope": " ".join(scopes),
            "iat": int(issued.timestamp()),
            "exp": int((issued + expires_in).timestamp()),
        }
        if groups:
            claims["cognito:groups"] = list(groups)
        claims.update(extra_claims or {})
        return jwt.encode(claims, self._private_key, algorithm="RS256", headers={"kid": self.kid})
