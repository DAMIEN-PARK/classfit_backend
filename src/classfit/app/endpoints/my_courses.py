"""강사의 배정 강의 끝점(InstructorCaller, T5 계획 결정 i·xii·xiii).

- GET /v1/me/courses?status=&archived=&cursor=&limit=: 세션이 하나라도 내게 배정된 강의다(첫 WHERE 는
  crud.scope.course_scope 의 강사 갈래). 키셋 커서 {items, next_cursor, has_more} 이고 깨진 커서는 422
  loc ["query", "cursor"] 다. archived 기본은 보관 안 한 것만. my_sessions 는 그 강의에서 내가 맡은 세션 수다.
- GET /v1/me/courses/{course_id} · …/schedule: 없는 강의 404 → 범위 밖 403 순이다(범위 getter 하나로 섞지 않는다,
  결정 i). 범위 안이면 그 강의의 모든 세션을 읽기 전용으로 본다(남의 세션도 강사 id·이름). 첨부는 개수만이고 href 는
  없다. 일정표는 관리자 일정표와 같은 ScheduleOut 이다(CRS-010).
- PATCH /v1/me/sessions/{session_id} 본문 {description?, keywords?, is_open?}: 그 밖의 키는 422 extra_forbidden.
  없는 세션 404 → 강의 행을 잠근 뒤 다시 읽어 내 세션이 아니면 403(배정이 바뀌는 사이의 수정을 막는다). audit 없음.
- 경로 id 는 1 ≤ id < 2**63(BIGINT)이다. 밖이면 DB 를 치지 않고 422 loc ["path", <이름>](IdPath).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import DbSession, IdPath, InstructorCaller, Today
from classfit.crud.schedule import get_session_and_course
from classfit.schemas.course import CourseStatus, ScheduleOut
from classfit.schemas.my_course import (
    MyCourseDetailOut,
    MyCourseInfoOut,
    MyCourseOut,
    MySectionOut,
    MySessionOut,
    MySessionPatchIn,
)
from classfit.schemas.page import Page
from classfit.service.courses import mine
from classfit.service.courses.codes import course_status_of

router = APIRouter(prefix="/v1/me", tags=["my-courses"])

_ONE = {
    403: {"description": "내 세션이 없는 강의"},
    404: {"description": "강의가 없음"},
}


def _session_out(item: mine.MySession) -> MySessionOut:
    row = item.row
    return MySessionOut(
        id=row.id,
        section_id=row.section_id,
        title=row.title,
        description=row.description,
        keywords=list(row.keywords),
        is_open=row.is_open,
        day_no=row.day_no,
        slot=row.slot,
        minutes=row.minutes,
        date=item.date,
        start=item.start,
        end=item.end,
        instructor_id=row.instructor_id,
        instructor_name=item.instructor_name,
        attachments=item.attachments,
    )


def _detail_out(view: mine.MyCourseView, today: date) -> MyCourseDetailOut:
    course = view.course
    return MyCourseDetailOut(
        course=MyCourseInfoOut(
            id=course.id,
            title=course.title,
            client_name=course.client_name,
            course_type=course.course_type,
            cohort=course.cohort,
            method=course.method,
            hours_per_person=course.hours_per_person,
            start_on=course.start_on,
            end_on=course.end_on,
            slot_min=course.slot_min,
            break_min=course.break_min,
            intro=course.intro,
            notice=course.notice,
            status=course_status_of(course, today),
        ),
        sections=[
            MySectionOut(
                id=sec.row.id,
                title=sec.row.title,
                description=sec.row.description,
                sessions=[_session_out(s) for s in sec.sessions],
            )
            for sec in view.sections
        ],
    )


@router.get("/courses", response_model=Page[MyCourseOut])
async def list_my_courses(
    session: DbSession,
    caller: InstructorCaller,
    today: Today,
    status: CourseStatus | None = None,
    archived: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[MyCourseOut]:
    try:
        page = await mine.my_courses(
            session,
            caller,
            status=status,
            archived=archived,
            today=today,
            cursor=cursor,
            limit=limit,
        )
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
    return Page[MyCourseOut](
        items=[
            MyCourseOut(
                id=c.id,
                title=c.title,
                client_name=c.client_name,
                course_type=c.course_type,
                cohort=c.cohort,
                method=c.method,
                start_on=c.start_on,
                end_on=c.end_on,
                status=course_status_of(c, today),
                my_sessions=mine_count,
            )
            for c, mine_count in page.items
        ],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/courses/{course_id}", response_model=MyCourseDetailOut, responses=_ONE)
async def get_my_course(
    course_id: IdPath, session: DbSession, caller: InstructorCaller, today: Today
) -> MyCourseDetailOut:
    view = await mine.course_view(session, caller, course_id=course_id)
    return _detail_out(view, today)


@router.get("/courses/{course_id}/schedule", response_model=ScheduleOut, responses=_ONE)
async def get_my_schedule(
    course_id: IdPath, session: DbSession, caller: InstructorCaller
) -> ScheduleOut:
    return await mine.schedule_for(session, caller, course_id=course_id)


@router.patch(
    "/sessions/{session_id}",
    response_model=MySessionOut,
    responses={
        403: {"description": "내 세션이 아님(남의 세션 · 미배정)"},
        404: {"description": "세션이 없음"},
    },
)
async def patch_my_session(
    session_id: IdPath,
    body: MySessionPatchIn,
    session: DbSession,
    caller: InstructorCaller,
) -> MySessionOut:
    await mine.patch_my_session(
        session, instructor_id=caller.id, session_id=session_id, changes=body.changes()
    )
    found = await get_session_and_course(session, session_id)
    if found is None:  # 방금 잠근 강의 안에서 고친 세션이다
        raise RuntimeError(f"세션 {session_id} 를 다시 못 읽었다")
    _, course_id = found
    view = await mine.course_view(session, caller, course_id=course_id)
    for sec in view.sections:
        for item in sec.sessions:
            if item.row.id == session_id:
                return _session_out(item)
    raise RuntimeError(f"세션 {session_id} 가 강의 {course_id} 보기에 없다")
