"""수강생 설문 조회·제출(T8 결정 ix·xviii·xix). 제출은 flush 까지만.

- 둘 다 경로의 강의가 토큰의 강의가 아니면 403 이다. 보는 것은 그 강의의 현재 설문 하나다.
- 조회: 현재 설문이 없으면 status none. 문항(과 문항 판 해시)은 열린 설문일 때만 준다. responded 는 내 등록의 응답이 있는지,
  prefill_dept 는 내 등록의 부서다(입장 때 값으로 미리 채운다).
- 제출: 현재 설문 없음 404 → 등록 없음 403 → 설문 행을 잡고(lock_survey — 강의 행은 잡지 않는다) fresh 로 다시 읽어 →
  본 설문판(survey_id · questions_hash)이 지금 현재 설문과 다르면 409 reason survey_changed → 열려 있지 않으면 409 →
  이미 응답했으면 409 → 답 검사(AnswersRejected — 422) → 정리한 답을 넣는다(유일 제약이 뒷받침 — 409).
- 다시 열어도·다시 입장해 토큰이 바뀌어도 같은 등록이라 두 번째는 409 다. 제출은 audit 을 쓰지 않는다(시각이 남아 명단의
  응답 여부와 이어질 수 있다).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, Forbidden, NotFound
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import survey as crud_survey
from classfit.crud import survey_response as crud_survey_response
from classfit.crud.scope import Subject
from classfit.models import Survey
from classfit.service.rules.survey import answer_errors, normalize_answers
from classfit.service.rules.survey import questions_hash as version_of
from classfit.service.surveys.views import status_of

LearnerSurveyStatus = Literal["none", "scheduled", "open", "closed"]
NOT_MY_COURSE = "내 강의가 아닙니다"
CHANGED = "설문이 바뀌었습니다. 새로 불러와 다시 답해 주세요"


class AnswersRejected(ValueError):
    """답 검사 실패(끝점이 422 violations[].loc = ["body","answers",<key>]). errors 는 (문항 key, 까닭) 목록이다."""

    def __init__(self, errors: list[tuple[str, str]]) -> None:
        super().__init__("답이 설문 문항에 맞지 않습니다")
        self.errors = errors


@dataclass(frozen=True)
class LearnerSurvey:
    status: LearnerSurveyStatus
    survey: Survey | None  # 열린 설문일 때만(문항을 싣는다)
    questions_hash: str | None  # survey 가 있을 때만
    responded: bool
    prefill_dept: str | None


def _my_course(subject: Subject, course_id: int) -> None:
    if subject.type != "learner" or subject.course_id != course_id:
        raise Forbidden(NOT_MY_COURSE)


async def learner_view(
    session: AsyncSession, subject: Subject, *, course_id: int, today: dt.date
) -> LearnerSurvey:
    _my_course(subject, course_id)
    enrollment = await crud_enrollment.find_enrollment(session, course_id, subject.id)
    prefill = None if enrollment is None else enrollment.dept
    current = await crud_survey.current_for_course(session, course_id)
    if current is None:
        return LearnerSurvey("none", None, None, False, prefill)
    responded = enrollment is not None and (
        await crud_survey_response.find_response(session, current.id, enrollment.id)
        is not None
    )
    status = status_of(current, today)
    if status != "open":
        return LearnerSurvey(status, None, None, responded, prefill)
    return LearnerSurvey(
        status, current, version_of(current.questions), responded, prefill
    )


async def submit(
    session: AsyncSession,
    subject: Subject,
    *,
    course_id: int,
    survey_id: int,
    questions_hash: str,
    answers: Mapping[str, Any],
    today: dt.date,
) -> Survey:
    """응답 한 행을 넣고 그 설문을 돌려준다."""
    _my_course(subject, course_id)
    current = await crud_survey.current_for_course(session, course_id)
    if current is None:
        raise NotFound("진행 중인 설문이 없습니다")
    enrollment = await crud_enrollment.find_enrollment(session, course_id, subject.id)
    if enrollment is None:
        raise Forbidden(NOT_MY_COURSE)
    if await crud_survey.lock_survey(session, current.id) is None:
        raise Conflict(CHANGED, reason="survey_changed")
    row = await crud_survey.get_survey(session, current.id, fresh=True)
    if (
        row is None
        or not row.current
        or row.id != survey_id
        or version_of(row.questions) != questions_hash
    ):
        raise Conflict(CHANGED, reason="survey_changed")
    if status_of(row, today) != "open":
        raise Conflict("열려 있는 설문이 아닙니다")
    if (
        await crud_survey_response.find_response(
            session, row.id, enrollment.id, fresh=True
        )
        is not None
    ):
        raise Conflict(crud_survey_response.ALREADY)
    if errors := answer_errors(row.questions, answers):
        raise AnswersRejected(errors)
    await crud_survey_response.insert_response(
        session,
        survey_id=row.id,
        enrollment_id=enrollment.id,
        answers=normalize_answers(row.questions, answers),
    )
    return row
