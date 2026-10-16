"""Local sign-in for `make run` (P2-2). Mounted only when ENV=local; never on AWS.

`POST /local/token {"identity": "a_owner"}` mints a token for a seeded fixture identity, whose
subject matches the local seed (`local-<key>`). `GET /local/jwks.json` publishes the public key.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.security.local_issuer import LOCAL_CLIENT_ID, LocalIssuer
from app.security.tokens import SCOPE_API, SCOPE_MCP

IDENTITIES = Path(__file__).resolve().parents[1] / "fixtures" / "identities.json"


@cache
def _identities() -> dict[str, dict[str, Any]]:
    data = json.loads(IDENTITIES.read_text(encoding="utf-8"))
    return {identity["key"]: identity for identity in data["identities"]}


class TokenRequest(BaseModel):
    identity: str


def router(issuer: LocalIssuer) -> APIRouter:
    routes = APIRouter(prefix="/local", tags=["local"])

    @routes.post("/token")
    def mint_token(request: TokenRequest) -> dict[str, Any]:
        identity = _identities().get(request.identity)
        if identity is None:
            raise HTTPException(status_code=404, detail="unknown fixture identity")
        token = issuer.mint(
            f"local-{identity['key']}",
            client_id=LOCAL_CLIENT_ID,
            scopes=["openid", SCOPE_API, SCOPE_MCP],
            groups=identity.get("groups", []),
        )
        return {"access_token": token, "token_type": "Bearer", "expires_in": 3600}

    @routes.get("/jwks.json")
    def jwks() -> dict[str, Any]:
        return issuer.jwks

    return routes
