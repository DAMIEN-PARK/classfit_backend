"""일정 표 읽기·쓰기: course_day · section · session. flush 까지만.

세션은 section 을 거쳐 강의에 묶인다(session 표에 course_id 칸이 없다). 그래서 강의 범위 조회는 section 과 잇는다.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import CourseDay, CourseSession, Section


async def apply_fields[R](session: AsyncSession, row: R, fields: dict[str, Any]) -> R:
    """일차·섹션·세션 행의 칸을 바꾸고 flush."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    return row


# ── course_day


async def list_days(session: AsyncSession, course_id: int) -> list[CourseDay]:
    stmt = (
        select(CourseDay)
        .where(CourseDay.course_id == course_id)
        .order_by(CourseDay.day_no)
    )
    return list((await session.scalars(stmt)).all())


async def get_day(
    session: AsyncSession, course_id: int, day_no: int
) -> CourseDay | None:
    stmt = select(CourseDay).where(
        CourseDay.course_id == course_id, CourseDay.day_no == day_no
    )
    return await session.scalar(stmt)


async def insert_days(
    session: AsyncSession, course_id: int, days: Sequence[dict[str, Any]]
) -> list[CourseDay]:
    rows = [CourseDay(course_id=course_id, **d) for d in days]
    session.add_all(rows)
    await session.flush()
    return rows


async def replace_days(
    session: AsyncSession, course_id: int, days: Sequence[dict[str, Any]]
) -> list[CourseDay]:
    """그 강의의 일차를 통째로 바꾼다. 지우기를 먼저 내보내야 (course_id, day_no) 유일이 겹치지 않는다."""
    await session.execute(delete(CourseDay).where(CourseDay.course_id == course_id))
    return await insert_days(session, course_id, days)


async def delete_day(session: AsyncSession, course_id: int, day_no: int) -> bool:
    stmt = (
        delete(CourseDay)
        .where(CourseDay.course_id == course_id, CourseDay.day_no == day_no)
        .returning(CourseDay.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


# ── section


async def insert_section(
    session: AsyncSession, course_id: int, **fields: Any
) -> Section:
    row = Section(course_id=course_id, **fields)
    session.add(row)
    await session.flush()
    return row


async def get_section(
    session: AsyncSession, course_id: int, section_id: int
) -> Section | None:
    """그 강의의 섹션만. 다른 강의의 섹션은 None(→ 404)."""
    stmt = select(Section).where(
        Section.id == section_id, Section.course_id == course_id
    )
    return await session.scalar(stmt)


async def list_sections(session: AsyncSession, course_id: int) -> list[Section]:
    stmt = (
        select(Section)
        .where(Section.course_id == course_id)
        .order_by(Section.sort, Section.id)
    )
    return list((await session.scalars(stmt)).all())


async def delete_section(session: AsyncSession, section_id: int) -> None:
    """세션은 FK CASCADE 로 같이 지워진다."""
    await session.execute(delete(Section).where(Section.id == section_id))


# ── session


async def insert_session(
    session: AsyncSession, section_id: int, **fields: Any
) -> CourseSession:
    row = CourseSession(section_id=section_id, **fields)
    session.add(row)
    await session.flush()
    return row


async def get_session_and_course(
    session: AsyncSession, session_id: int
) -> tuple[CourseSession, int] | None:
    """(세션, 그 세션의 강의 id). 없으면 None."""
    stmt = (
        select(CourseSession, Section.course_id)
        .join(Section, Section.id == CourseSession.section_id)
        .where(CourseSession.id == session_id)
    )
    found = (await session.execute(stmt)).first()
    return (found[0], found[1]) if found is not None else None


async def list_sessions(session: AsyncSession, course_id: int) -> list[CourseSession]:
    """그 강의의 세션 전부. 순서는 (섹션 순서, 섹션 id, 교시, id)."""
    stmt = (
        select(CourseSession)
        .join(Section, Section.id == CourseSession.section_id)
        .where(Section.course_id == course_id)
        .order_by(Section.sort, Section.id, CourseSession.slot, CourseSession.id)
    )
    return list((await session.scalars(stmt)).all())


async def delete_session(session: AsyncSession, session_id: int) -> None:
    await session.execute(delete(CourseSession).where(CourseSession.id == session_id))


async def unset_session_days(
    session: AsyncSession,
    course_id: int,
    *,
    day_nos: Collection[int] | None = None,
    after: int | None = None,
) -> None:
    """그 강의에서 day_nos 의 세션, 또는 after 보다 큰 일차의 세션을 "일차 미정"(day_no·slot NULL)으로."""
    in_course = CourseSession.section_id.in_(
        select(Section.id).where(Section.course_id == course_id)
    )
    if day_nos is not None:
        which = CourseSession.day_no.in_(list(day_nos))
    elif after is not None:
        which = CourseSession.day_no > after
    else:
        raise ValueError("day_nos 나 after 중 하나는 있어야 한다")
    stmt = (
        update(CourseSession)
        .where(in_course, which)
        .values(day_no=None, slot=None)
        .execution_options(synchronize_session="fetch")
    )
    await session.execute(stmt)
