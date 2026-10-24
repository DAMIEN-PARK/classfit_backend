"""수강생 설문 조회·제출과 강사 결과(T8 계획 결정 i·ix·xii·xiii·xxv).

- GET /v1/learner/courses/{course_id}/survey(LearnerCaller): 경로 강의가 토큰의 강의가 아니면 403. 현재 설문이 없으면
  status none, 있으면 오늘 기준 상태(scheduled·open·closed)이고 문항·questions_hash 는 open 일 때만 싣는다.
  responded 는 내 등록의 응답 여부, prefill_dept 는 내 등록의 부서다.
- POST …/survey/responses {survey_id, questions_hash, answers}: 본문은 app.deps.limited_json 이 파싱 전에 256KiB 로
  막는다(Content-Length · chunked 둘 다 413 — 인증 의존성 뒤라 401·403 이 먼저). 판정은 403(토큰의 강의 아님) → 404
  (현재 설문 없음) → 409 survey_changed(본 설문판과 현재 설문의 id·문항 해시가 다름) → 409(열림 아님) → 409(이미 응답 —
  다시 열어도 · 재입장해도 등록 1건당 1회) → 422(답 모양 — violations[].loc ["body", "answers", <문항 key>], type 은
  missing·unknown·invalid) → 201 {survey_id, responded}. 제출은 audit 을 쓰지 않는다(결정 xviii).
- GET /v1/me/courses/{course_id}/survey-results(InstructorCaller): 없는 강의 404 → 배정 없는 강의 403 → 현재 설문 없음
  404. 닫히지 않았으면 visible false · reason not_closed, 응답 수 < survey_min_responses 면 below_minimum, 그 밖에만
  results(A5 와 같은 집계). 응답률은 늘 준다. 사람 칸·제출 시각 없음.
- 경로 id 는 IdPath(밖이면 DB 를 치지 않고 422 loc ["path", "course_id"]).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import (
    DbSession,
    InstructorCaller,
    LearnerCaller,
    Today,
    limited_json,
)
from classfit.app.endpoints.assign import IdPath
from classfit.app.endpoints.surveys import head_out, rate_out, results_body
from classfit.core.config import Settings
from classfit.schemas.survey import (
    LearnerSurveyOut,
    LearnerSurveyQuestionsOut,
    QuestionOut,
    SubmitIn,
    SubmitOut,
)
from classfit.schemas.survey_results import MySurveyResultsOut
from classfit.service.surveys import respond, results

router = APIRouter(prefix="/v1", tags=["survey-learner"])

SURVEY_BODY_MAX_BYTES = 256 * 1024
_SUBMIT_DOC: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": SubmitIn.model_json_schema()}},
    }
}
_REASONS = {
    "missing": "필수 문항에 답이 없습니다",
    "unknown": "이 설문에 없는 문항입니다",
    "invalid": "문항에 맞지 않는 값입니다",
}


@router.get(
    "/learner/courses/{course_id}/survey",
    response_model=LearnerSurveyOut,
    responses={403: {"description": "토큰의 강의가 아님"}},
)
async def learner_survey(
    course_id: IdPath, session: DbSession, caller: LearnerCaller, today: Today
) -> LearnerSurveyOut:
    view = await respond.learner_view(session, caller, course_id=course_id, today=today)
    survey = None
    if view.survey is not None and view.questions_hash is not None:  # 열린 설문일 때만
        row = view.survey
        survey = LearnerSurveyQuestionsOut(
            id=row.id,
            open_on=row.open_on,
            close_on=row.close_on,
            questions_hash=view.questions_hash,
            questions=[QuestionOut.model_validate(q) for q in row.questions],
        )
    return LearnerSurveyOut(
        status=view.status,
        survey=survey,
        responded=view.responded,
        prefill_dept=view.prefill_dept,
    )


@router.post(
    "/learner/courses/{course_id}/survey/responses",
    response_model=SubmitOut,
    status_code=201,
    openapi_extra=_SUBMIT_DOC,
    responses={
        403: {"description": "토큰의 강의가 아님"},
        404: {"description": "현재 설문이 없음"},
        409: {
            "description": "본 설문판이 바뀜(survey_changed) · 열리지 않음 · 이미 응답"
        },
        413: {"description": "본문이 256KiB 보다 큼"},
        415: {"description": "JSON 이 아닌 Content-Type"},
        422: {"description": "본문 모양 · 답 모양(필수 누락 · 모르는 문항 · 값)"},
    },
)
async def submit_response(
    course_id: IdPath,
    session: DbSession,
    caller: LearnerCaller,
    today: Today,
    body: Annotated[SubmitIn, Depends(limited_json(SubmitIn, SURVEY_BODY_MAX_BYTES))],
) -> SubmitOut:
    try:
        row = await respond.submit(
            session,
            caller,
            course_id=course_id,
            survey_id=body.survey_id,
            questions_hash=body.questions_hash,
            answers=body.answers,
            today=today,
        )
    except respond.AnswersRejected as exc:
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "answers", key),
                    "msg": _REASONS.get(reason, reason),
                    "type": reason,
                }
                for key, reason in exc.errors
            ]
        ) from None
    return SubmitOut(survey_id=row.id, responded=True)


@router.get(
    "/me/courses/{course_id}/survey-results",
    response_model=MySurveyResultsOut,
    responses={
        403: {"description": "배정된 세션이 없는 강의"},
        404: {"description": "강의 · 현재 설문이 없음"},
    },
)
async def my_survey_results(
    course_id: IdPath,
    request: Request,
    session: DbSession,
    caller: InstructorCaller,
    today: Today,
) -> MySurveyResultsOut:
    settings: Settings = request.app.state.settings
    view = await results.instructor_results(
        session,
        caller,
        course_id=course_id,
        today=today,
        min_responses=settings.survey_min_responses,
    )
    return MySurveyResultsOut(
        head=head_out(view.head),
        response_rate=rate_out(view.responses, view.total, view.percent),
        visible=view.visible,
        reason=view.reason,
        min_responses=view.min_responses,
        results=(
            None
            if view.aggregate is None
            else results_body(view.head.row.questions, view.aggregate)
        ),
    )
