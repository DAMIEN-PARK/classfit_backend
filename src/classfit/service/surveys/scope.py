"""설문 끝점의 강의 판정(T8 결정 i). 읽기만 한다.

강사 결과(I7)는 범위 없는 getter 로 없으면 404 → 배정된 세션이 없는 강의면 403 이다. T5 service.courses.mine.course_for 와
같은 두 줄을 여기 다시 쓴다 — surveys 는 courses 를 import 하지 않는다(계약 ②).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Forbidden, NotFound
from classfit.crud import course as crud_course
from classfit.crud.scope import Subject
from classfit.models import Course

NO_COURSE = "강의가 없습니다"


async def course_or_404(session: AsyncSession, course_id: int) -> Course:
    course = await crud_course.get_course(session, course_id)
    if course is None:
        raise NotFound(NO_COURSE)
    return course


async def course_for_instructor(
    session: AsyncSession, subject: Subject, course_id: int
) -> Course:
    """없으면 NotFound, 주체 범위 밖(배정된 세션이 없는 강의)이면 Forbidden."""
    course = await course_or_404(session, course_id)
    if not await crud_course.in_scope(session, subject, course_id):
        raise Forbidden("배정된 세션이 없는 강의입니다")
    return course
