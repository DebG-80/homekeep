from __future__ import annotations

import boto3
import boto3.session
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _no_aws(*args: object, **kwargs: object) -> None:
    raise AssertionError("/healthz must not create an AWS client")


def test_healthz_returns_ok_without_aws_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    for target, name in (
        (boto3, "client"),
        (boto3, "resource"),
        (boto3.session.Session, "client"),
        (boto3.session.Session, "resource"),
    ):
        monkeypatch.setattr(target, name, _no_aws)
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8001")

    # The context manager runs the lifespan, so this also loads settings from the environment.
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
