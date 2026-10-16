from __future__ import annotations

from datetime import UTC, datetime

from app.channel.pipeline import local_prompt_time
from app.orchestrator.prompt import build_system_prompt


def test_inv10_prompt_uses_household_local_date_and_time() -> None:
    # 20:00 UTC is 01:30 the next day in Asia/Kolkata: date and time must agree.
    local_date, local_time = local_prompt_time(datetime(2026, 10, 20, 20, 0, tzinfo=UTC))
    assert (local_date, local_time) == ("2026-10-21", "01:30")
    assert "2026-10-21 01:30 (Asia/Kolkata)" in build_system_prompt(local_date, local_time)
