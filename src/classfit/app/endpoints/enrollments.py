"""수강생 명단 끝점(관리자만): GET /v1/admin/courses/{course_id}/enrollments.

- 목록은 키셋 커서 {items, next_cursor, has_more}, (created_at, id) 내림차순이다(T2a 강의 목록과 같다).
  첫 WHERE 는 주체 범위(crud.enrollment.list_stmt)다. 깨진 커서는 422 이고 violations[].loc 는 ["query", "cursor"] 다.
- 이름·부서는 이 강의 등록의 값이고, 이메일은 learner 의 값이다. 이 응답만 개인 칸을 준다(관리자 전용).
- survey_responded 는 그 강의 현재 설문에 그 등록의 응답이 있는지다(현재 설문이 없으면 null, T8 결정 xiv). 쪽을 받은
  뒤 한 번 묻는다(survey_responders — 강사 명단도 쓴다). 답·제출 시각과 잇는 칸은 없다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import AdminCaller, DbSession, IdPath
from classfit.app.endpoints.courses import course_or_404
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import survey as crud_survey
from classfit.crud import survey_response as crud_survey_response
from classfit.crud.page import keyset_page
from classfit.schemas.enrollment import EnrollmentOut
from classfit.schemas.page import Page

router = APIRouter(prefix="/v1/admin", tags=["enrollments"])


async def survey_responders(
    session: AsyncSession, course_id: int, enrollment_ids: Sequence[int]
) -> set[int] | None:
    """그 강의 현재 설문에 응답한 등록 id(이 쪽 안). 현재 설문이 없으면 None(명단 칸 null)."""
    survey = await crud_survey.current_for_course(session, course_id)
    if survey is None:
        return None
    if not enrollment_ids:
        return set()
    return await crud_survey_response.responded_ids(
        session, survey.id, list(enrollment_ids)
    )


@router.get(
    "/courses/{course_id}/enrollments",
    response_model=Page[EnrollmentOut],
    responses={404: {"description": "강의가 없음"}},
)
async def list_enrollments(
    course_id: IdPath,
    session: DbSession,
    caller: AdminCaller,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[EnrollmentOut]:
    await course_or_404(session, course_id)
    stmt = crud_enrollment.list_stmt(caller, course_id)
    try:
        items, next_cursor, has_more = await keyset_page(session, stmt, cursor, limit)
    except ValueError:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "cursor"),
                    "msg": "깨진 커서입니다",
                    "type": "value_error",
                }
            ]
        ) from None
    responded = await survey_responders(session, course_id, [r.id for r in items])
    return Page[EnrollmentOut](
        items=[
            EnrollmentOut(
                id=r.id,
                name=r.name,
                dept=r.dept,
                email=r.learner.email,
                enrolled_at=r.created_at,
                survey_responded=None if responded is None else r.id in responded,
            )
            for r in items
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )
