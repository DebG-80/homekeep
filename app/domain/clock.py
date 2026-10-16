"""The injected clock (TDD §4.5) and household-time helpers (CLAUDE.md invariant 10).

Times are stored in UTC and presented in the household timezone (default Asia/Kolkata).
CLOCK_OVERRIDE gives a fixed clock in local and test only; config refuses it in demo (P1-3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.config import Settings

DEFAULT_TIMEZONE = "Asia/Kolkata"


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass
class FixedClock:
    instant: datetime = field()

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware instant")
        self.instant = self.instant.astimezone(UTC)

    def now(self) -> datetime:
        return self.instant

    def advance(self, delta: timedelta) -> None:
        self.instant += delta


def clock_from_settings(settings: Settings) -> Clock:
    return FixedClock(settings.clock_override) if settings.clock_override else SystemClock()


def iso_utc(moment: datetime) -> str:
    """Fixed-width UTC text, so timestamps in sort keys order correctly."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def local_date(moment: datetime, timezone: str = DEFAULT_TIMEZONE) -> date:
    return moment.astimezone(ZoneInfo(timezone)).date()


def next_local_midnight(moment: datetime, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """The next 00:00 in the household timezone, returned in UTC (date rollover, AT-34)."""
    zone = ZoneInfo(timezone)
    tomorrow = local_date(moment, timezone) + timedelta(days=1)
    return datetime.combine(tomorrow, time(0, 0), tzinfo=zone).astimezone(UTC)
