"""enrollment 읽기·쓰기. flush 까지만.

- 행 넣기 insert_enrollment 는 service.enroll.enter 만 부른다(단일 진입, tests/integration/test_db_enroll.py 가 센다).
  정원을 세고 넣는 경쟁은 부르는 쪽이 강의 행을 먼저 잠가 줄 세운다(crud.course.lock_course).
- 관리자 명단 list_stmt 의 첫 WHERE 는 주체 범위다(crud.scope.course_scope). 이메일은 learner 를 joinedload 로 같이 읽는다.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from classfit.crud.scope import Subject, course_scope
from classfit.models import Course, Enrollment


async def find_enrollment(
    session: AsyncSession, course_id: int, learner_id: int
) -> Enrollment | None:
    stmt = select(Enrollment).where(
        Enrollment.course_id == course_id, Enrollment.learner_id == learner_id
    )
    return await session.scalar(stmt)


async def insert_enrollment(
    session: AsyncSession,
    *,
    course_id: int,
    learner_id: int,
    name: str,
    dept: str | None,
) -> Enrollment:
    row = Enrollment(course_id=course_id, learner_id=learner_id, name=name, dept=dept)
    session.add(row)
    await session.flush()
    return row


async def count_enrollments(session: AsyncSession, course_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(Enrollment)
        .where(Enrollment.course_id == course_id)
    )
    return await session.scalar(stmt) or 0


async def has_enrollments(session: AsyncSession, course_id: int) -> bool:
    stmt = select(
        select(Enrollment.id).where(Enrollment.course_id == course_id).exists()
    )
    return bool(await session.scalar(stmt))


def list_stmt(subject: Subject, course_id: int) -> Select[tuple[Enrollment]]:
    """그 강의의 명단(crud.page.keyset_page 에 넘긴다). 행마다 row.learner.email 을 읽을 수 있다.

    강사 주체로 부르지 않는다 — 명단 PII(이름·이메일)가 course_scope 강사 갈래 범위를 그대로 통과한다
    (T6 에서 강사 화면이 필요하면 따로 정한다, T5 리뷰 Nit 4).
    """
    return (
        select(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .where(course_scope(subject))
        .where(Enrollment.course_id == course_id)
        .options(joinedload(Enrollment.learner))
    )
