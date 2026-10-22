"""관리자 심화 과정 끝점(AdminCaller, T4 계획 결정 xii·xiii·xvii).

- GET /v1/admin/advanced-courses?active=: 비활성 포함 한 쪽 500(커서 없음). 순서는 id.
- POST /v1/admin/advanced-courses: 추가 201. id 는 adv-<n> 이고 import 가 넣은 adv-1… 과 겹치면 다음 번호로 넘어간다
  (crud.pool.next_id 의 존재 검사 루프, 결정 xiii). pub 거짓 · active 참으로 시작한다.
- PATCH /v1/admin/advanced-courses/{advanced_course_id}: 내용 · pub · active. 삭제는 없다(사용 중지, 기획안 :780).
  바뀐 칸이 있을 때만 audit advanced_course.update 1행.
"""

from __future__ import annotations

from fastapi import APIRouter

from classfit.app.deps import AdminCaller, DbSession
from classfit.app.endpoints.pool import valid_text_id
from classfit.core.errors import NotFound
from classfit.crud import advanced as crud_advanced
from classfit.crud import pool as crud_pool
from classfit.models import AdvancedCourse
from classfit.schemas.advanced import AdvancedIn, AdvancedOut, AdvancedPatchIn
from classfit.schemas.page import Page
from classfit.service.pool import admin

router = APIRouter(prefix="/v1/admin", tags=["admin-advanced-courses"])


def advanced_out(row: AdvancedCourse) -> AdvancedOut:
    return AdvancedOut(
        id=row.id,
        title=row.title,
        audience=row.audience,
        tool=row.tool,
        hours=row.hours,
        goal=row.goal,
        features=list(row.features),
        pub=row.pub,
        active=row.active,
        created_at=row.created_at,
    )


@router.get("/advanced-courses", response_model=Page[AdvancedOut])
async def list_advanced(
    session: DbSession, _: AdminCaller, active: bool | None = None
) -> Page[AdvancedOut]:
    rows, has_more = await crud_pool.first_page(
        session, crud_advanced.list_stmt(active=active)
    )
    return Page[AdvancedOut](
        items=[advanced_out(r) for r in rows], next_cursor=None, has_more=has_more
    )


@router.post("/advanced-courses", response_model=AdvancedOut, status_code=201)
async def create_advanced(
    body: AdvancedIn, session: DbSession, caller: AdminCaller
) -> AdvancedOut:
    row = await admin.create_advanced(
        session, actor=f"admin:{caller.id}", fields=body.fields()
    )
    return advanced_out(row)


@router.patch(
    "/advanced-courses/{advanced_course_id}",
    response_model=AdvancedOut,
    responses={404: {"description": "심화 과정이 없음"}},
)
async def patch_advanced(
    advanced_course_id: str,
    body: AdvancedPatchIn,
    session: DbSession,
    caller: AdminCaller,
) -> AdvancedOut:
    row = (
        await crud_advanced.get_advanced(session, advanced_course_id)
        if valid_text_id(advanced_course_id)
        else None
    )
    if row is None:
        raise NotFound("심화 과정이 없습니다")
    await admin.patch_advanced(
        session,
        actor=f"admin:{caller.id}",
        advanced_id=row.id,
        changes=body.changes(),
    )
    return advanced_out(row)
