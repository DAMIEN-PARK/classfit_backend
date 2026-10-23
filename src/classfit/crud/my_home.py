"""강사 홈의 셈과 목록(T6 결정 xiv). 읽기만 한다.

- 강의 질의의 첫 WHERE 는 course_scope(주체)이고 보관한 강의는 뺀다(archived_at IS NULL). 상태는 오늘 기준 SQL 판
  course_status_sql 이다. 내 세션 셈은 그 뒤에 session_scope(주체)를 단다. "준비된" 내 세션은 첨부가 1개 이상인 세션이다.
- 상태별 셈은 GROUP BY 대신 집계 FILTER 로 한다 — 상태 식에 바인드 값(today)이 있어 GROUP BY 식과 SELECT 식이
  서로 다른 자리 표시자가 되면 PG 가 같은 식으로 보지 않는다.
- 셈 셋(capable_count)은 capability_scope · own_course_scope(+ 활성) · curriculum_scope(+ 활성)가 첫 WHERE 다.
- 목록은 limit + 1 로 읽어 (앞 limit 행, 더 있는지)를 돌려준다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Exists, case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.course import course_status_sql
from classfit.crud.scope import (
    Subject,
    capability_scope,
    course_scope,
    curriculum_scope,
    own_course_scope,
    session_scope,
)
from classfit.models import (
    Capability,
    Course,
    CourseSession,
    Curriculum,
    PoolCourse,
    Section,
    SessionAttachment,
)


@dataclass(frozen=True)
class HomeCourseRow:
    course: Course
    status: str  # 오늘 기준(course_status_sql)
    my_sessions: int
    my_ready: int  # 첨부가 1개 이상인 내 세션


@dataclass(frozen=True)
class TodoRow:
    course_id: int
    course_title: str
    section_id: int
    section_title: str
    session_id: int
    session_title: str
    day_no: int | None
    slot: int | None


def _has_attachment() -> Exists:
    """그 세션(바깥 질의의 session 행)에 첨부가 있다."""
    return exists().where(SessionAttachment.session_id == CourseSession.id)


def _live_course(subject: Subject) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """범위 안 ∧ 보관하지 않은 강의. 첫 조건이 course_scope 다."""
    return (course_scope(subject), Course.archived_at.is_(None))


async def course_summary(
    session: AsyncSession, subject: Subject, *, today: dt.date
) -> dict[str, int]:
    """{courses, running, prep, ended, my_sessions, my_ready}."""
    status = course_status_sql(today)
    courses = (
        select(
            func.count(),
            func.count().filter(status == "running"),
            func.count().filter(status == "prep"),
            func.count().filter(status == "ended"),
        )
        .select_from(Course)
        .where(*_live_course(subject))
    )
    total, running, prep, ended = (await session.execute(courses)).one()
    sessions = (
        select(func.count(), func.count().filter(_has_attachment()))
        .select_from(CourseSession)
        .join(Section, Section.id == CourseSession.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(*_live_course(subject))
        .where(session_scope(subject))
    )
    my_sessions, my_ready = (await session.execute(sessions)).one()
    return {
        "courses": total,
        "running": running,
        "prep": prep,
        "ended": ended,
        "my_sessions": my_sessions,
        "my_ready": my_ready,
    }


async def course_rows(
    session: AsyncSession, subject: Subject, *, today: dt.date, limit: int
) -> tuple[list[HomeCourseRow], bool]:
    """보관 안 한 범위 강의. 순서는 진행 → 준비 → 종료, 시작일, id."""
    mine = (
        select(
            Section.course_id.label("course_id"),
            func.count().label("my_sessions"),
            func.count().filter(_has_attachment()).label("my_ready"),
        )
        .join(CourseSession, CourseSession.section_id == Section.id)
        .where(session_scope(subject))
        .group_by(Section.course_id)
        .subquery()
    )
    status = course_status_sql(today)
    rank = case((status == "running", 0), (status == "prep", 1), else_=2)
    stmt = (
        select(
            Course,
            status,
            func.coalesce(mine.c.my_sessions, 0),
            func.coalesce(mine.c.my_ready, 0),
        )
        .outerjoin(mine, mine.c.course_id == Course.id)
        .where(*_live_course(subject))
        .order_by(rank, Course.start_on, Course.id)
        .limit(limit + 1)
    )
    rows = [
        HomeCourseRow(course=c, status=s, my_sessions=n, my_ready=r)
        for c, s, n, r in (await session.execute(stmt)).all()
    ]
    return rows[:limit], len(rows) > limit


async def todo_rows(
    session: AsyncSession, subject: Subject, *, today: dt.date, limit: int
) -> tuple[list[TodoRow], bool]:
    """종료·보관 아닌 강의에서 첨부가 0개인 내 세션. 순서는 강의 시작일, 강의 id, 일차(미정은 뒤), 교시, 세션 id."""
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
        .where(*_live_course(subject))
        .where(course_status_sql(today) != "ended")
        .where(session_scope(subject), ~_has_attachment())
        .order_by(
            Course.start_on,
            Course.id,
            CourseSession.day_no.asc().nulls_last(),
            CourseSession.slot.asc().nulls_last(),
            CourseSession.id,
        )
        .limit(limit + 1)
    )
    rows = [TodoRow(*values) for values in (await session.execute(stmt)).all()]
    return rows[:limit], len(rows) > limit


async def capable_count(session: AsyncSession, subject: Subject) -> int:
    """내 역량 행 + 활성 고유 과정 + 활성 커리큘럼 수."""
    counts = (
        select(func.count()).select_from(Capability).where(capability_scope(subject)),
        select(func.count())
        .select_from(PoolCourse)
        .where(own_course_scope(subject))
        .where(PoolCourse.active.is_(True)),
        select(func.count())
        .select_from(Curriculum)
        .where(curriculum_scope(subject))
        .where(Curriculum.active.is_(True)),
    )
    total = 0
    for stmt in counts:
        total += await session.scalar(stmt) or 0
    return total
