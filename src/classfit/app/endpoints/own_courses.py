"""강사 고유 과정 끝점(InstructorCaller, T4 계획 결정 i·vi·xi·xiii·xvi).

- GET·POST /v1/me/own-courses: 내 고유 과정(비활성 포함, active 칸으로 보인다, 한 쪽 500) · 등록 201.
  등록은 id own-<강사 id>-<n> · reviewed 거짓 · pub 거짓 · active 참이다(service.pool.own.create_own_course).
- GET·PATCH·DELETE /v1/me/own-courses/{pool_id}: 판정 순서는 404(없음) → 403(AX 과정 · 남의 것) → 409(비활성, PATCH 만)
  이다(결정 i, service.pool.own). 범위 함수가 아니라 범위 없는 getter + owned_by 로 판정하므로 남의 고유 과정 GET 도
  404 가 아니라 403 이다.
- PATCH 는 준 칸만 바꾼다. 내용 칸이 하나라도 바뀌면 reviewed 가 거짓으로 돌아가고 pub·active 는 그대로다(결정 vi).
  바뀐 칸이 있을 때만 audit pool_course.update 1행.
- DELETE 는 지우지 않고 active 를 끈다(가정 7 · 결정 xi). 행·역량·파일은 남고 강사 풀·새 역량·카탈로그에서 빠진다.
  이미 비활성이면 204 + audit 없음. 다시 켜는 길은 관리자 PATCH active=true 뿐이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import DbSession, InstructorCaller
from classfit.app.endpoints.pool import (
    base_fields,
    content_fields,
    files_by_owner,
    id_or_404,
)
from classfit.crud import capability as crud_capability
from classfit.crud import pool as crud_pool
from classfit.models import PoolCourse
from classfit.schemas.page import Page
from classfit.schemas.pool import (
    OwnCourseIn,
    OwnCourseOut,
    OwnCoursePatchIn,
    PoolFileOut,
)
from classfit.service.pool import own

router = APIRouter(prefix="/v1/me", tags=["own-courses"])

FILE_KIND = "pool_course_file"
_ONE = {
    403: {"description": "AX 과정 · 남의 고유 과정"},
    404: {"description": "과정이 없음"},
}


def own_course_out(
    row: PoolCourse, *, capable: bool, files: list[PoolFileOut]
) -> OwnCourseOut:
    return OwnCourseOut(
        **base_fields(row),
        **content_fields(row),
        mine=True,
        capable=capable,
        files=files,
        reviewed=row.reviewed,
        reviewed_at=row.reviewed_at,
        pub=row.pub,
        active=row.active,
    )


async def _one_out(
    session: AsyncSession, instructor_id: int, pool_id: str
) -> OwnCourseOut:
    row = await own.get_own_course(
        session, instructor_id=instructor_id, pool_id=pool_id
    )
    capable = (
        await crud_capability.get_capability_any(session, instructor_id, row.id)
        is not None
    )
    files = await files_by_owner(session, FILE_KIND, [row.id])
    return own_course_out(row, capable=capable, files=files.get(row.id, []))


@router.get("/own-courses", response_model=Page[OwnCourseOut])
async def list_own_courses(
    session: DbSession, caller: InstructorCaller
) -> Page[OwnCourseOut]:
    rows, has_more = await crud_pool.first_page(
        session, crud_pool.list_own_stmt(caller)
    )
    ids = [r.id for r in rows]
    capable = await crud_capability.capable_pool_ids(session, caller.id, ids)
    files = await files_by_owner(session, FILE_KIND, ids)
    return Page[OwnCourseOut](
        items=[
            own_course_out(r, capable=r.id in capable, files=files.get(r.id, []))
            for r in rows
        ],
        next_cursor=None,
        has_more=has_more,
    )


@router.post("/own-courses", response_model=OwnCourseOut, status_code=201)
async def create_own_course(
    body: OwnCourseIn, session: DbSession, caller: InstructorCaller
) -> OwnCourseOut:
    row = await own.create_own_course(
        session, instructor_id=caller.id, fields=body.fields()
    )
    return own_course_out(row, capable=False, files=[])


@router.get("/own-courses/{pool_id}", response_model=OwnCourseOut, responses=_ONE)
async def get_own_course(
    pool_id: str, session: DbSession, caller: InstructorCaller
) -> OwnCourseOut:
    return await _one_out(session, caller.id, id_or_404(pool_id, "과정이 없습니다"))


@router.patch(
    "/own-courses/{pool_id}",
    response_model=OwnCourseOut,
    responses={**_ONE, 409: {"description": "사용 중지된 과정"}},
)
async def patch_own_course(
    pool_id: str, body: OwnCoursePatchIn, session: DbSession, caller: InstructorCaller
) -> OwnCourseOut:
    pool_id = id_or_404(pool_id, "과정이 없습니다")
    await own.patch_own_course(
        session, instructor_id=caller.id, pool_id=pool_id, changes=body.changes()
    )
    return await _one_out(session, caller.id, pool_id)


@router.delete(
    "/own-courses/{pool_id}", status_code=204, response_class=Response, responses=_ONE
)
async def delete_own_course(
    pool_id: str, session: DbSession, caller: InstructorCaller
) -> Response:
    """사용 중지(active 거짓). 행·역량·파일은 남는다."""
    await own.deactivate_own_course(
        session, instructor_id=caller.id, pool_id=id_or_404(pool_id, "과정이 없습니다")
    )
    return Response(status_code=204)
