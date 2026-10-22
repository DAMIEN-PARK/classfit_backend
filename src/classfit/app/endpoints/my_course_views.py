"""강사 화면 읽기(InstructorCaller, T6 계획 결정 xiii·xiv·xxi·xxii). 쓰지 않는다.

- 강의를 가리키는 넷(포털 미리 보기 · 초대코드 · 안내문 · 명단)은 없는 강의 404 → 내 세션이 없는 강의 403 순이다
  (service.courses.mine.course_for). 경로 id 는 IdPath(1 ≤ id < 2**63, 밖이면 DB 를 치지 않고 422).
- GET /v1/me/courses/{course_id}/portal: 그 강의 수강생이 같은 날 보는 것과 같은 PortalOut 이다(수강생 시점 범위로
  조립 — 열린 카드만 첨부가 보인다). 개인 칸은 없다.
- GET /v1/me/home: 강사 상태 · 강의 셈 · 배정 강의 표 · 강의안 없는 내 세션 · 안 낸 필수 서류 · 가능 과정 수.
  대기 강사도 200 이다(빈 목록).
- GET …/invite-code: 산 코드(없으면 404) + 등록 수. 강사는 읽기만 한다. …/invite-code/notice: 관리자와 같은 안내문 글자.
- GET …/enrollments: 이름·부서·등록일만이다(이메일·전화·id 없음, 결정 xxi). 키셋 커서 {items, next_cursor, has_more},
  (created_at, id) 내림차순, 깨진 커서는 422 loc ["query", "cursor"].
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import DbSession, InstructorCaller, Today
from classfit.app.endpoints.assign import IdPath
from classfit.app.endpoints.courses import code_out
from classfit.app.endpoints.portal import portal_out
from classfit.schemas.invite_code import NoticeOut
from classfit.schemas.my_home import MyHomeOut, MyInviteCodeOut, MyRosterOut
from classfit.schemas.page import Page
from classfit.schemas.portal import PortalOut
from classfit.service.courses import home, my_views

router = APIRouter(prefix="/v1/me", tags=["my-course-views"])

_ONE = {
    403: {"description": "내 세션이 없는 강의"},
    404: {"description": "강의가 없음"},
}
_CODE = {
    403: {"description": "내 세션이 없는 강의"},
    404: {"description": "강의나 그 강의의 산 초대코드가 없음"},
}


@router.get("/courses/{course_id}/portal", response_model=PortalOut, responses=_ONE)
async def my_portal_preview(
    course_id: IdPath, session: DbSession, caller: InstructorCaller, today: Today
) -> PortalOut:
    portal = await my_views.portal_preview(session, caller, course_id=course_id)
    return portal_out(portal, today)


@router.get("/home", response_model=MyHomeOut)
async def my_home(
    session: DbSession, caller: InstructorCaller, today: Today
) -> MyHomeOut:
    view = await home.home_of(session, caller, today=today)
    return MyHomeOut.model_validate(view, from_attributes=True)


@router.get(
    "/courses/{course_id}/invite-code", response_model=MyInviteCodeOut, responses=_CODE
)
async def my_invite_code(
    course_id: IdPath, session: DbSession, caller: InstructorCaller, today: Today
) -> MyInviteCodeOut:
    course, code, enrolled = await my_views.my_invite_code(
        session, caller, course_id=course_id
    )
    out = code_out(code, course, today)
    return MyInviteCodeOut.model_validate({**out.model_dump(), "enrolled": enrolled})


@router.get(
    "/courses/{course_id}/invite-code/notice", response_model=NoticeOut, responses=_CODE
)
async def my_invite_code_notice(
    course_id: IdPath, session: DbSession, caller: InstructorCaller
) -> NoticeOut:
    """고객사 담당자에게 보낼 안내문 글자(관리자 안내문과 같은 service.courses.codes.notice_text)."""
    return NoticeOut(
        text=await my_views.my_notice(session, caller, course_id=course_id)
    )


@router.get(
    "/courses/{course_id}/enrollments",
    response_model=Page[MyRosterOut],
    responses=_ONE,
)
async def my_roster(
    course_id: IdPath,
    session: DbSession,
    caller: InstructorCaller,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[MyRosterOut]:
    try:
        items, next_cursor, has_more = await my_views.my_roster(
            session, caller, course_id=course_id, cursor=cursor, limit=limit
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
    return Page[MyRosterOut](
        items=[
            MyRosterOut(name=r.name, dept=r.dept, enrolled_at=r.created_at)
            for r in items
        ],
        next_cursor=next_cursor,
        has_more=has_more,
    )
