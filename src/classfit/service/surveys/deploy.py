"""설문 배포(T8 결정 iii·vi·xvii·xviii·xix). flush 까지만.

- 한 요청이 강의마다 설문 한 행을 한 트랜잭션에 만든다. 한 강의라도 걸리면 전부 실패한다(부분 성공 없음 — problem 에 강의 id).
- 순서: 양식 행 FOR KEY SHARE(없으면 404 — 배포 중 양식 삭제와 줄 선다) → 강의 id 를 겹침 없이 오름차순으로 전부 lock_course
  (없으면 404) → 강의마다: 보관 409 → 현재 설문이 있으면 lock_survey 로 잡고 fresh 로 다시 읽어 예약·열림이면 409, 닫힘이면
  밀어낸다(supersede) → 열기·닫기 모드를 그 강의 종료일과 오늘로 날짜로 푼다(어긋나면 DatesRejected — 422) → 양식 이름·문항
  스냅샷으로 insert_survey(부분 유일 색인이 뒷받침 — 409) → audit survey.deploy → 알림.
- 알림(_notify_opened)은 그 강의 등록 수강생 전원과 배정 강사에게 survey_opened 를 1행씩 쌓는다. 예약 열림도 배포 때 쌓는다
  (워커가 없다). params 는 본문에 쓸 값의 스냅샷이다(강의·설문이 지워져도 미리 보기 본문이 같다).
"""

from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Collection, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import outbox as crud_outbox
from classfit.crud import survey as crud_survey
from classfit.crud import survey_template as crud_survey_template
from classfit.models import Course, Survey
from classfit.service.rules.survey import DatesRejected, resolve_dates
from classfit.service.surveys.views import NO_TEMPLATE, status_of

OPENED_KIND = "survey_opened"


async def deploy(
    session: AsyncSession,
    *,
    course_ids: Collection[int],
    template_id: int,
    open: Mapping[str, Any],
    close: Mapping[str, Any],
    today: dt.date,
    close_days: int,
    actor: str,
) -> list[Survey]:
    """새 현재 설문들(강의 id 순). open·close 는 {mode, date?} 모드 dict 다(결정 vi)."""
    template = await crud_survey_template.lock_template_shared(session, template_id)
    if template is None:
        raise NotFound(NO_TEMPLATE)
    courses: list[Course] = []
    for course_id in sorted(set(course_ids)):
        course = await crud_course.lock_course(session, course_id)
        if course is None:
            raise NotFound("강의가 없습니다", course_id=course_id)
        courses.append(course)
    surveys = []
    for course in courses:
        if course.archived_at is not None:
            raise Conflict("보관한 강의에는 배포할 수 없습니다", course_id=course.id)
        superseded_id = None
        current = await crud_survey.current_for_course(session, course.id)
        if current is not None:
            await crud_survey.lock_survey(session, current.id)
            fresh = await crud_survey.get_survey(session, current.id, fresh=True)
            if fresh is not None and fresh.current:
                if status_of(fresh, today) != "closed":
                    raise Conflict(
                        "이 강의에는 열려 있거나 예약된 설문이 있습니다",
                        course_id=course.id,
                    )
                await crud_survey.supersede(session, fresh)
                superseded_id = fresh.id
        try:
            open_on, close_on = resolve_dates(
                open, close, today=today, end_on=course.end_on, close_days=close_days
            )
        except DatesRejected as exc:
            raise DatesRejected(exc.reason, course_id=course.id) from exc
        row = await crud_survey.insert_survey(
            session,
            course_id=course.id,
            template_id=template.id,
            template_name=template.name,
            questions=copy.deepcopy(template.questions),
            open_on=open_on,
            close_on=close_on,
        )
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="survey.deploy",
            target_type="course",
            target_id=str(course.id),
            detail={
                "survey_id": row.id,
                "template_id": template.id,
                "open_on": open_on.isoformat(),
                "close_on": close_on.isoformat(),
                "superseded_id": superseded_id,
            },
        )
        await _notify_opened(session, survey=row, course=course)
        surveys.append(row)
    return surveys


async def _notify_opened(
    session: AsyncSession, *, survey: Survey, course: Course
) -> int:
    """등록 수강생 전원(등록 순)과 배정 강사(강사 id 순)에게 survey_opened 한 행씩. 쌓은 수."""
    learners, instructors = await crud_survey.recipient_emails(session, course.id)
    params = {
        "survey_id": survey.id,
        "course_title": course.title,
        "open_on": survey.open_on.isoformat(),
        "close_on": survey.close_on.isoformat(),
    }
    for to in [*learners, *instructors]:
        await crud_outbox.enqueue(session, kind=OPENED_KIND, params=dict(params), to=to)
    return len(learners) + len(instructors)
