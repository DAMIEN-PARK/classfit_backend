"""입장 끝점(인증 없음): POST /v1/enter/lookup · POST /v1/enter(기획안 P3 · ADR-002 · T2b 계획 결정 i·vi).

- 판정은 service.enroll.enter 가 하고 결과 값만 돌려준다. 실패는 예외가 아니라 problem() 을 반환한다(T1 로그인 전례).
- 응답 매핑(결정 i): 혼동 문자 422 invite-code-confusable · 그 밖 형식 422 invite-code-malformed ·
  없는 코드·replaced 404 invite-code-not-found · 종료 409 course-ended · 만료 409 invite-code-expired ·
  정지 409 invite-code-paused · 정원 409 course-full · 새 등록에 이름 없음 422(violations body.name).
- 새 등록 201, 재입장 200. 재입장마다 새 세션을 주고 옛 세션은 만료까지 산다(결정 iii).
  세션은 Principal("learner", learner_id, course_id), 수명 learner_session_days(결정 vi).
- lookup 은 산 코드면 상태와 무관하게 200 + 강의 카드 + state · accepts_new · notice 다.
- 입장·재입장·조회는 audit 하지 않는다(enrollment·auth_session 행이 기록이다, 결정 xii).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from classfit.app.deps import DbSession, Today
from classfit.app.errors import problem
from classfit.core.config import Settings
from classfit.schemas.enter import (
    EnterCourseOut,
    EnterIn,
    EnterLookupIn,
    EnterLookupOut,
    EnterOut,
)
from classfit.service.auth.sessions import Principal, create_session
from classfit.service.enroll.enter import enter_course, lookup_code

router = APIRouter(prefix="/v1", tags=["enter"])

# 결과 → (상태, problem type, 안내). 안내에 코드 글자는 싣지 않는다(옛 코드 응답 = 없는 코드 응답)
_FAILURES: dict[str, tuple[int, str, str]] = {
    "confusable": (
        422,
        "/problems/invite-code-confusable",
        "초대코드에는 0·O·1·I 가 없습니다. 비슷한 글자를 다시 확인하세요",
    ),
    "malformed": (
        422,
        "/problems/invite-code-malformed",
        "초대코드는 영문 대문자·숫자 6자입니다",
    ),
    "not_found": (
        404,
        "/problems/invite-code-not-found",
        "초대코드가 없습니다. 담당자에게 받은 코드를 확인하세요",
    ),
    "ended": (409, "/problems/course-ended", "종료된 강의입니다"),
    "expired": (409, "/problems/invite-code-expired", "만료된 초대코드입니다"),
    "paused": (
        409,
        "/problems/invite-code-paused",
        "지금은 입장을 받지 않는 초대코드입니다",
    ),
    "full": (409, "/problems/course-full", "정원이 찼습니다"),
}

_LOOKUP_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "없는 코드 · 재발급으로 바뀐 옛 코드"},
    422: {
        "description": "혼동 문자(invite-code-confusable) · 그 밖 형식(invite-code-malformed)"
    },
}
_ENTER_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"description": "재입장(이 강의에 등록된 이메일)", "model": EnterOut},
    **_LOOKUP_RESPONSES,
    409: {
        "description": "종료 · 만료 · 정지 · 정원(새 이메일만, 기존 등록자는 재입장)"
    },
}


def _failure(request: Request, outcome: str) -> JSONResponse:
    status, type_, detail = _FAILURES[outcome]
    return problem(request, status=status, type=type_, detail=detail)


@router.post(
    "/enter/lookup", response_model=EnterLookupOut, responses=_LOOKUP_RESPONSES
)
async def lookup(
    body: EnterLookupIn, request: Request, session: DbSession, today: Today
) -> EnterLookupOut | JSONResponse:
    result = await lookup_code(session, raw_code=body.code, today=today)
    if (
        result.outcome != "ok"
        or result.course is None
        or result.course_status is None
        or result.state is None
    ):
        return _failure(request, result.outcome)
    course = result.course
    return EnterLookupOut(
        course=EnterCourseOut(
            title=course.title,
            start_on=course.start_on,
            end_on=course.end_on,
            status=result.course_status,
        ),
        state=result.state,
        accepts_new=result.accepts_new,
        notice=result.notice,
    )


@router.post(
    "/enter", response_model=EnterOut, status_code=201, responses=_ENTER_RESPONSES
)
async def enter(
    body: EnterIn,
    request: Request,
    response: Response,
    session: DbSession,
    today: Today,
) -> EnterOut | JSONResponse:
    result = await enter_course(
        session,
        raw_code=body.code,
        email=body.email,
        name=body.name,
        dept=body.dept,
        today=today,
    )
    if result.outcome == "name_required":
        return problem(
            request,
            status=422,
            title="요청 검증 실패",
            detail="처음 들어오는 이메일은 이름이 필요합니다",
            violations=[
                {
                    "loc": ["body", "name"],
                    "msg": "이름을 입력하세요",
                    "type": "missing",
                }
            ],
        )
    if (
        result.outcome not in ("created", "reentered")
        or result.learner_id is None
        or result.course_id is None
        or result.name is None
    ):
        return _failure(request, result.outcome)
    settings: Settings = request.app.state.settings
    issued = await create_session(
        session,
        principal=Principal("learner", result.learner_id, result.course_id),
        lifetime=timedelta(days=settings.learner_session_days),
    )
    reentered = result.outcome == "reentered"
    if reentered:
        response.status_code = 200
    return EnterOut(
        access_token=issued.token,
        expires_at=issued.expires_at,
        course_id=result.course_id,
        name=result.name,
        reentered=reentered,
        notice=result.notice,
    )
