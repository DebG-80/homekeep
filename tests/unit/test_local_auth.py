from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.main import create_app
from app.security.local_issuer import LOCAL_CLIENT_ID, LocalIssuer
from app.security.tokens import SCOPE_MCP, AccessTokenVerifier, StaticJwks

LOCAL = {"ENV": "local", "DYNAMODB_ENDPOINT_URL": "http://localhost:8001"}


def test_p2_2_local_token_routes_exist_only_in_local_env(
    demo_env: dict[str, str], issuer: LocalIssuer
) -> None:
    with TestClient(create_app(Settings.from_env(LOCAL), issuer=issuer)) as client:
        minted = client.post("/local/token", json={"identity": "a_owner"})
        assert minted.status_code == 200
        jwks = client.get("/local/jwks.json").json()
        verifier = AccessTokenVerifier(issuer.issuer, [LOCAL_CLIENT_ID], StaticJwks(jwks))
        assert verifier.verify(minted.json()["access_token"], SCOPE_MCP).sub == "local-a_owner"
        assert client.post("/local/token", json={"identity": "nobody"}).status_code == 404

    for env in ("test", "demo"):
        settings = Settings.from_env({**demo_env, "ENV": env})
        with TestClient(create_app(settings)) as client:
            assert client.post("/local/token", json={"identity": "a_owner"}).status_code == 404
            assert client.get("/local/jwks.json").status_code == 404
        with pytest.raises(ConfigError, match="only when ENV=local"):
            create_app(settings, issuer=issuer)  # the local issuer can never be injected there
