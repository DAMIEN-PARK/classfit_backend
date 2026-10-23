"""교육 기록 읽기·쓰기(T7 결정 iv·vi·x·xv). flush 까지만.

- 기록은 세션당 1행이다(none = 행 없음). 칸 값은 service 가 dict(Mapping) 로 준다 — crud 는 service 의 RecordFields 를
  모른다(계약 ①). 기록 시각·확인 시각은 DB 의 now() 다.
- 잠근 뒤 읽기(T5 결정 xviii): session_context · get_record · course_day 는 fresh=True 면 populate_existing 이고,
  day_sessions 는 늘 populate_existing 이다(잠금을 기다린 사이 커밋된 재배정·기록을 identity map 의 옛 값이 가리지 않게).
- 목록의 첫 WHERE 는 주체 범위다: 기록 목록 course_rows 는 session_scope(관리자 전부 · 강사 내 세션, 결정 x),
  홈 미기록 record_todo_rows 는 course_scope → 보관 아님 → session_scope(결정 xv, crud.my_home 꼴).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.course import course_status_sql
from classfit.crud.my_home import TodoRow
from classfit.crud.scope import Subject, course_scope, session_scope
from classfit.models import Course, CourseDay, CourseSession, Section, SessionRecord


@dataclass(frozen=True)
class SessionContext:
    """세션 · 그 세션의 강의 id · 그 세션 일차 행(일차 미정이거나 그 일차가 없으면 None)."""

    row: CourseSession
    course_id: int
    day: CourseDay | None


@dataclass(frozen=True)
class RecordRow:
    """기록 목록 한 행: 세션 · 섹션 · 일차(없으면 None) · 기록(없으면 None = none)."""

    row: CourseSession
    section: Section
    day: CourseDay | None
    record: SessionRecord | None


def _same_day() -> ColumnElement[bool]:
    """세션의 일차 행(그 강의 · 그 day_no)."""
    return and_(
        CourseDay.course_id == Section.course_id,
        CourseDay.day_no == CourseSession.day_no,
    )


async def session_context(
    session: AsyncSession, session_id: int, *, fresh: bool = False
) -> SessionContext | None:
    """세션 JOIN 섹션 LEFT JOIN 일차 한 문장. 없으면 None. 범위 없는 getter 다(404 판정용)."""
    stmt = (
        select(CourseSession, Section.course_id, CourseDay)
        .join(Section, Section.id == CourseSession.section_id)
        .outerjoin(CourseDay, _same_day())
        .where(CourseSession.id == session_id)
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    found = (await session.execute(stmt)).first()
    return SessionContext(found[0], found[1], found[2]) if found is not None else None


async def get_record(
    session: AsyncSession, session_id: int, *, fresh: bool = False
) -> SessionRecord | None:
    stmt = select(SessionRecord).where(SessionRecord.session_id == session_id)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def insert_record(
    session: AsyncSession,
    *,
    session_id: int,
    status: str,
    values: Mapping[str, Any],
    by_kind: str,
    by_id: int,
    confirmed_by_id: int | None,
) -> SessionRecord:
    """새 기록 행. 칸은 apply_record 와 같다."""
    row = SessionRecord(session_id=session_id)
    session.add(row)
    return await apply_record(
        session,
        row,
        status=status,
        values=values,
        by_kind=by_kind,
        by_id=by_id,
        confirmed_by_id=confirmed_by_id,
    )


async def apply_record(
    session: AsyncSession,
    row: SessionRecord,
    *,
    status: str,
    values: Mapping[str, Any],
    by_kind: str,
    by_id: int,
    confirmed_by_id: int | None,
) -> SessionRecord:
    """내용 저장: 칸 값 · 상태 · 기록자 · 기록 시각(now). ok 면 확인자·확인 시각(now)을 채우고 아니면 비운다.

    flush 뒤 다시 읽는다(now()·updated_at 이 응답에 쓰인다).
    """
    for name, value in values.items():
        setattr(row, name, value)
    row.status = status
    row.recorded_by_kind = by_kind
    row.recorded_by_id = by_id
    row.recorded_at = func.now()
    ok = status == "ok"
    row.confirmed_by_id = confirmed_by_id if ok else None
    row.confirmed_at = func.now() if ok else None
    await session.flush()
    await session.refresh(row)
    return row


async def confirm_row(
    session: AsyncSession, row: SessionRecord, *, admin_id: int
) -> SessionRecord:
    """done → ok. 기록자·기록 시각·내용은 그대로다."""
    row.status = "ok"
    row.confirmed_by_id = admin_id
    row.confirmed_at = func.now()
    await session.flush()
    await session.refresh(row)
    return row


async def course_day(
    session: AsyncSession, course_id: int, day_no: int, *, fresh: bool = False
) -> CourseDay | None:
    stmt = select(CourseDay).where(
        CourseDay.course_id == course_id, CourseDay.day_no == day_no
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def day_sessions(
    session: AsyncSession, course_id: int, day_no: int
) -> list[tuple[CourseSession, SessionRecord | None]]:
    """그 강의 그 일차의 세션 전부(모든 섹션)와 기록. 순서는 (섹션 순서, 섹션 id, 교시(미정 뒤), id).

    잠근 뒤 대상을 고르는 자리라 늘 populate_existing 이다.
    """
    stmt = (
        select(CourseSession, SessionRecord)
        .join(Section, Section.id == CourseSession.section_id)
        .outerjoin(SessionRecord, SessionRecord.session_id == CourseSession.id)
        .where(Section.course_id == course_id, CourseSession.day_no == day_no)
        .order_by(
            Section.sort,
            Section.id,
            CourseSession.slot.asc().nulls_last(),
            CourseSession.id,
        )
        .execution_options(populate_existing=True)
    )
    return [(s, r) for s, r in (await session.execute(stmt)).all()]


async def course_rows(
    session: AsyncSession, subject: Subject, course_id: int
) -> list[RecordRow]:
    """그 강의에서 주체 범위의 세션(첫 WHERE session_scope)과 일차·기록.

    순서는 (섹션 순서, 섹션 id, 일차(미정 뒤), 교시(미정 뒤), id).
    """
    stmt = (
        select(CourseSession, Section, CourseDay, SessionRecord)
        .join(Section, Section.id == CourseSession.section_id)
        .outerjoin(CourseDay, _same_day())
        .outerjoin(SessionRecord, SessionRecord.session_id == CourseSession.id)
        .where(session_scope(subject))
        .where(Section.course_id == course_id)
        .order_by(
            Section.sort,
            Section.id,
            CourseSession.day_no.asc().nulls_last(),
            CourseSession.slot.asc().nulls_last(),
            CourseSession.id,
        )
    )
    return [RecordRow(*values) for values in (await session.execute(stmt)).all()]


async def record_todo_rows(
    session: AsyncSession, subject: Subject, *, today: dt.date, limit: int
) -> tuple[list[TodoRow], bool]:
    """종료·보관 아닌 범위 강의의 내 세션 가운데 일차 날짜 ≤ today ∧ 기록 없음(결정 xv).

    순서는 일차 날짜, 강의 id, 교시(미정 뒤), 세션 id. limit + 1 로 읽어 (앞 limit 행, 더 있는지).
    """
    recorded = exists().where(SessionRecord.session_id == CourseSession.id)
    stmt = (
        select(
            Course.id,
            Course.title,
            Section.id,
            Section.title,
            CourseSession.id,
            CourseSession.title,
            CourseSession.day_no,
            CourseSession.slot,
        )
        .select_from(Course)
        .join(Section, Section.course_id == Course.id)
        .join(CourseSession, CourseSession.section_id == Section.id)
        .join(CourseDay, _same_day())
        .where(course_scope(subject), Course.archived_at.is_(None))
        .where(course_status_sql(today) != "ended")
        .where(session_scope(subject), CourseDay.date <= today, ~recorded)
        .order_by(
            CourseDay.date,
            Course.id,
            CourseSession.slot.asc().nulls_last(),
            CourseSession.id,
        )
        .limit(limit + 1)
    )
    rows = [TodoRow(*values) for values in (await session.execute(stmt)).all()]
    return rows[:limit], len(rows) > limit
