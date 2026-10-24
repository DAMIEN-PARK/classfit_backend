"""일정 끝점(관리자만, AdminCaller): 일차 PUT·PATCH·DELETE · 섹션 · 세션 · 일정표 GET.

- 일차를 바꾸면 강의 기간이 첫·끝 일차를 따른다(service.courses.days). 일정표의 세션 시각은 rules.schedule 로 계산한다.
- 그 강의에 없는 일차·날짜 순서 어긋남은 409, 다른 강의의 섹션은 404, 본문 모양 오류는 422 다.
- 일정·섹션·세션 편집은 audit 하지 않는다(T2a 계획 결정 viii).
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from classfit.app.deps import AdminCaller, DayPath, DbSession, IdPath
from classfit.app.endpoints.courses import course_or_404
from classfit.schemas.course import (
    DayPatchIn,
    DaysPutIn,
    ScheduleOut,
    SectionIn,
    SectionOut,
    SectionPatchIn,
    SessionIn,
    SessionOut,
    SessionPatchIn,
)
from classfit.service.courses import days, sections

router = APIRouter(prefix="/v1/admin", tags=["schedule"])

_404 = {404: {"description": "강의·일차·섹션·세션이 없음(다른 강의의 섹션 포함)"}}
_409 = {
    409: {
        "description": "그 강의에 없는 일차 · 일차 날짜 순서 어긋남 · 저장 상태와 충돌"
    }
}


@router.put("/courses/{course_id}/days", response_model=ScheduleOut, responses=_404)
async def put_days(
    course_id: IdPath, body: DaysPutIn, session: DbSession, _: AdminCaller
) -> ScheduleOut:
    """일차를 통째로 바꾸고 1..n 으로 다시 매긴다. 없어진 일차의 세션은 일차 미정이 된다."""
    course = await course_or_404(session, course_id)
    await days.put_days(session, course, body)
    return await days.schedule_of(session, course)


@router.patch(
    "/courses/{course_id}/days/{day_no}",
    response_model=ScheduleOut,
    responses={**_404, **_409},
)
async def patch_day(
    course_id: IdPath,
    day_no: DayPath,
    body: DayPatchIn,
    session: DbSession,
    _: AdminCaller,
) -> ScheduleOut:
    course = await course_or_404(session, course_id)
    await days.patch_day(session, course, day_no, body)
    return await days.schedule_of(session, course)


@router.delete(
    "/courses/{course_id}/days/{day_no}",
    status_code=204,
    response_class=Response,
    responses=_404,
)
async def delete_day(
    course_id: IdPath, day_no: DayPath, session: DbSession, _: AdminCaller
) -> Response:
    """번호는 다시 매기지 않는다. 그날 세션은 일차 미정이 된다."""
    course = await course_or_404(session, course_id)
    await days.delete_day(session, course, day_no)
    return Response(status_code=204)


@router.post(
    "/courses/{course_id}/sections",
    response_model=SectionOut,
    status_code=201,
    responses=_404,
)
async def add_section(
    course_id: IdPath, body: SectionIn, session: DbSession, _: AdminCaller
) -> SectionOut:
    await course_or_404(session, course_id)
    row = await sections.add_section(session, course_id, body)
    return SectionOut.model_validate(row)


@router.patch(
    "/courses/{course_id}/sections/{section_id}",
    response_model=SectionOut,
    responses=_404,
)
async def patch_section(
    course_id: IdPath,
    section_id: IdPath,
    body: SectionPatchIn,
    session: DbSession,
    _: AdminCaller,
) -> SectionOut:
    row = await sections.patch_section(session, course_id, section_id, body)
    return SectionOut.model_validate(row)


@router.delete(
    "/courses/{course_id}/sections/{section_id}",
    status_code=204,
    response_class=Response,
    responses=_404,
)
async def delete_section(
    course_id: IdPath, section_id: IdPath, session: DbSession, _: AdminCaller
) -> Response:
    """그 섹션의 세션도 같이 지운다."""
    await sections.remove_section(session, course_id, section_id)
    return Response(status_code=204)


@router.post(
    "/courses/{course_id}/sections/{section_id}/sessions",
    response_model=SessionOut,
    status_code=201,
    responses={**_404, **_409},
)
async def add_session(
    course_id: IdPath,
    section_id: IdPath,
    body: SessionIn,
    session: DbSession,
    _: AdminCaller,
) -> SessionOut:
    row = await sections.add_session(session, course_id, section_id, body)
    return SessionOut.model_validate(row)


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionOut,
    responses={
        404: {"description": "세션이 없음 · 배정할 강사가 없음"},
        409: {
            "description": "그 강의에 없는 일차 · 저장 상태와 충돌 · 승인되지 않은 강사 배정"
            "(instructor_status)"
        },
    },
)
async def patch_session(
    session_id: IdPath, body: SessionPatchIn, session: DbSession, caller: AdminCaller
) -> SessionOut:
    """instructor_id 를 주면 담당 강사를 바꾼다(null 은 해제). 배정은 audit·배정 알림 outbox 를 쓴다(T5)."""
    row = await sections.patch_session(
        session, session_id, body, actor=f"admin:{caller.id}"
    )
    return SessionOut.model_validate(row)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    response_class=Response,
    responses=_404,
)
async def delete_session(
    session_id: IdPath, session: DbSession, _: AdminCaller
) -> Response:
    await sections.remove_session(session, session_id)
    return Response(status_code=204)


@router.get("/courses/{course_id}/schedule", response_model=ScheduleOut, responses=_404)
async def get_schedule(
    course_id: IdPath, session: DbSession, _: AdminCaller
) -> ScheduleOut:
    course = await course_or_404(session, course_id)
    return await days.schedule_of(session, course)
