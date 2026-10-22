"""일정 표 읽기·쓰기: course_day · section · session. flush 까지만.

세션은 section 을 거쳐 강의에 묶인다(session 표에 course_id 칸이 없다). 그래서 강의 범위 조회는 section 과 잇는다.
담당 강사(session.instructor_id, T5)는 set_instructor 로만 바꾼다(service.courses.assign — 배정 audit·outbox 가 따른다).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from sqlalchemy import delete, func, select, update
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
    session: AsyncSession, session_id: int, *, fresh: bool = False
) -> tuple[CourseSession, int] | None:
    """(세션, 그 세션의 강의 id). 없으면 None.

    fresh: 강의 행을 잠근 뒤 다시 읽을 때 쓴다(populate_existing — 잠금을 기다린 사이 커밋된 값을 identity map 의
    옛 값이 가리지 않게 덮어 읽는다, T5 결정 xviii).
    """
    stmt = (
        select(CourseSession, Section.course_id)
        .join(Section, Section.id == CourseSession.section_id)
        .where(CourseSession.id == session_id)
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
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


async def list_section_sessions(
    session: AsyncSession, section_id: int
) -> list[CourseSession]:
    """그 섹션의 세션 전부, (id) 순. 잠근 뒤 다시 읽는 자리라 populate_existing 이다."""
    stmt = (
        select(CourseSession)
        .where(CourseSession.section_id == section_id)
        .order_by(CourseSession.id)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def reload_sessions(
    session: AsyncSession, course_id: int, session_ids: Collection[int]
) -> list[CourseSession]:
    """그 강의의 세션을 id 로 다시 읽는다(populate_existing, id 순). 그 사이 지워졌거나 다른 강의의 세션은 빠진다."""
    ids = list(session_ids)
    if not ids:
        return []
    stmt = (
        select(CourseSession)
        .join(Section, Section.id == CourseSession.section_id)
        .where(Section.course_id == course_id, CourseSession.id.in_(ids))
        .order_by(CourseSession.id)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def used_slots(session: AsyncSession, section_id: int) -> dict[int, set[int]]:
    """그 섹션에서 일차마다 이미 쓴 교시(일차 → 교시 집합). 일차·교시가 없는 세션은 빠진다."""
    stmt = select(CourseSession.day_no, CourseSession.slot).where(
        CourseSession.section_id == section_id,
        CourseSession.day_no.is_not(None),
        CourseSession.slot.is_not(None),
    )
    out: dict[int, set[int]] = {}
    for day_no, slot in (await session.execute(stmt)).all():
        out.setdefault(day_no, set()).add(slot)
    return out


async def set_instructor(
    session: AsyncSession, rows: Sequence[CourseSession], instructor_id: int | None
) -> list[int]:
    """담당 강사를 바꾸고 flush. 실제로 바뀐 세션 id(준 순서). 이미 그 강사인 행은 건드리지 않는다.

    instructor_id 칸만 바꾸므로 UPDATE 의 FK 검사는 강사 행에만 걸린다(T5 결정 xvii).
    """
    changed = [row for row in rows if row.instructor_id != instructor_id]
    for row in changed:
        row.instructor_id = instructor_id
    if changed:
        await session.flush()
    return [row.id for row in changed]


async def my_session_counts(
    session: AsyncSession, course_ids: Collection[int], instructor_id: int
) -> dict[int, int]:
    """강의마다 그 강사가 맡은 세션 수. 맡은 세션이 없으면 키가 없다.

    범위로 걸러진 강의 id 만 받는다 — 부르는 쪽이 course_scope 목록에서 뽑아 넘긴다.
    """
    ids = list(course_ids)
    if not ids:
        return {}
    stmt = (
        select(Section.course_id, func.count())
        .join(CourseSession, CourseSession.section_id == Section.id)
        .where(Section.course_id.in_(ids), CourseSession.instructor_id == instructor_id)
        .group_by(Section.course_id)
    )
    return {cid: n for cid, n in (await session.execute(stmt)).all()}


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
