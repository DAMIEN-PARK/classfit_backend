"""수강생 명단 끝점(관리자만): GET /v1/admin/courses/{course_id}/enrollments.

- 목록은 키셋 커서 {items, next_cursor, has_more}, (created_at, id) 내림차순이다(T2a 강의 목록과 같다).
  첫 WHERE 는 주체 범위(crud.enrollment.list_stmt)다. 깨진 커서는 422 이고 violations[].loc 는 ["query", "cursor"] 다.
- 이름·부서는 이 강의 등록의 값이고, 이메일은 learner 의 값이다. 이 응답만 개인 칸을 준다(관리자 전용).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import AdminCaller, DbSession
from classfit.app.endpoints.courses import course_or_404
from classfit.crud import enrollment as crud_enrollment
from classfit.crud.page import keyset_page
from classfit.schemas.enrollment import EnrollmentOut
from classfit.schemas.page import Page

router = APIRouter(prefix="/v1/admin", tags=["enrollments"])


@router.get(
    "/courses/{course_id}/enrollments",
    response_model=Page[EnrollmentOut],
    responses={404: {"description": "강의가 없음"}},
)
async def list_enrollments(
    course_id: int,
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
    return Page[EnrollmentOut](
        items=[
            EnrollmentOut(
                id=r.id,
                name=r.name,
                dept=r.dept,
                email=r.learner.email,
                enrolled_at=r.created_at,
            )
            for r in items
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )
