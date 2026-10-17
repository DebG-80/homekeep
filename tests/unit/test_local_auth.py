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


def test_g4_7_fake_model_script_only_with_local_fake_model(
    demo_env: dict[str, str], issuer: LocalIssuer
) -> None:
    from app.orchestrator.fake_model import ScriptedModel

    app = create_app(Settings.from_env(LOCAL), issuer=issuer, start_sweep=False)
    with TestClient(app) as client:
        queued = client.post(
            "/local/fake-model/script",
            json={"turns": [[{"call": "get_context", "input": {}}, {"say": "Scripted hello."}]]},
        )
        assert queued.status_code == 200
        assert queued.json() == {"queued": 1}
        bad = client.post("/local/fake-model/script", json={"turns": [[{"shout": "x"}]]})
        assert bad.status_code == 422
    factory = app.state.runtime.model_factory
    scripted = factory()
    assert isinstance(scripted, ScriptedModel)
    assert factory() is not scripted  # the queue is drained; the default model follows

    bedrock = Settings.from_env({**LOCAL, "MODEL_PROVIDER": "bedrock"})
    with TestClient(create_app(bedrock, issuer=issuer, start_sweep=False)) as client:
        assert client.post("/local/fake-model/script", json={"turns": []}).status_code == 404
    with TestClient(create_app(Settings.from_env(demo_env), start_sweep=False)) as client:
        assert client.post("/local/fake-model/script", json={"turns": []}).status_code == 404
