"""강사 커리큘럼 끝점(InstructorCaller, T4 계획 결정 i·vi·xi·xv·xix).

- GET·POST /v1/me/curricula: 내 커리큘럼(비활성 포함, 한 쪽 500) · 등록 201(id cur-<강사 id>-<n>, 차시표 없이).
- GET·PATCH·DELETE /v1/me/curricula/{curriculum_id}: 404(없음) → 403(남의 것) → 409(비활성, PATCH·차시표 PUT 만)
  (service.pool.curricula). DELETE 는 active 를 끈다(결정 xi). 이미 비활성이면 204 + audit 없음.
- PUT /v1/me/curricula/{curriculum_id}/slots 본문 {slots: [{day, slot, title, description?}]}: 차시표를 통째 바꾼다.
  1 ≤ day ≤ days · 1 ≤ slot ≤ slots_per_day · (day, slot) 중복 없음. 어기면 422 violations
  (loc ["body", "slots", i, "day"|"slot"] type out_of_grid · ["body", "slots", i] type duplicate). 같은 차시표는 audit 없음.
- PATCH 로 days·시각·교시를 줄여 기존 차시가 격자 밖이 되면 422 loc ["body", <바꾼 격자 칸>] type slots_out_of_grid
  (먼저 차시표를 줄인다). 한쪽 시각만 바꿔 저장값과 합쳐 시작 ≥ 끝이 되면 422 type time_order.
- 내용 칸·차시표가 바뀌면 reviewed 가 거짓으로 돌아가고 pub·active 는 그대로다(결정 vi). 차시표 교체와 수정은
  커리큘럼 행을 FOR UPDATE 로 잠근 뒤 판정한다(service, 결정 xix).
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import DbSession, InstructorCaller
from classfit.app.endpoints.pool import files_by_owner, id_or_404
from classfit.app.errors import AppError
from classfit.crud import curriculum as crud_curriculum
from classfit.crud import pool as crud_pool
from classfit.models import Curriculum, CurriculumSlot
from classfit.schemas.curriculum import (
    CurriculumIn,
    CurriculumOut,
    CurriculumPatchIn,
    SlotOut,
    SlotsPutIn,
)
from classfit.schemas.page import Page
from classfit.schemas.pool import PoolFileOut
from classfit.service.pool import curricula
from classfit.service.pool.common import PoolViolation
from classfit.service.rules.pool import slots_per_day

router = APIRouter(prefix="/v1/me", tags=["curricula"])

FILE_KIND = "curriculum_file"
_NOT_FOUND = "커리큘럼이 없습니다"
_ONE = {
    403: {"description": "남의 커리큘럼"},
    404: {"description": "커리큘럼이 없음"},
}
_WRITE = {
    **_ONE,
    409: {"description": "사용 중지된 커리큘럼"},
    422: {"description": "본문 모양 · 격자 밖 차시 · (day, slot) 중복 · 시각 순서"},
}


def violation_error(exc: PoolViolation) -> AppError:
    """service 의 422 예외(NotEditable·GridViolation)를 problem+json 422 로."""
    return AppError(422, exc.detail, title="요청 검증 실패", violations=exc.violations)


def curriculum_out(
    row: Curriculum, slots: list[CurriculumSlot], files: list[PoolFileOut]
) -> CurriculumOut:
    return CurriculumOut(
        id=row.id,
        title=row.title,
        job_groups=list(row.job_groups),
        difficulty=row.difficulty,
        days=row.days,
        start_time=row.start_time,
        end_time=row.end_time,
        slot_min=row.slot_min,
        break_min=row.break_min,
        slots_per_day=slots_per_day(
            row.start_time, row.end_time, row.slot_min, row.break_min
        ),
        goal=row.goal,
        output=row.output,
        slots=[
            SlotOut(day=s.day, slot=s.slot, title=s.title, description=s.description)
            for s in slots
        ],
        files=files,
        reviewed=row.reviewed,
        reviewed_at=row.reviewed_at,
        pub=row.pub,
        active=row.active,
    )


async def curriculum_outs(
    session: AsyncSession, rows: list[Curriculum]
) -> list[CurriculumOut]:
    """차시·파일을 한 번씩 모아 읽어 출력으로(목록·단건 공용)."""
    ids = [r.id for r in rows]
    slots = await crud_curriculum.slots_by_curriculum(session, ids)
    files = await files_by_owner(session, FILE_KIND, ids)
    return [curriculum_out(r, slots.get(r.id, []), files.get(r.id, [])) for r in rows]


async def _one_out(
    session: AsyncSession, instructor_id: int, curriculum_id: str
) -> CurriculumOut:
    row = await curricula.get_own_curriculum(
        session, instructor_id=instructor_id, curriculum_id=curriculum_id
    )
    return (await curriculum_outs(session, [row]))[0]


@router.get("/curricula", response_model=Page[CurriculumOut])
async def list_curricula(
    session: DbSession, caller: InstructorCaller
) -> Page[CurriculumOut]:
    rows, has_more = await crud_pool.first_page(
        session, crud_curriculum.list_stmt(caller)
    )
    return Page[CurriculumOut](
        items=await curriculum_outs(session, rows),
        next_cursor=None,
        has_more=has_more,
    )


@router.post("/curricula", response_model=CurriculumOut, status_code=201)
async def create_curriculum(
    body: CurriculumIn, session: DbSession, caller: InstructorCaller
) -> CurriculumOut:
    row = await curricula.create_curriculum(
        session, instructor_id=caller.id, fields=body.fields()
    )
    return curriculum_out(row, [], [])


@router.get("/curricula/{curriculum_id}", response_model=CurriculumOut, responses=_ONE)
async def get_curriculum(
    curriculum_id: str, session: DbSession, caller: InstructorCaller
) -> CurriculumOut:
    return await _one_out(session, caller.id, id_or_404(curriculum_id, _NOT_FOUND))


@router.patch(
    "/curricula/{curriculum_id}", response_model=CurriculumOut, responses=_WRITE
)
async def patch_curriculum(
    curriculum_id: str,
    body: CurriculumPatchIn,
    session: DbSession,
    caller: InstructorCaller,
) -> CurriculumOut:
    curriculum_id = id_or_404(curriculum_id, _NOT_FOUND)
    try:
        await curricula.patch_curriculum(
            session,
            instructor_id=caller.id,
            curriculum_id=curriculum_id,
            changes=body.changes(),
        )
    except PoolViolation as exc:
        raise violation_error(exc) from None
    return await _one_out(session, caller.id, curriculum_id)


@router.put(
    "/curricula/{curriculum_id}/slots", response_model=CurriculumOut, responses=_WRITE
)
async def put_slots(
    curriculum_id: str,
    body: SlotsPutIn,
    session: DbSession,
    caller: InstructorCaller,
) -> CurriculumOut:
    curriculum_id = id_or_404(curriculum_id, _NOT_FOUND)
    try:
        await curricula.replace_slots(
            session,
            instructor_id=caller.id,
            curriculum_id=curriculum_id,
            slots=[s.fields() for s in body.slots],
        )
    except PoolViolation as exc:
        raise violation_error(exc) from None
    return await _one_out(session, caller.id, curriculum_id)


@router.delete(
    "/curricula/{curriculum_id}",
    status_code=204,
    response_class=Response,
    responses=_ONE,
)
async def delete_curriculum(
    curriculum_id: str, session: DbSession, caller: InstructorCaller
) -> Response:
    """사용 중지(active 거짓). 행·차시·파일은 남는다."""
    await curricula.deactivate_curriculum(
        session,
        instructor_id=caller.id,
        curriculum_id=id_or_404(curriculum_id, _NOT_FOUND),
    )
    return Response(status_code=204)
