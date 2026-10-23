"""설문 결과 — 관리자 A5 · 강사 I7(T8 결정 x·xi·xii·xiii). 읽기만 하고 잠그지 않는다.

- 읽기는 한 문장이다: A5 는 crud.survey_response.survey_with_answers, I7 은 current_with_answers 가 설문 행 · 강의 행 · 답 배열을
  SELECT 하나로 읽어 상태·응답 수·집계가 한 스냅샷이다. 머리도 그 행으로 만든다(둘째 survey 문장을 만들지 않는다).
- 응답률 분모는 조회 시점 그 강의 등록 수(crud.enrollment.count_enrollments — enrollment 만 읽는다), 0 이면 percent null.
- 관리자는 임계 없이 늘 본다. 강사는 배정 강의(404 → 403)의 현재 설문(없으면 404)을, 닫힌 뒤(reason not_closed) 응답 수가
  min_responses 이상일 때만(reason below_minimum) 본다. 응답률은 늘 준다.
- 집계는 rules.survey_stats.aggregate 한 곳이다. 결과에 사람 칸 · 응답 id · 제출 시각은 없다(Design 1절 만족도 공개 범위).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import survey_response as crud_survey_response
from classfit.crud.scope import Subject
from classfit.service.rules.survey_stats import Aggregate, aggregate, percent
from classfit.service.surveys.scope import course_for_instructor
from classfit.service.surveys.views import SurveyHead, head_from

HiddenReason = Literal["not_closed", "below_minimum"]


@dataclass(frozen=True)
class SurveyResults:
    head: SurveyHead
    responses: int
    total: int
    percent: int | None  # 응답률(분모 0 이면 None)
    aggregate: Aggregate


@dataclass(frozen=True)
class MySurveyResults:
    head: SurveyHead
    responses: int
    total: int
    percent: int | None
    visible: bool
    reason: HiddenReason | None  # visible 이면 None
    min_responses: int
    aggregate: Aggregate | None  # visible 일 때만


async def admin_results(
    session: AsyncSession, *, survey_id: int, today: dt.date
) -> SurveyResults:
    found = await crud_survey_response.survey_with_answers(session, survey_id)
    if found is None:
        raise NotFound("설문이 없습니다")
    row, course, answers = found
    total = await crud_enrollment.count_enrollments(session, course.id)
    head = head_from(
        row,
        course_title=course.title,
        client_name=course.client_name,
        responses=len(answers),
        total=total,
        today=today,
    )
    return SurveyResults(
        head=head,
        responses=len(answers),
        total=total,
        percent=percent(len(answers), total),
        aggregate=aggregate(row.questions, answers),
    )


async def instructor_results(
    session: AsyncSession,
    subject: Subject,
    *,
    course_id: int,
    today: dt.date,
    min_responses: int,
) -> MySurveyResults:
    await course_for_instructor(session, subject, course_id)
    found = await crud_survey_response.current_with_answers(session, course_id)
    if found is None:
        raise NotFound("이 강의에 배포된 설문이 없습니다")
    row, course, answers = found
    total = await crud_enrollment.count_enrollments(session, course.id)
    head = head_from(
        row,
        course_title=course.title,
        client_name=course.client_name,
        responses=len(answers),
        total=total,
        today=today,
    )
    reason: HiddenReason | None = None
    if head.status != "closed":
        reason = "not_closed"
    elif len(answers) < min_responses:
        reason = "below_minimum"
    return MySurveyResults(
        head=head,
        responses=len(answers),
        total=total,
        percent=percent(len(answers), total),
        visible=reason is None,
        reason=reason,
        min_responses=min_responses,
        aggregate=None if reason is not None else aggregate(row.questions, answers),
    )
