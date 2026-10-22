"""강사가 보는 배정 강의와 내 세션 고치기(기획안 I3-1 · 원칙 13, T5 결정 xii·xiii). flush 까지만.

- 범위: 세션 하나라도 배정된 강의(crud.scope.course_scope 강사 갈래). 판정은 404 → 403 이다 — 범위 없는 getter
  (get_course · get_session_and_course)로 없으면 404, 있으면 범위(강의는 in_scope, 세션은 담당 == 주체)로 403.
- 범위 안이면 그 강의의 모든 세션을 읽기 전용으로 본다(남의 세션도 제목·시각·설명·키워드·공개·첨부 수·강사 이름·id).
  첨부는 개수만 준다(파일 판정 OWNER_KINDS["session_attachment"] 은 강사에게 거짓이다, T6 몫).
- 일정표는 관리자 일정표와 같은 계산(days.schedule_of, CRS-010). 목록은 관리자 목록과 같은 crud.course.list_stmt(첫
  WHERE course_scope) + 키셋 커서에 내가 맡은 세션 수를 붙인다.
- 내 세션 고치기는 설명·키워드·공개만이다(그 밖의 칸은 schemas 가 422). 세션 없음 404 → 강의 행 잠금 → 세션을 다시 읽어
  담당 ≠ 주체면 403(배정 해제·변경과 엇갈려 방금 남의 것이 된 세션을 고치지 않게). audit 은 없다(T2a 결정 viii).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Forbidden, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import course as crud_course
from classfit.crud import instructor as crud_instructor
from classfit.crud import schedule as crud_schedule
from classfit.crud.page import keyset_page
from classfit.crud.scope import Subject
from classfit.models import Course, CourseSession, Section
from classfit.schemas.course import ScheduleOut
from classfit.service.courses.days import schedule_of

MY_SESSION_FIELDS = frozenset({"description", "keywords", "is_open"})


@dataclass(frozen=True)
class MySession:
    row: CourseSession
    date: dt.date | None
    start: str | None
    end: str | None
    instructor_name: str | None
    attachments: int  # 첨부 수(href 는 주지 않는다)


@dataclass(frozen=True)
class MySection:
    row: Section
    sessions: list[MySession]


@dataclass(frozen=True)
class MyCourseView:
    course: Course
    sections: list[MySection]


@dataclass(frozen=True)
class MyCoursePage:
    items: list[tuple[Course, int]]  # (강의, 내가 맡은 세션 수)
    next_cursor: str | None
    has_more: bool


async def my_courses(
    session: AsyncSession,
    subject: Subject,
    *,
    status: str | None,
    archived: bool,
    today: dt.date,
    cursor: str | None,
    limit: int,
) -> MyCoursePage:
    """배정된 강의 목록((created_at, id) 내림차순 키셋). 깨진 커서는 ValueError(끝점이 422 loc ["query","cursor"])."""
    stmt = crud_course.list_stmt(subject, status, archived, today)
    items, next_cursor, has_more = await keyset_page(session, stmt, cursor, limit)
    counts = await crud_schedule.my_session_counts(
        session, [c.id for c in items], subject.id
    )
    return MyCoursePage(
        items=[(c, counts.get(c.id, 0)) for c in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


async def course_for(session: AsyncSession, subject: Subject, course_id: int) -> Course:
    """없으면 NotFound, 주체 범위 밖(배정된 세션이 없는 강의)이면 Forbidden."""
    course = await crud_course.get_course(session, course_id)
    if course is None:
        raise NotFound("강의가 없습니다")
    if not await crud_course.in_scope(session, subject, course_id):
        raise Forbidden("배정된 세션이 없는 강의입니다")
    return course


def _key(item: MySession) -> tuple[bool, dt.date, bool, str, int, int]:
    """일차 순 → 시작 시각 순 → 교시 → id. 일차 미정·시각 미정은 뒤로(포털 카드와 같은 순서)."""
    return (
        item.date is None,
        item.date or dt.date.min,
        item.start is None,
        item.start or "",
        item.row.slot or 99,
        item.row.id,
    )


async def course_view(
    session: AsyncSession, subject: Subject, *, course_id: int
) -> MyCourseView:
    course = await course_for(session, subject, course_id)
    schedule = await schedule_of(session, course)
    times: dict[int, tuple[dt.date | None, str | None, str | None]] = {}
    for day in schedule.days:
        for item in day.sessions:
            times[item.id] = (day.date, item.start, item.end)
    for item in schedule.undated:
        times[item.id] = (None, item.start, item.end)
    rows = await crud_schedule.list_sessions(session, course_id)
    counts = await crud_attachment.counts_by_session(session, [r.id for r in rows])
    names = await crud_instructor.names_by_id(
        session, [r.instructor_id for r in rows if r.instructor_id is not None]
    )
    by_section: dict[int, list[MySession]] = defaultdict(list)
    for r in rows:
        date, start, end = times.get(r.id, (None, None, None))
        by_section[r.section_id].append(
            MySession(
                row=r,
                date=date,
                start=start,
                end=end,
                instructor_name=None
                if r.instructor_id is None
                else names.get(r.instructor_id),
                attachments=counts.get(r.id, 0),
            )
        )
    sections = [
        MySection(row=sec, sessions=sorted(by_section[sec.id], key=_key))
        for sec in await crud_schedule.list_sections(session, course_id)
    ]
    return MyCourseView(course=course, sections=sections)


async def schedule_for(
    session: AsyncSession, subject: Subject, *, course_id: int
) -> ScheduleOut:
    """관리자 일정표와 같은 모양·계산(강사 id·이름 칸 포함)."""
    return await schedule_of(session, await course_for(session, subject, course_id))


async def patch_my_session(
    session: AsyncSession,
    *,
    instructor_id: int,
    session_id: int,
    changes: Mapping[str, Any],
) -> CourseSession:
    """내 세션의 설명·키워드·공개만 바꾼다. 없으면 NotFound, 내 세션이 아니면 Forbidden."""
    if unknown := set(changes) - MY_SESSION_FIELDS:
        raise ValueError(f"강사가 고칠 수 없는 칸: {sorted(unknown)}")
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound("세션이 없습니다")
    if await crud_course.lock_course(session, found[1]) is None:
        raise NotFound("세션이 없습니다")
    found = await crud_schedule.get_session_and_course(session, session_id, fresh=True)
    if found is None:
        raise NotFound("세션이 없습니다")
    row, _ = found
    if row.instructor_id != instructor_id:
        raise Forbidden("내 세션만 고칠 수 있습니다")
    return await crud_schedule.apply_fields(session, row, dict(changes))
