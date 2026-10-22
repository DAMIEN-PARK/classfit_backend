"""강의 끝점(관리자만, AdminCaller): 목록·개설·조회·수정·삭제·보관·상태 지정/되돌리기.

- 개설 POST /v1/admin/courses 는 open_course() 하나로 강의·일차·초대코드·audit 을 한 트랜잭션에 쓴다.
- 목록은 키셋 커서 {items, next_cursor, has_more}. 첫 WHERE 는 주체 범위(crud.scope.course_scope)다.
  깨진 커서는 422 problem 이고 violations[].loc 는 ["query", "cursor"] 다.
- 응답 status 는 오늘(Today, Asia/Seoul) 기준 계산값이다. 목록 필터는 같은 규칙의 SQL 판으로 거른다.
- 상태를 바꾸는 요청(개설·수정·삭제·보관·상태 지정·되돌리기)은 audit_log 1행을 같은 트랜잭션에 쓴다
  (target course·id 글자, T2a 계획 결정 viii). 멱등 호출(이미 보관 · 같은 값 PATCH)은 audit 을 쓰지 않는다.
- 동작은 접미사 경로(`{course_id}:archive` 등)다. 같은 경로의 다른 메서드가 먼저 맞아도 Starlette 는 다음 라우트를 찾는다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import AdminCaller, DbSession, Today
from classfit.core.config import Settings
from classfit.core.errors import NotFound
from classfit.crud import course as crud_course
from classfit.crud.audit import insert_audit
from classfit.crud.page import keyset_page
from classfit.models import Course, InviteCode
from classfit.schemas.course import (
    CourseOpenedOut,
    CourseOpenIn,
    CourseOut,
    CoursePatchIn,
    CourseStatus,
    StatusSetIn,
)
from classfit.schemas.invite_code import InviteCodeOut
from classfit.schemas.page import Page
from classfit.service.auth.sessions import Principal
from classfit.service.courses.codes import code_state_of, course_status_of
from classfit.service.courses.days import patch_course
from classfit.service.courses.open import open_course

router = APIRouter(prefix="/v1/admin", tags=["courses"])

_NOT_FOUND = {404: {"description": "강의가 없음"}}


def course_out(row: Course, today: date) -> CourseOut:
    return CourseOut(
        id=row.id,
        title=row.title,
        client_name=row.client_name,
        course_type=row.course_type,
        cohort=row.cohort,
        method=row.method,
        hours_per_person=row.hours_per_person,
        start_on=row.start_on,
        end_on=row.end_on,
        slot_min=row.slot_min,
        break_min=row.break_min,
        intro=row.intro,
        notice=row.notice,
        status=course_status_of(row, today),
        status_manual=row.status_manual,
        archived_at=row.archived_at,
        created_at=row.created_at,
    )


def code_out(code: InviteCode, course: Course, today: date) -> InviteCodeOut:
    return InviteCodeOut(
        code=code.code,
        status=code.status,  # type: ignore[arg-type]  # CHECK 가 세 값으로 막는다
        state=code_state_of(code, course, today),
        expires_on=code.expires_on,
        max_seats=code.max_seats,
        issued_at=code.created_at,
    )


async def course_or_404(session: AsyncSession, course_id: int) -> Course:
    row = await crud_course.get_course(session, course_id)
    if row is None:
        raise NotFound("강의가 없습니다")
    return row


async def audit_course(
    session: AsyncSession,
    caller: Principal,
    action: str,
    course_id: int,
    detail: dict[str, Any] | None = None,
) -> None:
    await insert_audit(
        session,
        actor=f"admin:{caller.id}",
        action=action,
        target_type="course",
        target_id=str(course_id),
        detail=detail,
    )


@router.get("/courses", response_model=Page[CourseOut])
async def list_courses(
    session: DbSession,
    caller: AdminCaller,
    today: Today,
    status: CourseStatus | None = None,
    archived: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CourseOut]:
    stmt = crud_course.list_stmt(caller, status, archived, today)
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
    return Page[CourseOut](
        items=[course_out(r, today) for r in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/courses", response_model=CourseOpenedOut, status_code=201)
async def open_blank_course(
    body: CourseOpenIn,
    request: Request,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> CourseOpenedOut:
    settings: Settings = request.app.state.settings
    course, code = await open_course(
        session,
        body,
        actor=f"admin:{caller.id}",
        invite_expiry_days=settings.invite_expiry_days,
    )
    return CourseOpenedOut(
        course=course_out(course, today), invite_code=code_out(code, course, today)
    )


@router.get("/courses/{course_id}", response_model=CourseOut, responses=_NOT_FOUND)
async def get_course(
    course_id: int, session: DbSession, _: AdminCaller, today: Today
) -> CourseOut:
    return course_out(await course_or_404(session, course_id), today)


@router.patch(
    "/courses/{course_id}",
    response_model=CourseOut,
    responses={
        **_NOT_FOUND,
        409: {"description": "일차가 있는데 기간을 바꿈 · 기간이 뒤집힘"},
    },
)
async def patch_course_info(
    course_id: int,
    body: CoursePatchIn,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> CourseOut:
    course = await course_or_404(session, course_id)
    fields = await patch_course(session, course, body)
    if fields:
        await audit_course(
            session, caller, "course.update", course_id, {"fields": fields}
        )
    return course_out(course, today)


@router.delete(
    "/courses/{course_id}",
    status_code=204,
    response_class=Response,
    responses=_NOT_FOUND,
)
async def delete_course(
    course_id: int, session: DbSession, caller: AdminCaller
) -> Response:
    await course_or_404(session, course_id)
    await crud_course.delete_course(session, course_id)
    await audit_course(session, caller, "course.delete", course_id)
    return Response(status_code=204)


@router.post(
    "/courses/{course_id}:archive", response_model=CourseOut, responses=_NOT_FOUND
)
async def archive_course(
    course_id: int, session: DbSession, caller: AdminCaller, today: Today
) -> CourseOut:
    """보관한 강의는 기본 목록(archived=false)에서 빠진다. 이미 보관했으면 그대로 200."""
    course = await course_or_404(session, course_id)
    if course.archived_at is None:
        await crud_course.update_course(session, course, archived_at=datetime.now(UTC))
        await audit_course(session, caller, "course.archive", course_id)
    return course_out(course, today)


@router.post(
    "/courses/{course_id}:set-status", response_model=CourseOut, responses=_NOT_FOUND
)
async def set_course_status(
    course_id: int,
    body: StatusSetIn,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> CourseOut:
    """관리자 수동 지정. :reset-status 전까지 날짜 규칙보다 이긴다(기획안 5-3)."""
    course = await course_or_404(session, course_id)
    await crud_course.update_course(
        session, course, status=body.status, status_manual=True
    )
    await audit_course(
        session, caller, "course.set_status", course_id, {"status": body.status}
    )
    return course_out(course, today)


@router.post(
    "/courses/{course_id}:reset-status", response_model=CourseOut, responses=_NOT_FOUND
)
async def reset_course_status(
    course_id: int, session: DbSession, caller: AdminCaller, today: Today
) -> CourseOut:
    """수동 지정을 풀어 날짜 규칙으로 되돌린다."""
    course = await course_or_404(session, course_id)
    await crud_course.update_course(session, course, status_manual=False)
    await audit_course(session, caller, "course.reset_status", course_id)
    return course_out(course, today)
