"""관리자 과정 풀·커리큘럼 끝점(AdminCaller, T4 계획 결정 i·v·vi·xii·xviii).

- GET /v1/admin/pool?source=&job=&difficulty=&q=&active=&reviewed=: 비활성 포함 한 쪽 500(커서 없음). 고유 과정은
  owner{id, name}, 행마다 역량 강사 수(capable_count).
- POST /v1/admin/pool/ax: AX 과정 추가. id ax-custom-<n> · reviewed 참 · pub 거짓 · active 참(관리자.html:1476).
  이 라우트를 /pool/{pool_id} 보다 먼저 등록한다(메서드가 달라도 순서를 고정해 둔다).
- GET·PATCH /v1/admin/pool/{pool_id}: 상세는 내용 전부 + 역량 강사 이름 + 파일. PATCH 는 AX 행에 내용 + active·pub,
  고유 과정 행에 reviewed·pub·active 만(결정 xviii). 고칠 수 없는 칸은 422 violations type not_editable.
  플래그는 reviewed → pub → active 순으로 적용하고, 미검토 항목의 pub 켜기는 409 + reviewed: false(결정 v).
  검토 해제는 pub 도 끈다. 바뀐 칸이 있을 때만 audit pool_course.update 1행.
- GET /v1/admin/curricula?reviewed=&active= · GET·PATCH /v1/admin/curricula/{curriculum_id}: 플래그 셋만 고친다.
- 관리자 끝점은 공개 카탈로그를 돌려주지 않는다(ADR-004 결정 4). 카탈로그는 crud.catalog.published_catalog() 다.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import AdminCaller, DbSession
from classfit.app.endpoints.curricula import curriculum_outs, violation_error
from classfit.app.endpoints.pool import (
    Source,
    base_fields,
    content_fields,
    files_by_owner,
    pool_filters,
    valid_text_id,
)
from classfit.core.errors import NotFound
from classfit.crud import curriculum as crud_curriculum
from classfit.crud import pool as crud_pool
from classfit.crud.scope import Subject
from classfit.models import Curriculum, PoolCourse
from classfit.schemas.curriculum import CurriculumAdminItemOut, CurriculumFlagsPatchIn
from classfit.schemas.page import Page
from classfit.schemas.pool import (
    AxCourseCreateIn,
    CapableOut,
    OwnerOut,
    PoolAdminItemOut,
    PoolAdminOut,
    PoolAdminPatchIn,
)
from classfit.service.pool import admin
from classfit.service.pool.common import PoolViolation

router = APIRouter(prefix="/v1/admin", tags=["admin-pool"])

_POOL_404 = {404: {"description": "과정이 없음"}}
_CURRICULUM_404 = {404: {"description": "커리큘럼이 없음"}}


def _owner(row: PoolCourse, names: dict[int, str]) -> OwnerOut | None:
    """고유 과정의 작성 강사(관리자 출력에만). AX 는 None."""
    owner_id = row.owner_instructor_id
    if owner_id is None:
        return None
    return OwnerOut(id=owner_id, name=names.get(owner_id, ""))


def _flags(row: PoolCourse) -> dict[str, Any]:
    return {
        "reviewed": row.reviewed,
        "reviewed_at": row.reviewed_at,
        "pub": row.pub,
        "active": row.active,
    }


async def _pool_or_404(
    session: AsyncSession, caller: Subject, pool_id: str
) -> PoolCourse:
    row = (
        await crud_pool.get_pool_course(session, caller, pool_id)
        if valid_text_id(pool_id)
        else None
    )
    if row is None:
        raise NotFound("과정이 없습니다")
    return row


async def pool_admin_out(session: AsyncSession, row: PoolCourse) -> PoolAdminOut:
    names = await crud_pool.owner_names(session, [row.owner_instructor_id])
    capable = await crud_pool.capable_instructors(session, row.id)
    files = await files_by_owner(session, "pool_course_file", [row.id])
    return PoolAdminOut(
        **base_fields(row),
        **content_fields(row),
        **_flags(row),
        owner=_owner(row, names),
        capable_count=len(capable),
        capable=[CapableOut(instructor_id=i, name=n) for i, n in capable],
        files=files.get(row.id, []),
    )


async def _curriculum_or_404(
    session: AsyncSession, caller: Subject, curriculum_id: str
) -> Curriculum:
    row = (
        await crud_curriculum.get_curriculum(session, caller, curriculum_id)
        if valid_text_id(curriculum_id)
        else None
    )
    if row is None:
        raise NotFound("커리큘럼이 없습니다")
    return row


async def curriculum_admin_outs(
    session: AsyncSession, rows: list[Curriculum]
) -> list[CurriculumAdminItemOut]:
    names = await crud_pool.owner_names(session, [r.instructor_id for r in rows])
    outs = await curriculum_outs(session, rows)
    return [
        CurriculumAdminItemOut(
            **out.model_dump(),
            owner=OwnerOut(id=row.instructor_id, name=names.get(row.instructor_id, "")),
        )
        for row, out in zip(rows, outs, strict=True)
    ]


@router.get("/pool", response_model=Page[PoolAdminItemOut])
async def list_pool(
    session: DbSession,
    caller: AdminCaller,
    source: Source | None = None,
    job: Annotated[str | None, Query(max_length=50)] = None,
    difficulty: Annotated[str | None, Query(max_length=10)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    active: bool | None = None,
    reviewed: bool | None = None,
) -> Page[PoolAdminItemOut]:
    job, difficulty, text = pool_filters(job, difficulty, q)
    stmt = crud_pool.list_stmt(
        caller,
        source=source,
        job=job,
        difficulty=difficulty,
        q=text,
        active=active,
        reviewed=reviewed,
    )
    rows, has_more = await crud_pool.first_page(session, stmt)
    counts = await crud_pool.capable_counts(session, [r.id for r in rows])
    names = await crud_pool.owner_names(session, [r.owner_instructor_id for r in rows])
    return Page[PoolAdminItemOut](
        items=[
            PoolAdminItemOut(
                **base_fields(r),
                **_flags(r),
                owner=_owner(r, names),
                capable_count=counts.get(r.id, 0),
            )
            for r in rows
        ],
        next_cursor=None,
        has_more=has_more,
    )


@router.post("/pool/ax", response_model=PoolAdminOut, status_code=201)
async def create_ax_course(
    body: AxCourseCreateIn, session: DbSession, caller: AdminCaller
) -> PoolAdminOut:
    row = await admin.create_ax_course(
        session, actor=f"admin:{caller.id}", fields=body.fields()
    )
    return await pool_admin_out(session, row)


@router.get("/pool/{pool_id}", response_model=PoolAdminOut, responses=_POOL_404)
async def get_pool(
    pool_id: str, session: DbSession, caller: AdminCaller
) -> PoolAdminOut:
    return await pool_admin_out(session, await _pool_or_404(session, caller, pool_id))


@router.patch(
    "/pool/{pool_id}",
    response_model=PoolAdminOut,
    responses={
        **_POOL_404,
        409: {"description": "미검토 항목 공개(reviewed: false 칸)"},
        422: {"description": "본문 모양 · 고칠 수 없는 칸(type not_editable)"},
    },
)
async def patch_pool(
    pool_id: str, body: PoolAdminPatchIn, session: DbSession, caller: AdminCaller
) -> PoolAdminOut:
    row = await _pool_or_404(session, caller, pool_id)
    try:
        await admin.patch_pool_course(
            session, actor=f"admin:{caller.id}", pool_id=row.id, changes=body.changes()
        )
    except PoolViolation as exc:
        raise violation_error(exc) from None
    return await pool_admin_out(session, row)


@router.get("/curricula", response_model=Page[CurriculumAdminItemOut])
async def list_curricula(
    session: DbSession,
    caller: AdminCaller,
    reviewed: bool | None = None,
    active: bool | None = None,
) -> Page[CurriculumAdminItemOut]:
    stmt = crud_curriculum.list_stmt(caller, reviewed=reviewed, active=active)
    rows, has_more = await crud_pool.first_page(session, stmt)
    return Page[CurriculumAdminItemOut](
        items=await curriculum_admin_outs(session, rows),
        next_cursor=None,
        has_more=has_more,
    )


@router.get(
    "/curricula/{curriculum_id}",
    response_model=CurriculumAdminItemOut,
    responses=_CURRICULUM_404,
)
async def get_curriculum(
    curriculum_id: str, session: DbSession, caller: AdminCaller
) -> CurriculumAdminItemOut:
    row = await _curriculum_or_404(session, caller, curriculum_id)
    return (await curriculum_admin_outs(session, [row]))[0]


@router.patch(
    "/curricula/{curriculum_id}",
    response_model=CurriculumAdminItemOut,
    responses={
        **_CURRICULUM_404,
        409: {"description": "미검토 커리큘럼 공개(reviewed: false 칸)"},
    },
)
async def patch_curriculum(
    curriculum_id: str,
    body: CurriculumFlagsPatchIn,
    session: DbSession,
    caller: AdminCaller,
) -> CurriculumAdminItemOut:
    row = await _curriculum_or_404(session, caller, curriculum_id)
    await admin.patch_curriculum_flags(
        session,
        actor=f"admin:{caller.id}",
        curriculum_id=row.id,
        changes=body.changes(),
    )
    return (await curriculum_admin_outs(session, [row]))[0]
