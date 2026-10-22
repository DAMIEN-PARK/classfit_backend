"""일정 규칙. 시안 관리자.html 의 일정 함수(656~678줄, scSlotTimes·scSlots 는 T5)를 그대로 옮긴 순수 함수다.

golden(tests/fixtures/golden.json, scripts/golden/extract.mjs)이 시안 값과 같은지 잰다.
시각은 datetime.time 으로 받고, session_time 은 시안처럼 "HH:MM" 글자를 돌려준다.
일차·세션은 칸 이름만 맞으면 된다(DayHours·SessionSlot). ORM 행을 그대로 넘겨도 된다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Protocol

SLOT_MIN = 50  # 시안 656 SC_SLOT: 교시 길이(분) 기본값
BREAK_MIN = 10  # 시안 656 SC_BREAK: 휴식(분) 기본값
MAKE_DAYS_GUARD = 60  # 시안 675: 달력 날을 60일까지만 본다
_NO_SLOT = 99  # 시안 672: slot 이 없으면 맨 뒤
SLOT_TIMES_MAX = 60  # 시안 677: 하루 교시를 60개까지만 만든다


@dataclass(frozen=True)
class PlannedDay:
    """make_days 가 만든 일차 하나."""

    no: int
    date: date
    start_time: time
    end_time: time


class DayHours(Protocol):
    start_time: time
    end_time: time
    lunch_start: time | None
    lunch_end: time | None


class SessionSlot(Protocol):
    id: int
    day_no: int | None
    slot: int | None
    minutes: int | None
    time_start: time | None
    time_end: time | None


def _hm(t: time) -> int:
    """시안 658 scHm: 하루 시작부터의 분."""
    return t.hour * 60 + t.minute


def _m2(m: int) -> str:
    """시안 659 scM2: 분 → "HH:MM"."""
    return f"{m // 60:02d}:{m % 60:02d}"


def _lunch(day: DayHours) -> tuple[int, int] | None:
    """시안 663 scLunch: 그날 시간과 겹치는 점심 (시작, 끝) 분. 없거나 겹치지 않으면 None."""
    if day.lunch_start is None or day.lunch_end is None:
        return None
    a, b = _hm(day.lunch_start), _hm(day.lunch_end)
    overlap = min(b, _hm(day.end_time)) - max(a, _hm(day.start_time))
    return (a, b) if b > a and overlap > 0 else None


def _skip_lunch(day: DayHours, st: int, length: int) -> int:
    """시안 664 scSkip: [st, st+length) 가 점심에 걸리면 점심 끝으로 민다."""
    lunch = _lunch(day)
    if lunch is not None and st < lunch[1] and st + length > lunch[0]:
        return lunch[1]
    return st


def make_days(
    start: date, n: int, start_time: time, end_time: time
) -> list[PlannedDay]:
    """시안 675 scMakeDays: start 부터 토·일을 건너뛰고 평일 n 개를 1..n 일차로 만든다.

    달력 날을 MAKE_DAYS_GUARD(60)일까지만 보므로 n 이 크면 그 안의 평일까지만 나온다.
    """
    out: list[PlannedDay] = []
    d = start
    for _ in range(MAKE_DAYS_GUARD):
        if len(out) >= n:
            break
        if d.weekday() < 5:
            out.append(PlannedDay(len(out) + 1, d, start_time, end_time))
        d += timedelta(days=1)
    return out


def session_time(
    day: DayHours | None,
    slot_min: int | None,
    break_min: int | None,
    siblings: Iterable[SessionSlot],
    target: SessionSlot,
) -> tuple[str, str] | None:
    """시안 665 scTime: 세션의 (시작, 끝) "HH:MM". 일차가 없거나 slot 이 없으면 None.

    - 예외 시각(time_start·time_end)이 있으면 그 값이 먼저다. 일차가 없어도 그렇다.
    - day 는 target 의 일차, siblings 는 target 이 든 섹션의 세션이다(일차는 여기서 거른다).
      siblings 에 target 이 없으면 target 하나만 놓는다(시안의 섹션 없음).
    - 같은 일차의 예외 시각 없는 세션을 slot 순(시안 672 scBySlot, 같은 slot 은 id 순)으로 놓고
      "앞 세션 끝 + 휴식" 에서 시작한다. 길이는 minutes(양수일 때), 아니면 교시 길이다.
      점심에 걸리면 점심 뒤로 밀고(scSkip), 끝은 그날 끝에서 자른다.
    - 시안 665 끝의 교시 번호 계산 줄은 target 이 늘 목록에 있어 닿지 않으므로 옮기지 않았다.
    """
    if target.time_start is not None:
        return _m2(_hm(target.time_start)), _m2(_hm(target.time_end))
    if day is None or not target.slot:
        return None
    sm = slot_min or SLOT_MIN
    bm = BREAK_MIN if break_min is None else break_min
    same_day = [
        x for x in siblings if x.day_no == target.day_no and x.time_start is None
    ]
    if not any(x.id == target.id for x in same_day):
        same_day = [target]
    same_day.sort(key=lambda x: (x.slot or _NO_SLOT, x.id))
    day_end = _hm(day.end_time)
    cur = _hm(day.start_time)
    for x in same_day:
        length = x.minutes if x.minutes and x.minutes > 0 else sm
        st = _skip_lunch(day, cur, length)
        en = st + length
        if x.id == target.id:
            return _m2(st), _m2(min(en, day_end))
        cur = en + bm
    raise AssertionError("target 은 same_day 에 있다")


def slot_times(
    day: DayHours, slot_min: int | None, break_min: int | None
) -> list[tuple[str, str]]:
    """시안 677 scSlotTimes: 그날 교시 시간표 [(시작, 끝) "HH:MM"].

    그날 시작부터 「교시 + 휴식」을 반복하고, 점심에 걸리는 교시는 점심 뒤로 민다(scSkip). 끝을 넘는 교시는 만들지 않고,
    SLOT_TIMES_MAX(60)개에서 멈춘다. 교시가 0 이하·None 이면 SLOT_MIN, 휴식이 None 이면 BREAK_MIN 이다.
    """
    bm = BREAK_MIN if break_min is None else break_min
    sm = slot_min if slot_min is not None and slot_min > 0 else SLOT_MIN
    end = _hm(day.end_time)
    cur = _hm(day.start_time)
    out: list[tuple[str, str]] = []
    while len(out) < SLOT_TIMES_MAX:
        st = _skip_lunch(day, cur, sm)
        if st + sm > end:
            break
        out.append((_m2(st), _m2(st + sm)))
        cur = st + sm + bm
    return out


def slot_count(day: DayHours, slot_min: int | None, break_min: int | None) -> int:
    """시안 678 scSlots: 하루 교시 수. 하나도 안 들어가도 1 이다."""
    return max(1, len(slot_times(day, slot_min, break_min)))


def _first_free(capacity: int, used: set[int]) -> int:
    """시안 667 scNextSlot 의 안쪽: 1..capacity 중 안 쓴 첫 교시, 없으면 0."""
    for slot in range(1, capacity + 1):
        if slot not in used:
            return slot
    return 0


def place_in_free_slots(
    capacity: Mapping[int, int],
    used: Mapping[int, set[int]],
    start_day: int | None,
    n: int,
) -> list[tuple[int, int] | None]:
    """고른 n 개를 차례로 (일차, 교시)에 놓는다(시안 :1840-1842 pmgo 가 scNextSlot 을 고른 수만큼 돈다).

    capacity 는 일차 → 하루 교시 수(slot_count), used 는 일차 → 이미 쓴 교시다(그 섹션만).
    start_day 부터 일차 오름차순으로 빈 교시를 채우고 그날이 차면 다음 일차로 간다. 일차가 모자라면 None(일차 미정).
    start_day 가 None 이면 전부 None 이다. capacity 에 없는 start_day 는 ValueError(service 가 409 로 먼저 막는다).
    """
    if start_day is None:
        return [None] * n
    if start_day not in capacity:
        raise ValueError(f"그 강의에 {start_day}일차가 없다")
    days = sorted(capacity)
    taken = {d: set(used.get(d, ())) for d in days}
    di = days.index(start_day)
    out: list[tuple[int, int] | None] = []
    for _ in range(n):
        while di < len(days) and not _first_free(capacity[days[di]], taken[days[di]]):
            di += 1
        if di == len(days):
            out.append(None)
            continue
        day = days[di]
        slot = _first_free(capacity[day], taken[day])
        taken[day].add(slot)
        out.append((day, slot))
    return out
