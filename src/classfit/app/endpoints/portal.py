"""포털 끝점(T2b 계획 결정 vii·x): 수강생 GET /v1/learner/courses/{course_id}/portal ·
관리자 미리 보기 GET /v1/admin/courses/{course_id}/portal. 두 경로가 조립 함수 portal_out 하나를 쓴다.

- 수강생은 토큰의 강의만 본다. 경로의 course_id 가 다르면 403 이다(ADR-002 결정 1). 첨부는 crud 의 주체 범위로 거른다.
- 종료 강의도 등록자는 200 이다(L1). 강의 status 는 오늘(Today) 기준 계산값이다.
- 잠긴 카드는 제목·일차·날짜·시각만 준다. 첨부의 href 는 여기서 단다(pdf 는 href_for, link 는 url).
- 응답에 개인 칸(이름·이메일·부서)이 없다(원칙 10, E-14).
- survey 는 그 강의 현재 설문의 머리이고 상태는 오늘(Today) 기준 계산값이다(T8 결정 xv). 주체와 무관해 수강생 포털과
  관리자·강사 미리 보기가 같다. 응답 여부는 수강생 설문 GET 의 responded 다.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from classfit.app.deps import AdminCaller, DbSession, IdPath, LearnerCaller, Today
from classfit.app.endpoints.attachments import attachment_out
from classfit.app.errors import forbidden
from classfit.models import Survey
from classfit.schemas.portal import (
    PortalCourseOut,
    PortalOut,
    PortalSectionOut,
    PortalSessionOut,
    PortalSurveyOut,
)
from classfit.service.courses.codes import course_status_of
from classfit.service.courses.portal import Portal, PortalCard, build_portal
from classfit.service.rules.survey import status_at

router = APIRouter(prefix="/v1", tags=["portal"])


def _card_out(card: PortalCard) -> PortalSessionOut:
    row = card.row
    opened = card.state == "open"
    return PortalSessionOut(
        id=row.id,
        title=row.title,
        day_no=row.day_no,
        date=card.date,
        start=card.start,
        end=card.end,
        state=card.state,
        description=row.description if opened else None,
        keywords=list(row.keywords) if opened else None,
        attachments=[attachment_out(a) for a in card.attachments],
        instructor_name=card.instructor_name,
    )


def _survey_out(survey: Survey | None, today: date) -> PortalSurveyOut | None:
    if survey is None:
        return None
    return PortalSurveyOut(
        id=survey.id,
        status=status_at(
            open_on=survey.open_on,
            close_on=survey.close_on,
            closed_at=survey.closed_at,
            today=today,
        ),
        open_on=survey.open_on,
        close_on=survey.close_on,
    )


def portal_out(portal: Portal, today: date) -> PortalOut:
    course = portal.course
    return PortalOut(
        course=PortalCourseOut(
            id=course.id,
            title=course.title,
            start_on=course.start_on,
            end_on=course.end_on,
            status=course_status_of(course, today),
            intro=course.intro,
            notice=course.notice,
        ),
        sections=[
            PortalSectionOut(
                id=sec.row.id,
                title=sec.row.title,
                description=sec.row.description,
                sessions=[_card_out(c) for c in sec.cards],
            )
            for sec in portal.sections
        ],
        survey=_survey_out(portal.survey, today),
    )


@router.get(
    "/learner/courses/{course_id}/portal",
    response_model=PortalOut,
    responses={403: {"description": "토큰의 강의가 아님"}},
)
async def learner_portal(
    course_id: IdPath, session: DbSession, caller: LearnerCaller, today: Today
) -> PortalOut:
    if caller.course_id != course_id:
        raise forbidden("이 강의의 수강생이 아닙니다")
    return portal_out(await build_portal(session, caller, course_id=course_id), today)


@router.get(
    "/admin/courses/{course_id}/portal",
    response_model=PortalOut,
    responses={404: {"description": "강의가 없음"}},
)
async def admin_portal(
    course_id: IdPath, session: DbSession, caller: AdminCaller, today: Today
) -> PortalOut:
    """수강생이 보는 것과 같은 판정의 미리 보기."""
    return portal_out(await build_portal(session, caller, course_id=course_id), today)
