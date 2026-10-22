"""관리자 강사 끝점(AdminCaller, T3 계획 결정 vi·vii·xviii): 목록 · 상세 · 승인·반려·정지·해제 · 메모.

- 목록은 키셋 커서 {items, next_cursor, has_more}, (created_at, id) 내림차순이다. 첫 WHERE 는 주체 범위
  (crud.instructor.list_stmt → instructor_scope)다. status 로 거르고 q 는 이름·소속·이메일 부분 일치다.
  깨진 커서는 422 이고 violations[].loc 는 ["query", "cursor"] 다(T2a 꼴).
- 전이는 service.instructors.status.transition 하나가 한다: 강사 행 FOR UPDATE → 표(기획안 A2 4행 5전이) 밖이면
  409 + current_status → 상태 → 정지면 그 강사의 산 세션 폐기 → audit 1행 → 승인·반려면 outbox 1행.
- 반려는 사유 1~500자가 필수다(없거나 공백뿐 422, 결정 vii). 승인은 대기 상태면 되고 서류는 조건이 아니다(결정 xviii).
- 메모는 바뀌었을 때만 audit instructor.memo 1행(detail 없음)을 이 끝점이 쓴다. 같은 값이면 audit 없음.
- 응답에 서류 href 는 없다. 관리자의 서류 열람은 audit 끝점 하나다(instructor_documents, 결정 x).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import AdminCaller, DbSession
from classfit.app.endpoints.instructors import document_outs, instructor_tags
from classfit.core.errors import NotFound
from classfit.crud import instructor as crud_instructor
from classfit.crud import instructor_document as crud_document
from classfit.crud.audit import insert_audit
from classfit.crud.page import keyset_page
from classfit.crud.scope import Subject
from classfit.models import Instructor
from classfit.schemas.auth import no_control_chars
from classfit.schemas.instructor import (
    DocumentAdminOut,
    InstructorAdminItemOut,
    InstructorAdminOut,
    InstructorStatus,
    MemoIn,
    RejectIn,
)
from classfit.schemas.page import Page
from classfit.service.auth.sessions import Principal
from classfit.service.instructors import status as instructor_status

router = APIRouter(prefix="/v1/admin", tags=["admin-instructors"])

_NOT_FOUND = {404: {"description": "강사가 없음"}}
_TRANSITION = {
    **_NOT_FOUND,
    409: {"description": "상태 전이표 밖(current_status 칸에 지금 상태)"},
}


def _invalid_query(field: str, msg: str) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("query", field), "msg": msg, "type": "value_error"}]
    )


def query_text(value: str | None, field: str = "q") -> str | None:
    """질의 글자: 앞뒤 공백 제거, 제어 문자 422, 비면 None."""
    if value is None:
        return None
    try:
        text = no_control_chars(value.strip())
    except ValueError as exc:
        raise _invalid_query(field, str(exc)) from None
    return text or None


async def instructor_or_404(
    session: AsyncSession, caller: Subject, instructor_id: int
) -> Instructor:
    row = await crud_instructor.get_instructor(session, caller, instructor_id)
    if row is None:
        raise NotFound("강사가 없습니다")
    return row


async def _required_count(session: AsyncSession) -> int:
    return sum(
        1 for t in await crud_document.list_document_types(session) if t.required
    )


async def admin_out(session: AsyncSession, row: Instructor) -> InstructorAdminOut:
    tags = await instructor_tags(session, [row.id])
    documents = await document_outs(session, row.id)
    return InstructorAdminOut(
        id=row.id,
        email=row.email,
        name=row.name,
        phone=row.phone,
        org=row.org,
        status=row.status,  # type: ignore[arg-type]  # CHECK 가 네 값으로 막는다
        applied_at=row.created_at,
        tags=tags[row.id],
        # 목록(crud.instructor.document_counts)과 같은 셈: 낸 필수 서류 수 / 필수 서류 수
        documents_submitted=sum(
            1 for d in documents if d.required and d.submitted_at is not None
        ),
        documents_required=sum(1 for d in documents if d.required),
        intro=row.intro,
        career=list(row.career),
        reject_reason=row.reject_reason,
        memo=row.memo,
        documents=[
            DocumentAdminOut.model_validate(d.model_dump(exclude={"href"}))
            for d in documents
        ],
    )


async def _transition(
    session: AsyncSession,
    caller: Principal,
    instructor_id: int,
    action: str,
    reason: str | None = None,
) -> InstructorAdminOut:
    row = await instructor_status.transition(
        session,
        instructor_id=instructor_id,
        action=action,
        actor=f"admin:{caller.id}",
        reason=reason,
    )
    return await admin_out(session, row)


@router.get("/instructors", response_model=Page[InstructorAdminItemOut])
async def list_instructors(
    session: DbSession,
    caller: AdminCaller,
    status: InstructorStatus | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[InstructorAdminItemOut]:
    stmt = crud_instructor.list_stmt(caller, status, query_text(q))
    try:
        items, next_cursor, has_more = await keyset_page(session, stmt, cursor, limit)
    except ValueError:
        raise _invalid_query("cursor", "깨진 커서입니다") from None
    ids = [r.id for r in items]
    tags = await instructor_tags(session, ids)
    submitted = await crud_instructor.document_counts(session, ids)
    required = await _required_count(session)
    return Page[InstructorAdminItemOut](
        items=[
            InstructorAdminItemOut(
                id=r.id,
                email=r.email,
                name=r.name,
                phone=r.phone,
                org=r.org,
                status=r.status,  # type: ignore[arg-type]  # CHECK 가 네 값으로 막는다
                applied_at=r.created_at,
                tags=tags[r.id],
                documents_submitted=submitted.get(r.id, 0),
                documents_required=required,
            )
            for r in items
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get(
    "/instructors/{instructor_id}",
    response_model=InstructorAdminOut,
    responses=_NOT_FOUND,
)
async def get_instructor(
    instructor_id: int, session: DbSession, caller: AdminCaller
) -> InstructorAdminOut:
    return await admin_out(
        session, await instructor_or_404(session, caller, instructor_id)
    )


@router.post(
    "/instructors/{instructor_id}:approve",
    response_model=InstructorAdminOut,
    responses=_TRANSITION,
)
async def approve_instructor(
    instructor_id: int, session: DbSession, caller: AdminCaller
) -> InstructorAdminOut:
    """대기 → 승인. audit 1 + outbox 1(kind instructor_approved)."""
    return await _transition(session, caller, instructor_id, "approve")


@router.post(
    "/instructors/{instructor_id}:reject",
    response_model=InstructorAdminOut,
    responses={**_TRANSITION, 422: {"description": "사유가 없거나 공백뿐"}},
)
async def reject_instructor(
    instructor_id: int, body: RejectIn, session: DbSession, caller: AdminCaller
) -> InstructorAdminOut:
    """대기 → 반려. 사유는 행과 audit detail 에 남고, 메일 본문은 audit 의 사유를 쓴다."""
    return await _transition(session, caller, instructor_id, "reject", body.reason)


@router.post(
    "/instructors/{instructor_id}:suspend",
    response_model=InstructorAdminOut,
    responses=_TRANSITION,
)
async def suspend_instructor(
    instructor_id: int, session: DbSession, caller: AdminCaller
) -> InstructorAdminOut:
    """승인 → 정지. 그 강사의 산 세션을 전부 폐기한다(옛 토큰 401)."""
    return await _transition(session, caller, instructor_id, "suspend")


@router.post(
    "/instructors/{instructor_id}:unsuspend",
    response_model=InstructorAdminOut,
    responses=_TRANSITION,
)
async def unsuspend_instructor(
    instructor_id: int, session: DbSession, caller: AdminCaller
) -> InstructorAdminOut:
    """정지 → 승인. 폐기한 세션은 되살리지 않는다(다시 로그인)."""
    return await _transition(session, caller, instructor_id, "unsuspend")


@router.patch(
    "/instructors/{instructor_id}/memo",
    response_model=InstructorAdminOut,
    responses=_NOT_FOUND,
)
async def patch_memo(
    instructor_id: int, body: MemoIn, session: DbSession, caller: AdminCaller
) -> InstructorAdminOut:
    row = await instructor_or_404(session, caller, instructor_id)
    if await crud_instructor.update_instructor(session, row, memo=body.memo):
        await insert_audit(
            session,
            actor=f"admin:{caller.id}",
            action="instructor.memo",
            target_type="instructor",
            target_id=str(row.id),
        )
    return await admin_out(session, row)
