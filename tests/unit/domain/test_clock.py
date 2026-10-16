from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.domain.clock import (
    FixedClock,
    SystemClock,
    clock_from_settings,
    iso_utc,
    local_date,
    next_local_midnight,
)


def test_inv10_utc_storage_and_kolkata_midnight_rollover() -> None:
    kolkata = ZoneInfo("Asia/Kolkata")
    # Stored text is UTC whatever zone the instant arrives in.
    assert iso_utc(datetime(2026, 10, 21, 0, 0, tzinfo=kolkata)) == "2026-10-20T18:30:00.000000Z"

    # 23:59 in Kolkata is still the 20th; one minute later the household date rolls over.
    before = datetime(2026, 10, 20, 18, 29, tzinfo=UTC)
    after = before + timedelta(minutes=1)
    assert local_date(before) == date(2026, 10, 20)
    assert local_date(after) == date(2026, 10, 21)
    assert next_local_midnight(before) == datetime(2026, 10, 20, 18, 30, tzinfo=UTC)
    assert next_local_midnight(after) == datetime(2026, 10, 21, 18, 30, tzinfo=UTC)

    clock = FixedClock(datetime(2026, 10, 20, 23, 59, tzinfo=kolkata))
    assert clock.now() == before
    assert clock.now().tzinfo is UTC
    clock.advance(timedelta(minutes=1))
    assert local_date(clock.now()) == date(2026, 10, 21)

    assert SystemClock().now().tzinfo is UTC
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 10, 20, 12, 0))  # noqa: DTZ001 (deliberately naive)


def test_inv10_clock_override_drives_the_clock() -> None:
    override = Settings.from_env(
        {
            "ENV": "local",
            "DYNAMODB_ENDPOINT_URL": "http://x",
            "CLOCK_OVERRIDE": "2026-10-20T18:29:00Z",
        }
    )
    assert clock_from_settings(override).now() == datetime(2026, 10, 20, 18, 29, tzinfo=UTC)
    plain = Settings.from_env({"ENV": "local", "DYNAMODB_ENDPOINT_URL": "http://x"})
    assert isinstance(clock_from_settings(plain), SystemClock)
