from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.security.local_issuer import LocalIssuer
from app.store.table import Table
from scripts import seed
from tests.contract.live import LiveServer, serve


@pytest.fixture
def live(table: Table, issuer: LocalIssuer) -> Iterator[LiveServer]:
    """A live server over the seeded fixtures (Household A has consent and a verified AC)."""
    seed.seed_local(table)
    with serve(table, issuer) as server:
        yield server
