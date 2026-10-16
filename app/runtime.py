"""Process-wide collaborators shared by the MCP server and (Slice 2b) the channel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.domain.clock import Clock
from app.security.attestation import Attestor
from app.security.local_issuer import LocalIssuer
from app.security.tokens import AccessTokenVerifier
from app.store.table import Table


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    table: Table
    clock: Clock
    verifier: AccessTokenVerifier
    attestor: Attestor
    local_issuer: LocalIssuer | None = None
    model_factory: Callable[[], Any] | None = None  # a Strands Model per turn
