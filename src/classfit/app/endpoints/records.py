"""교육 기록 끝점(T7 계획 결정 i·ii·iii·v·vi·x·xi·xxi·xxii). 강사 셋(InstructorCaller) · 관리자 다섯(AdminCaller).

- 상태 전이(결정 iii): 강사 저장 none → done · 바뀐 칸이 있으면 done(확인된 기록도 done 으로 돌아온다) · 바뀐 칸이
  없으면 그대로. 관리자 저장은 ok(기록자·확인자 관리자). 확인 done → ok(ok 는 그대로, 기록 없음 409). 판정은
  service.rules.record 한 곳이고 바뀐 것이 있는 쓰기마다 audit 1행이다(service.courses.records·record_days).
- 강사 쓰기는 그 세션의 지금 담당만이다(남의 세션·미배정 403). 저장은 일정 날짜를 보지 않는다(결정 v). 판정은 404(없음)
  → 403(내 세션 아님)이고 경로 id 는 IdPath(1 ≤ id < 2**63, 밖이면 DB 를 치지 않고 422 loc ["path", <이름>]), 일차
  번호는 DayPath(1..60, 밖이면 422).
- 계획대로 기록(…/days/{day_no}:record-as-planned)은 그 강의 그 일차의 모든 섹션 세션 가운데 기록 없는 것에 계획 값을
  넣는다(강사는 내 세션만 done, 관리자는 전부 ok). 지난 일차만이다(예정 일차 409). 일괄 확인(:confirm-all)은 그 일차의
  done 을 ok 로 하고 날짜를 보지 않는다. 0건이면 200 · audit 없음.
- 기록 목록: 강사는 그 강의의 내 세션만(첫 WHERE session_scope, 결정 x), 관리자는 모든 세션이다. 세션마다 사진은 올린
  순 앞 20장 + photos_more, summary.photos 는 전체 장수다. 사람 칸은 강사 이름 하나다(결정 xxi).
- 관리자 강의 끝점은 없는 강의를 먼저 404 "강의가 없습니다" 로 가린다(course_or_404, 결정 i) — 일차 둘은 그 뒤 없는 일차 404.
- 기록은 포털·수강생 경로에 없다(결정 xvii). 지우는 끝점은 없다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields
from typing import Annotated, Any

from fastapi import APIRouter, Path

from classfit.app.deps import AdminCaller, DbSession, InstructorCaller, Today
from classfit.app.endpoints.assign import IdPath
from classfit.app.endpoints.courses import course_or_404
from classfit.schemas.record import (
    AdminCourseRecordsOut,
    AdminRecordSessionOut,
    MyCourseRecordsOut,
    RecordDayOut,
    RecordIn,
    RecordSessionOut,
    RecordSummaryOut,
    SessionRecordOut,
)
from classfit.service.courses import record_days, record_views, records
from classfit.service.files.store import href_for
from classfit.service.rules.record import RecordFields

router = APIRouter(prefix="/v1", tags=["records"])

# 일차 번호 경로(본문 DayNo 1..60 의 경로 판). 밖이면 DB 를 치지 않고 422 loc ["path", "day_no"]
DayPath = Annotated[int, Path(ge=1, le=60)]

_SESSION = {
    403: {"description": "내 세션이 아님(남의 세션 · 미배정)"},
    404: {"description": "세션이 없음"},
}
_COURSE_MINE = {
    403: {"description": "내 세션이 없는 강의"},
    404: {"description": "강의가 없음"},
}
_DAY = {
    404: {"description": "강의·일차가 없음"},
    409: {"description": "예정 일차(일차 날짜가 오늘보다 뒤)"},
}


def record_out(view: records.RecordView) -> SessionRecordOut:
    """RecordView 는 속성 이름이 응답 칸이다."""
    return SessionRecordOut.model_validate(view, from_attributes=True)


def _shallow(item: Any) -> dict[str, Any]:
    """dataclass 의 칸을 한 겹만 dict 로(asdict 는 ORM 행까지 깊이 복사한다)."""
    return {f.name: getattr(item, f.name) for f in fields(item)}


def _sessions[S: (RecordSessionOut, AdminRecordSessionOut)](
    model: type[S], items: Sequence[record_views.RecordSession]
) -> list[S]:
    """세션 항목. 사진은 파일 key 를 싣고 오니(courses 는 files 를 모른다) href 를 여기서 단다."""
    return [
        model.model_validate(
            {
                **_shallow(item),
                "photos": [
                    {**_shallow(p), "href": href_for(p.key)} for p in item.photos
                ],
            },
            from_attributes=True,
        )
        for item in items
    ]


def _summary_out(summary: record_views.RecordSummary) -> RecordSummaryOut:
    return RecordSummaryOut.model_validate(summary, from_attributes=True)


def _day_out(result: record_days.DayResult) -> RecordDayOut:
    return RecordDayOut.model_validate(result, from_attributes=True)


def _fields(body: RecordIn) -> RecordFields:
    return RecordFields(**body.model_dump())


# ── 강사


@router.get(
    "/me/courses/{course_id}/records",
    response_model=MyCourseRecordsOut,
    responses=_COURSE_MINE,
)
async def my_course_records(
    course_id: IdPath, session: DbSession, caller: InstructorCaller, today: Today
) -> MyCourseRecordsOut:
    view = await record_views.my_records(
        session, caller, course_id=course_id, today=today
    )
    return MyCourseRecordsOut(
        course_id=view.course_id,
        summary=_summary_out(view.summary),
        sessions=_sessions(RecordSessionOut, view.sessions),
    )


@router.put(
    "/me/sessions/{session_id}/record",
    response_model=SessionRecordOut,
    responses=_SESSION,
)
async def save_my_record(
    session_id: IdPath, body: RecordIn, session: DbSession, caller: InstructorCaller
) -> SessionRecordOut:
    view = await records.save_my_record(
        session,
        instructor_id=caller.id,
        session_id=session_id,
        fields=_fields(body),
        actor=f"instructor:{caller.id}",
    )
    return record_out(view)


@router.post(
    "/me/courses/{course_id}/days/{day_no}:record-as-planned",
    response_model=RecordDayOut,
    responses={**_COURSE_MINE, **_DAY},
)
async def record_my_day_as_planned(
    course_id: IdPath,
    day_no: DayPath,
    session: DbSession,
    caller: InstructorCaller,
    today: Today,
) -> RecordDayOut:
    """그 일차의 내 세션 가운데 기록 없는 것만 done(계획 값). 이미 쓴 기록은 덮지 않는다."""
    result = await record_days.record_day_as_planned(
        session,
        caller,
        course_id=course_id,
        day_no=day_no,
        today=today,
        actor=f"instructor:{caller.id}",
    )
    return _day_out(result)


# ── 관리자


@router.get(
    "/admin/courses/{course_id}/records",
    response_model=AdminCourseRecordsOut,
    responses={404: {"description": "강의가 없음"}},
)
async def admin_course_records(
    course_id: IdPath, session: DbSession, caller: AdminCaller, today: Today
) -> AdminCourseRecordsOut:
    view = await record_views.admin_records(
        session, caller, course_id=course_id, today=today
    )
    return AdminCourseRecordsOut(
        course_id=view.course_id,
        summary=_summary_out(view.summary),
        sessions=_sessions(AdminRecordSessionOut, view.sessions),
    )


@router.put(
    "/admin/sessions/{session_id}/record",
    response_model=SessionRecordOut,
    responses={404: {"description": "세션이 없음"}},
)
async def save_admin_record(
    session_id: IdPath, body: RecordIn, session: DbSession, caller: AdminCaller
) -> SessionRecordOut:
    """관리자가 쓰면 바로 확인된다(ok). 미배정 세션도 쓴다."""
    view = await records.save_admin_record(
        session,
        admin_id=caller.id,
        session_id=session_id,
        fields=_fields(body),
        actor=f"admin:{caller.id}",
    )
    return record_out(view)


@router.post(
    "/admin/sessions/{session_id}/record:confirm",
    response_model=SessionRecordOut,
    responses={
        404: {"description": "세션이 없음"},
        409: {"description": "확인할 기록이 없음"},
    },
)
async def confirm_record(
    session_id: IdPath, session: DbSession, caller: AdminCaller
) -> SessionRecordOut:
    view = await records.confirm_record(
        session,
        admin_id=caller.id,
        session_id=session_id,
        actor=f"admin:{caller.id}",
    )
    return record_out(view)


@router.post(
    "/admin/courses/{course_id}/days/{day_no}:record-as-planned",
    response_model=RecordDayOut,
    responses=_DAY,
)
async def record_day_as_planned(
    course_id: IdPath,
    day_no: DayPath,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> RecordDayOut:
    """그 일차의 모든 세션 가운데 기록 없는 것을 ok(계획 값)로. 이미 쓴 기록은 덮지 않는다."""
    await course_or_404(session, course_id)
    result = await record_days.record_day_as_planned(
        session,
        caller,
        course_id=course_id,
        day_no=day_no,
        today=today,
        actor=f"admin:{caller.id}",
    )
    return _day_out(result)


@router.post(
    "/admin/courses/{course_id}/days/{day_no}:confirm-all",
    response_model=RecordDayOut,
    responses={404: {"description": "강의·일차가 없음"}},
)
async def confirm_day(
    course_id: IdPath, day_no: DayPath, session: DbSession, caller: AdminCaller
) -> RecordDayOut:
    """그 일차의 done 을 전부 ok 로. none·ok 는 그대로다."""
    await course_or_404(session, course_id)
    result = await record_days.confirm_day(
        session,
        admin_id=caller.id,
        course_id=course_id,
        day_no=day_no,
        actor=f"admin:{caller.id}",
    )
    return _day_out(result)
