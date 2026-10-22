"""강사 역량(가능 표시) 끝점(InstructorCaller, T4 계획 결정 i·x·xii).

- GET /v1/me/capabilities: 내 역량 전부(한 쪽 500, 커서 없음). 과정 제목·메모·파일을 같이 준다. 순서는 과정 id.
- PUT /v1/me/capabilities/{pool_id} 본문 {memo?}: 없으면 만든다(201), 있으면 메모를 바꾼다(200). AX 과정·내 고유 과정·
  남의 고유 과정 모두 대상이다(소유 판정 없음). 없는 과정 404, 비활성 과정 409(결정 i·x). 본문이 없거나 memo 가
  null·빈 글자면 메모를 비운다. 만들기 audit capability.create, 메모가 바뀌었을 때만 capability.update.
- DELETE /v1/me/capabilities/{pool_id}: 역량 행을 지운다. 그 역량의 파일 행과 stored_file 행을 같은 트랜잭션에서
  먼저 지운다(바이트는 gc 몫). 없으면 404.
- 응답에 남의 이름·이메일이 없다. 역량 파일 href 는 본인과 관리자만 연다(OWNER_KINDS capability_file).
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from classfit.app.deps import DbSession, InstructorCaller
from classfit.app.endpoints.pool import files_by_owner, valid_text_id
from classfit.core.errors import NotFound
from classfit.crud import capability as crud_capability
from classfit.crud import pool as crud_pool
from classfit.models import Capability
from classfit.schemas.page import Page
from classfit.schemas.pool import CapabilityIn, CapabilityOut, PoolFileOut
from classfit.service.pool import capabilities

router = APIRouter(prefix="/v1/me", tags=["capabilities"])

FILE_KIND = "capability_file"


def _pool_id_or_404(pool_id: str) -> str:
    if not valid_text_id(pool_id):
        raise NotFound("과정이 없습니다")
    return pool_id


def capability_out(
    row: Capability, title: str, files: list[PoolFileOut]
) -> CapabilityOut:
    return CapabilityOut(
        pool_id=row.pool_course_id,
        title=title,
        memo=row.memo,
        files=files,
        created_at=row.created_at,
    )


@router.get("/capabilities", response_model=Page[CapabilityOut])
async def list_capabilities(
    session: DbSession, caller: InstructorCaller
) -> Page[CapabilityOut]:
    pairs, has_more = await crud_capability.list_capabilities(
        session, caller, crud_pool.LIST_LIMIT
    )
    files = await files_by_owner(session, FILE_KIND, [c.id for c, _ in pairs])
    return Page[CapabilityOut](
        items=[capability_out(c, p.title, files.get(c.id, [])) for c, p in pairs],
        next_cursor=None,
        has_more=has_more,
    )


@router.put(
    "/capabilities/{pool_id}",
    response_model=CapabilityOut,
    status_code=201,
    responses={
        200: {"description": "이미 있던 역량의 메모를 바꿈", "model": CapabilityOut},
        404: {"description": "과정이 없음"},
        409: {"description": "비활성 과정"},
    },
)
async def put_capability(
    pool_id: str,
    response: Response,
    session: DbSession,
    caller: InstructorCaller,
    body: CapabilityIn | None = None,
) -> CapabilityOut:
    row, created = await capabilities.put_capability(
        session,
        instructor_id=caller.id,
        pool_id=_pool_id_or_404(pool_id),
        memo=body.memo if body is not None else None,
    )
    course = await crud_pool.get_pool_course_any(session, row.pool_course_id)
    if course is None:  # 방금 판정한 과정이다
        raise RuntimeError(f"역량의 과정 {row.pool_course_id} 를 다시 못 읽었다")
    if not created:
        response.status_code = 200
    files = await files_by_owner(session, FILE_KIND, [row.id])
    return capability_out(row, course.title, files.get(row.id, []))


@router.delete(
    "/capabilities/{pool_id}",
    status_code=204,
    response_class=Response,
    responses={404: {"description": "과정이 없음 · 역량이 없음"}},
)
async def delete_capability(
    pool_id: str, session: DbSession, caller: InstructorCaller
) -> Response:
    await capabilities.remove_capability(
        session, instructor_id=caller.id, pool_id=_pool_id_or_404(pool_id)
    )
    return Response(status_code=204)
