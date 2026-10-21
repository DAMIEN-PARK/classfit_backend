"""일차와 일정표, 그리고 기간 규칙(T2a 계획 결정 i·v). flush 까지만.

- 일차가 있으면 강의 기간(start_on·end_on)은 첫·끝 일차 날짜를 따른다. 일차를 바꾸는 요청이 같은 트랜잭션에서 고친다.
  그래서 일차가 있는 강의의 기간을 PATCH 로 바꾸면 409 다.
- PUT 은 일차를 통째로 바꾸고 1..n 으로 다시 매긴다. 없어진 일차(> n)의 세션은 "일차 미정"(day_no·slot NULL)이 된다.
- PATCH 로 날짜를 바꿔 앞뒤 일차와 순서가 어긋나면 409. DELETE 는 번호를 다시 매기지 않고 그날 세션을 일차 미정으로 둔다.
- 저장 상태와의 충돌은 409(Conflict), 본문 모양 오류는 schemas 가 422 로 막는다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import course as crud_course
from classfit.crud import schedule as crud_schedule
from classfit.models import Course, CourseSession
from classfit.schemas.course import (
    CoursePatchIn,
    DayPatchIn,
    DaysPutIn,
    ScheduleDayOut,
    ScheduleOut,
    ScheduleSessionOut,
)
from classfit.service.rules.schedule import session_time

_PERIOD = ("start_on", "end_on")
_DAY_FIELDS = ("date", "start_time", "end_time", "lunch_start", "lunch_end")


async def patch_course(
    session: AsyncSession, course: Course, body: CoursePatchIn
) -> Course:
    """강의 기본 정보를 준 칸만 바꾼다. 일차가 있는데 기간을 바꾸면 409, 기간이 뒤집히면 409."""
    changes = body.changes()
    if any(k in changes for k in _PERIOD):
        moved = any(getattr(course, k) != changes[k] for k in _PERIOD if k in changes)
        if moved and await crud_schedule.list_days(session, course.id):
            raise Conflict("일차가 있는 강의의 기간은 일차가 정합니다. 일차를 바꾸세요")
        start_on = changes.get("start_on", course.start_on)
        end_on = changes.get("end_on", course.end_on)
        if start_on > end_on:
            raise Conflict("시작일이 종료일보다 뒤가 됩니다")
    if changes:
        await crud_course.update_course(session, course, **changes)
    return course


async def _follow_period(session: AsyncSession, course: Course) -> None:
    """일차가 있으면 기간을 첫·끝 일차 날짜로 맞춘다. 일차가 없으면 기간은 그대로다."""
    days = await crud_schedule.list_days(session, course.id)
    if not days:
        return
    start_on, end_on = min(d.date for d in days), max(d.date for d in days)
    if (course.start_on, course.end_on) != (start_on, end_on):
        await crud_course.update_course(
            session, course, start_on=start_on, end_on=end_on
        )


async def put_days(session: AsyncSession, course: Course, body: DaysPutIn) -> None:
    rows = [{"day_no": no, **d.model_dump()} for no, d in enumerate(body.days, start=1)]
    await crud_schedule.replace_days(session, course.id, rows)
    await crud_schedule.unset_session_days(session, course.id, after=len(rows))
    await _follow_period(session, course)


async def patch_day(
    session: AsyncSession, course: Course, day_no: int, body: DayPatchIn
) -> None:
    day = await crud_schedule.get_day(session, course.id, day_no)
    if day is None:
        raise NotFound("그 일차가 없습니다")
    changes = body.changes()
    final = {k: changes.get(k, getattr(day, k)) for k in _DAY_FIELDS}
    if final["start_time"] >= final["end_time"]:
        raise Conflict("그날 시작이 끝보다 앞이어야 합니다")
    if (final["lunch_start"] is None) != (final["lunch_end"] is None):
        raise Conflict("점심 시작·끝은 둘 다 있거나 둘 다 없어야 합니다")
    if final["lunch_start"] is not None and final["lunch_start"] >= final["lunch_end"]:
        raise Conflict("점심 시작이 끝보다 앞이어야 합니다")
    if final["date"] != day.date:
        await _check_order(session, course.id, day_no, final["date"])
    await crud_schedule.apply_fields(session, day, changes)
    await _follow_period(session, course)


async def _check_order(
    session: AsyncSession, course_id: int, day_no: int, new: date
) -> None:
    days = await crud_schedule.list_days(session, course_id)
    before = [d.date for d in days if d.day_no < day_no]
    after = [d.date for d in days if d.day_no > day_no]
    if (before and new <= max(before)) or (after and new >= min(after)):
        raise Conflict(
            "일차 날짜 순서가 어긋납니다(앞 일차보다 뒤, 뒤 일차보다 앞이어야 합니다)"
        )


async def delete_day(session: AsyncSession, course: Course, day_no: int) -> None:
    if not await crud_schedule.delete_day(session, course.id, day_no):
        raise NotFound("그 일차가 없습니다")
    await crud_schedule.unset_session_days(session, course.id, day_nos=[day_no])
    await _follow_period(session, course)


def _sort_key(item: ScheduleSessionOut) -> tuple[bool, str, int, int]:
    return (item.start is None, item.start or "", item.slot or 99, item.id)


async def schedule_of(session: AsyncSession, course: Course) -> ScheduleOut:
    """일차마다 세션 시각을 rules.schedule.session_time 으로 계산한 일정표. 일차 미정 세션은 undated."""
    days = await crud_schedule.list_days(session, course.id)
    sessions = await crud_schedule.list_sessions(session, course.id)
    by_section: dict[int, list[CourseSession]] = defaultdict(list)
    for s in sessions:
        by_section[s.section_id].append(s)
    day_of = {d.day_no: d for d in days}
    per_day: dict[int, list[ScheduleSessionOut]] = defaultdict(list)
    undated: list[ScheduleSessionOut] = []
    for s in sessions:
        day = day_of.get(s.day_no) if s.day_no is not None else None
        times = session_time(
            day, course.slot_min, course.break_min, by_section[s.section_id], s
        )
        item = ScheduleSessionOut(
            id=s.id,
            section_id=s.section_id,
            title=s.title,
            slot=s.slot,
            start=times[0] if times else None,
            end=times[1] if times else None,
        )
        if day is None:
            undated.append(item)
        else:
            per_day[day.day_no].append(item)
    return ScheduleOut(
        days=[
            ScheduleDayOut(
                day_no=d.day_no,
                date=d.date,
                start_time=d.start_time,
                end_time=d.end_time,
                lunch_start=d.lunch_start,
                lunch_end=d.lunch_end,
                sessions=sorted(per_day[d.day_no], key=_sort_key),
            )
            for d in days
        ],
        undated=sorted(undated, key=_sort_key),
    )
