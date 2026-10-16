from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.clock import FixedClock
from app.domain.errors import DomainError
from app.store.table import Table
from tests.unit.domain.world import HH_A, HH_B, World, put_household


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 16, 4, 30, tzinfo=UTC))


@pytest.fixture
def world(table: Table, clock: FixedClock) -> World:
    """Households A and B, both with storage consent granted."""
    put_household(table, HH_A)
    put_household(table, HH_B)
    return World(table, clock)


@pytest.fixture
def expect_error() -> Callable[..., DomainError]:
    def _expect(
        code: str, reason: str | None, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> DomainError:
        with pytest.raises(DomainError) as caught:
            fn(*args, **kwargs)
        assert caught.value.code.value == code, caught.value
        if reason is not None:
            assert caught.value.reason == reason, caught.value
        return caught.value

    return _expect
