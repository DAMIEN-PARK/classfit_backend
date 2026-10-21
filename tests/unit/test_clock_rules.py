"""오늘의 원천(core/clock.py): KST 날짜, UTC 15:00 경계. DB 없음."""

from datetime import UTC, date, datetime

import pytest

from classfit.core.clock import today_kst


def test_today_kst_boundary_utc_15() -> None:
    assert today_kst(datetime(2026, 10, 22, 14, 59, 59, 999999, tzinfo=UTC)) == date(2026, 10, 22)
    assert today_kst(datetime(2026, 10, 22, 15, 0, tzinfo=UTC)) == date(2026, 10, 23)
    assert today_kst(datetime(2026, 12, 31, 15, 0, tzinfo=UTC)) == date(2027, 1, 1)  # 해 넘김
    with pytest.raises(ValueError):
        today_kst(datetime(2026, 10, 22, 15, 0))  # 시간대 없는 시각은 받지 않는다
