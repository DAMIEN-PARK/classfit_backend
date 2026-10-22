"""강사 가입·본인 끝점(T3 계획 결정 i·ii·iii·v·xi·xii·xiii).

- POST /v1/instructors/email-codes(인증 없음, 202): 이메일당 열린 인증 요청 1행 + outbox 1행(params 는 요청 id 뿐).
  코드는 여기서 만들지 않는다. 발송 쪽(scripts.outbox_preview --apply)이 만들고 해시를 저장한다. 이미 가입된 이메일 409.
- POST /v1/instructors(인증 없음, 201): 코드 대조 → 강사 행(pending) · 태그 · 약관 판본. 코드 실패 셋은 예외가 아니라
  problem() 반환이다(tries·auth_attempt 행이 커밋되게, Design 5절 7): 틀림·발송 전·열린 요청 없음 422
  email-code-mismatch · 만료 410 email-code-expired · 시도 초과 429 email-code-locked(Retry-After 없음).
  이미 가입 409 · 사용 중지 태그 422 violations[{loc: ["body","tags",i], type: "tag_inactive"}] 는 예외라 롤백된다.
- GET·PATCH /v1/me · POST /v1/me:reapply(InstructorCaller): 대기·반려 강사도 쓴다(결정 v). 재신청은 rejected 만,
  아니면 409(audit 은 service 가 쓴다). 응답의 서류 href 는 본인만 여는 파일 주소다(결정 x).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import DbSession, InstructorCaller
from classfit.app.errors import AppError, problem
from classfit.core.config import Settings
from classfit.core.errors import NotFound
from classfit.crud import instructor as crud_instructor
from classfit.crud import instructor_document as crud_document
from classfit.crud import tag as crud_tag
from classfit.crud.scope import Subject
from classfit.models import Instructor, Tag
from classfit.schemas.instructor import (
    DocumentOut,
    EmailCodeRequestIn,
    EmailCodeRequestOut,
    InstructorMeOut,
    InstructorPatchIn,
    InstructorSignupIn,
    InstructorTagOut,
)
from classfit.service.auth.sessions import Principal
from classfit.service.files.store import href_for
from classfit.service.instructors import profile, signup
from classfit.service.instructors.signup import InactiveTags

router = APIRouter(prefix="/v1", tags=["instructors"])

# 결과 → (상태, problem type, 안내). 셋 다 같은 이메일로 다시 발송받으면 풀린다
_CODE_FAILURES: dict[str, tuple[int, str, str]] = {
    "mismatch": (422, "/problems/email-code-mismatch", "인증 코드가 맞지 않습니다"),
    "expired": (
        410,
        "/problems/email-code-expired",
        "인증 코드가 만료됐습니다. 다시 발송받으세요",
    ),
    "locked": (
        429,
        "/problems/email-code-locked",
        "인증 코드를 너무 많이 틀렸습니다. 다시 발송받으세요",
    ),
}

_SIGNUP_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"description": "이미 가입된 이메일"},
    410: {"description": "인증 코드 만료(/problems/email-code-expired)"},
    422: {
        "description": "인증 코드 틀림·발송 전·요청 없음(/problems/email-code-mismatch)"
        " · 본문 모양 · 사용 중지 태그(violations type tag_inactive)"
    },
    429: {"description": "인증 코드 시도 초과(/problems/email-code-locked)"},
}


def tag_out(tag: Tag) -> InstructorTagOut:
    return InstructorTagOut(id=tag.id, name=tag.name, group=tag.group_name)


def inactive_tags_error(exc: InactiveTags) -> AppError:
    """중지된 이름의 자리(받은 목록 기준)마다 violations 한 줄. 예외라 그 요청은 아무 행도 남기지 않는다."""
    violations = [
        {
            "loc": ["body", "tags", i],
            "msg": "사용 중지된 분야라 새로 붙일 수 없습니다",
            "type": "tag_inactive",
        }
        for i in exc.indexes
    ]
    return AppError(
        422,
        "사용 중지된 분야는 새로 붙일 수 없습니다",
        title="요청 검증 실패",
        violations=violations,
    )


async def instructor_tags(
    session: AsyncSession, instructor_ids: list[int]
) -> dict[int, list[InstructorTagOut]]:
    found = await crud_tag.tags_by_instructor(session, instructor_ids)
    return {i: [tag_out(t) for t in found.get(i, [])] for i in instructor_ids}


async def document_outs(session: AsyncSession, instructor_id: int) -> list[DocumentOut]:
    """서류 종류마다 한 줄(종류 정렬 순서). 미제출은 submitted_at·size·href 가 null 이다."""
    return [
        DocumentOut(
            type_id=kind.id,
            name=kind.name,
            required=kind.required,
            submitted_at=doc.submitted_at if doc is not None else None,
            size=stored.size if stored is not None else None,
            href=href_for(stored.key) if stored is not None else None,
        )
        for kind, doc, stored in await crud_document.list_documents(
            session, instructor_id
        )
    ]


async def me_out(session: AsyncSession, row: Instructor) -> InstructorMeOut:
    tags = await instructor_tags(session, [row.id])
    return InstructorMeOut(
        id=row.id,
        email=row.email,
        name=row.name,
        phone=row.phone,
        org=row.org,
        intro=row.intro,
        career=list(row.career),
        status=row.status,  # type: ignore[arg-type]  # CHECK 가 네 값으로 막는다
        reject_reason=row.reject_reason,
        terms_version=row.terms_version,
        terms_agreed_at=row.terms_agreed_at,
        tags=tags[row.id],
        documents=await document_outs(session, row.id),
        created_at=row.created_at,
    )


async def _own_row(session: AsyncSession, subject: Subject) -> Instructor:
    row = await crud_instructor.get_instructor(session, subject, subject.id)
    if row is None:
        raise NotFound("강사 계정이 없습니다")
    return row


@router.post(
    "/instructors/email-codes",
    response_model=EmailCodeRequestOut,
    status_code=202,
    responses={409: {"description": "이미 가입된 이메일"}},
)
async def request_email_code(
    body: EmailCodeRequestIn, session: DbSession
) -> EmailCodeRequestOut:
    """다시 부르면 같은 요청 행에 outbox 만 한 줄 더한다. 새로 발송된 코드가 옛 코드를 무효로 만든다."""
    await signup.request_email_code(session, email=body.email)
    return EmailCodeRequestOut(email=body.email)


@router.post(
    "/instructors",
    response_model=InstructorMeOut,
    status_code=201,
    responses=_SIGNUP_RESPONSES,
)
async def signup_instructor(
    body: InstructorSignupIn, request: Request, session: DbSession
) -> InstructorMeOut | JSONResponse:
    settings: Settings = request.app.state.settings
    client = request.client.host if request.client else "unknown"
    try:
        result = await signup.signup(
            session,
            settings,
            email=body.email,
            code=body.code,
            password=body.password,
            name=body.name,
            phone=body.phone,
            org=body.org,
            intro=body.intro,
            career=body.career,
            tags=body.tags,
            client=client,
        )
    except InactiveTags as exc:
        raise inactive_tags_error(exc) from None
    if result.outcome != "ok" or result.instructor_id is None:
        status, type_, detail = _CODE_FAILURES[result.outcome]
        return problem(request, status=status, type=type_, detail=detail)
    row = await _own_row(session, Principal(type="instructor", id=result.instructor_id))
    return await me_out(session, row)


@router.get("/me", response_model=InstructorMeOut)
async def get_me(session: DbSession, caller: InstructorCaller) -> InstructorMeOut:
    return await me_out(session, await _own_row(session, caller))


@router.patch(
    "/me",
    response_model=InstructorMeOut,
    responses={422: {"description": "본문 모양 · 분야 0개 · 사용 중지 태그"}},
)
async def patch_me(
    body: InstructorPatchIn, session: DbSession, caller: InstructorCaller
) -> InstructorMeOut:
    row = await _own_row(session, caller)
    try:
        await profile.patch_profile(session, row, body.changes())
    except InactiveTags as exc:
        raise inactive_tags_error(exc) from None
    return await me_out(session, row)


@router.post(
    "/me:reapply",
    response_model=InstructorMeOut,
    responses={409: {"description": "반려 상태가 아님"}},
)
async def reapply(session: DbSession, caller: InstructorCaller) -> InstructorMeOut:
    """반려 → 대기. 반려 사유는 행에서 지우고 audit detail 에만 남는다(결정 xii)."""
    row = await profile.reapply(
        session, instructor_id=caller.id, actor=f"instructor:{caller.id}"
    )
    return await me_out(session, row)
