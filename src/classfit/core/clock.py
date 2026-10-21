"""날짜의 원천. 오늘은 Asia/Seoul 기준이고 UTC 15:00 이 날짜 경계다(Design 5절 15).

`app/deps.py` 의 `Today` 가 여기서 받고, 시험은 dependency_overrides 로 주입한다.
상태 판정 함수는 오늘을 인자로 받는다(스스로 시계를 읽지 않는다).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def today_kst(now: datetime | None = None) -> date:
    """now(시간대 있는 시각, 없으면 지금)의 KST 날짜. 시간대 없는 시각은 ValueError."""
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        raise ValueError("시간대 없는 시각은 받지 않는다")
    return now.astimezone(KST).date()
