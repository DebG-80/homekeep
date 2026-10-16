from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from app.domain.errors import DomainError, ErrorCode
from app.security.local_issuer import LocalIssuer
from app.security.tokens import SCOPE_API, SCOPE_MCP, AccessTokenVerifier, StaticJwks

WEB = "web-client"
MCP = "mcp-inspector-client"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _hs256(claims: dict[str, object], secret: bytes, kid: str) -> str:
    """Hand-built HS256 JWT; PyJWT itself refuses to HMAC with an asymmetric key."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid}).encode())
    payload = _b64(json.dumps(claims).encode())
    signature = hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


@pytest.fixture
def verifier(issuer: LocalIssuer) -> AccessTokenVerifier:
    return AccessTokenVerifier(issuer.issuer, [WEB, MCP], StaticJwks(issuer.jwks))


def test_nfr04_valid_access_token_accepted(
    issuer: LocalIssuer, verifier: AccessTokenVerifier
) -> None:
    token = issuer.mint("sub-1", client_id=WEB, scopes=["openid", SCOPE_API, SCOPE_MCP])
    verified = verifier.verify(token, SCOPE_API)
    assert (verified.sub, verified.client_id) == ("sub-1", WEB)
    assert verified.scopes == {"openid", SCOPE_API, SCOPE_MCP}

    staff = issuer.mint("sub-2", client_id=MCP, scopes=[SCOPE_MCP], groups=["technician"])
    assert verifier.verify(staff, SCOPE_MCP).groups == {"technician"}


@pytest.mark.parametrize(
    ("mint_kwargs", "required", "reason"),
    [
        (
            {"issuer": "https://cognito-idp.us-east-1.amazonaws.com/other"},
            SCOPE_API,
            "WRONG_ISSUER",
        ),
        ({"now": datetime.now(UTC) - timedelta(hours=2)}, SCOPE_API, "TOKEN_EXPIRED"),
        ({"token_use": "id"}, SCOPE_API, "WRONG_TOKEN_USE"),
        ({"client_id": "someone-elses-client"}, SCOPE_API, "UNKNOWN_CLIENT"),
        ({"scopes": [SCOPE_API]}, SCOPE_MCP, "MISSING_SCOPE"),
    ],
    ids=["bad-issuer", "expired", "id-token", "wrong-client", "missing-scope"],
)
def test_nfr04_rejects_bad_issuer_expired_id_token_wrong_client_missing_scope(
    issuer: LocalIssuer,
    verifier: AccessTokenVerifier,
    mint_kwargs: dict[str, object],
    required: str,
    reason: str,
) -> None:
    kwargs: dict[str, object] = {"client_id": WEB, "scopes": [SCOPE_API, SCOPE_MCP], **mint_kwargs}
    token = issuer.mint("sub-1", **kwargs)  # type: ignore[arg-type]
    with pytest.raises(DomainError) as caught:
        verifier.verify(token, required)
    assert (caught.value.code, caught.value.reason) == (ErrorCode.AUTH_DENIED, reason)


def test_nfr04_rejects_none_and_hs256_algorithms(
    issuer: LocalIssuer, verifier: AccessTokenVerifier
) -> None:
    now = datetime.now(UTC)
    claims = {
        "sub": "sub-1",
        "iss": issuer.issuer,
        "client_id": WEB,
        "token_use": "access",
        "scope": SCOPE_API,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    unsigned = jwt.encode(claims, key="", algorithm="none", headers={"kid": issuer.kid})
    # Classic key confusion: HMAC "signed" with the issuer's public key as the secret.
    public_pem = jwt.PyJWK(issuer.jwks["keys"][0]).key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    hmac_token = _hs256(claims, public_pem, issuer.kid)

    for token in (unsigned, hmac_token):
        with pytest.raises(DomainError) as caught:
            verifier.verify(token, SCOPE_API)
        assert caught.value.reason == "UNSUPPORTED_ALGORITHM"

    # A well-formed RS256 token signed by a different key is rejected on the signature.
    impostor = LocalIssuer(issuer=issuer.issuer, kid=issuer.kid)
    with pytest.raises(DomainError) as caught:
        verifier.verify(impostor.mint("sub-1", client_id=WEB, scopes=[SCOPE_API]), SCOPE_API)
    assert caught.value.reason == "INVALID_TOKEN"
    for garbage in ("", "not-a-jwt", "a.b.c"):
        with pytest.raises(DomainError):
            verifier.verify(garbage, SCOPE_API)
