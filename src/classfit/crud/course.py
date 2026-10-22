"""course 읽기·쓰기와 상태의 SQL 판. flush 까지만.

- 행 넣기 insert_course 는 service.courses.open 의 open_course() 만 부른다(단일 진입점, Design 5절 13).
- course_status_sql 은 service.rules.status.course_status_at 의 SQL 판이다. 목록 필터는 이 판, 응답 status 는 Python 판이다.
  경계는 두 판이 같다: 수동이면 저장값, 아니면 today > end_on → ended, today ≥ start_on → running, 그 밖 prep.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, Select, case, delete, exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.scope import Subject, course_scope
from classfit.models import Course


async def insert_course(session: AsyncSession, **fields: Any) -> Course:
    row = Course(**fields)
    session.add(row)
    await session.flush()
    return row


async def get_course(session: AsyncSession, course_id: int) -> Course | None:
    return await session.get(Course, course_id)


async def lock_course(session: AsyncSession, course_id: int) -> Course | None:
    """강의 행을 SELECT … FOR UPDATE 로 잠그고 새로 읽는다. 없으면(그 사이 지워졌으면) None.

    같은 강의의 입장·코드 관리 네 문·강의 삭제가 이 행 하나로 줄 선다(T2b 결정 v, Design 5절 6).
    populate_existing: 잠금을 기다린 사이 커밋된 값을 identity map 의 옛 값이 가리지 않게 덮어 읽는다.
    """
    stmt = (
        select(Course)
        .where(Course.id == course_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def in_scope(session: AsyncSession, subject: Subject, course_id: int) -> bool:
    """그 강의가 주체 범위 안인가(강사 끝점의 403 판정). 존재(404)는 get_course 가 먼저 본다."""
    stmt = select(exists().where(course_scope(subject), Course.id == course_id))
    return bool(await session.scalar(stmt))


async def update_course(session: AsyncSession, row: Course, **fields: Any) -> Course:
    """칸을 바꾸고 flush. updated_at 은 onupdate 로 바뀌고 만료되니 응답에 쓰려면 다시 읽는다."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    return row


async def delete_course(session: AsyncSession, course_id: int) -> bool:
    """지웠으면 True. course_day·section·session·invite_code 는 FK CASCADE 로 같이 지워진다."""
    stmt = delete(Course).where(Course.id == course_id).returning(Course.id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


def course_status_sql(today: date) -> ColumnElement[str]:
    return case(
        (Course.status_manual.is_(True), Course.status),
        (Course.end_on < today, literal("ended")),
        (Course.start_on <= today, literal("running")),
        else_=literal("prep"),
    )


def list_stmt(
    subject: Subject, status: str | None, archived: bool, today: date
) -> Select[tuple[Course]]:
    """강의 목록. 첫 WHERE 는 주체 범위다. archived 는 보관한 것만(True)·보관 안 한 것만(False)."""
    stmt = select(Course).where(course_scope(subject))
    if archived:
        stmt = stmt.where(Course.archived_at.is_not(None))
    else:
        stmt = stmt.where(Course.archived_at.is_(None))
    if status is not None:
        stmt = stmt.where(course_status_sql(today) == status)
    return stmt
