"""교육 기록의 상태 전이와 계획 값(T7 결정 iii·vi). 순수 함수다 — DB·crud·models 를 부르지 않는다
(tests/unit/test_import_rules.py).

- 상태는 none(행 없음) · done(기록됨) · ok(관리자 확인)다. 강사 저장은 none → done, 바뀐 칸이 있으면 done·ok → done,
  바뀐 칸이 없으면 그대로다(R1~R4). 관리자 저장은 늘 ok 다(R5). 확인은 done·ok → ok, none 이면 RecordRejected(R6~R8).
- 바뀐 칸은 저장 본문 여섯 칸(RecordFields)을 지금 행과 견준 이름 목록이다. 없던 기록은 여섯 칸 전부다.
- 계획 값(계획대로 기록): 실시일 = 일차 날짜 · 시작·끝 = 일정표 시각(rules.schedule.session_time 의 "HH:MM") ·
  진행 내용 = 다듬은 설명이 비지 않으면 그것, 아니면 제목 · 참석 = 등록 수 · 비고 없음.
  일정표는 끝을 그날 끝에서 자르고 시작은 자르지 않아, 시작이 끝보다 늦거나 24시를 넘으면 실제 시각을 정할 수 없어 둘 다 None 이다.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, time
from typing import Literal

ActorKind = Literal["instructor", "admin"]


@dataclass(frozen=True)
class RecordFields:
    """저장 본문 여섯 칸. 끝점이 본문으로 만들고, service 가 dataclasses.asdict 로 crud 에 넘긴다."""

    held_on: date
    start_time: time | None
    end_time: time | None
    attendees: int | None
    content: str
    note: str | None


class RecordRejected(ValueError):
    """확인할 기록이 없다(none). service 가 Conflict(409)로 바꾼다."""

    reason = "no_record"


def after_save(current: str, by: ActorKind, changed: bool) -> str:
    """저장 뒤 상태. current 는 none·done·ok, changed 는 바뀐 칸이 있는지."""
    if by == "admin":
        return "ok"
    if current == "none" or changed:
        return "done"
    return current


def after_confirm(current: str) -> str:
    """확인 뒤 상태. none 이면 RecordRejected. ok 는 그대로 ok 다(멱등)."""
    if current == "none":
        raise RecordRejected("확인할 기록이 없습니다")
    return "ok"


def changed_fields(current: RecordFields | None, new: RecordFields) -> list[str]:
    """new 가 current 와 다른 칸 이름(RecordFields 칸 순서). current 가 None(기록 없음)이면 여섯 칸 전부."""
    return [
        f.name
        for f in fields(new)
        if current is None or getattr(current, f.name) != getattr(new, f.name)
    ]


def _clock(hm: str) -> time | None:
    """일정표의 "HH:MM". 24시 이상이면 None(그날 안의 시각이 아니다)."""
    hours, minutes = (int(part) for part in hm.split(":"))
    return time(hours, minutes) if hours < 24 else None


def plan_fields(
    *,
    day_date: date,
    times: tuple[str, str] | None,
    title: str,
    description: str | None,
    enrolled: int,
) -> RecordFields:
    """계획대로 기록할 값(결정 vi). times 는 rules.schedule.session_time 의 결과다."""
    start = end = None
    if times is not None:
        start, end = _clock(times[0]), _clock(times[1])
        if start is None or end is None or start >= end:
            start = end = None
    content = (description or "").strip() or title
    return RecordFields(
        held_on=day_date,
        start_time=start,
        end_time=end,
        attendees=enrolled,
        content=content,
        note=None,
    )


def is_past(day_date: date | None, today: date) -> bool:
    """지난 일차(날짜 ≤ 오늘)인가. 일차가 없으면(None) 거짓."""
    return day_date is not None and day_date <= today
