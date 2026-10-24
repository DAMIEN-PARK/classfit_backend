"""배포 설문 끝점(관리자만, AdminCaller, T8 계획 결정 i·ii·iii·vi·vii·xi·xiii·xviii·xix·xxv·xxvi).

- GET /v1/admin/surveys?course_id=&status=: 키셋 커서 {items, next_cursor, has_more}, (created_at, id) 내림차순. 첫
  WHERE 는 주체 범위다. status 는 오늘(Today) 기준 계산 상태(scheduled·open·closed)로 거른다. 깨진 커서는 422 loc
  ["query", "cursor"].
- POST /v1/admin/surveys {course_ids, template_id, open {mode, date?}, close {mode, date?}}: 강의마다 설문 한 행을 한
  트랜잭션에 만든다(201 {items}, 강의 id 순). 모드는 잠근 강의마다 날짜로 푼다(닫힘 기본은 종료일 + survey_close_days).
  현재 설문이 예약·열림인 강의 · 보관 강의는 409 이고 하나라도 409 면 전부 0행이다. 닫힌 현재 설문은 밀려난다
  (current false). 풀린 날짜가 어긋나면 422(그 강의 id 를 msg 에). 없는 양식·강의 404.
- PATCH …/{survey_id} {questions?, open_on?, close_on?}: 문항은 응답 0건일 때만(아니면 409 — 문항 잠금) · 열림일은
  예약일 때만 · 닫힘일은 예약·열림일 때만. 밀려난 설문은 전부 409. 바뀐 칸이 없으면 200 · audit 없음.
- POST …:close: 예약·열림 → 닫힘(closed_at, 닫힘 알림은 배정 강사에게). POST …:reopen: 닫힌 현재 설문을 연다(닫힘일은
  max(닫힘일, 오늘 + 7), 열리기 전에 닫힌 설문은 열림일을 오늘로). 기존 응답자는 다시 내지 못한다.
- GET …/results: A5 결과(머리 · 응답률 · 종합 · 영역 · 문항 · 주관식). 관리자는 임계 없이 본다. 사람 칸·제출 시각 없음.
- 경로 id 는 IdPath(밖이면 DB 를 치지 않고 422 loc ["path", "survey_id"]). 없는 설문 404.
- results_body·head_out 은 강사 결과(survey_learner)도 쓴다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import AdminCaller, DbSession, Today
from classfit.app.endpoints.assign import IdPath
from classfit.app.endpoints.survey_templates import questions_invalid
from classfit.core.config import Settings
from classfit.schemas.course import DB_ID_LIMIT
from classfit.schemas.page import Page
from classfit.schemas.survey import (
    DeployIn,
    DeployOut,
    SurveyHeadOut,
    SurveyOut,
    SurveyPatchIn,
    SurveyStatus,
)
from classfit.schemas.survey_results import (
    AreaOut,
    ChoiceStatOut,
    QuestionResultOut,
    ResponseRateOut,
    ResultsBodyOut,
    ScaleStatOut,
    SurveyResultsOut,
    TextResultOut,
    ValueCountOut,
)
from classfit.service.rules.survey import DatesRejected
from classfit.service.rules.survey_stats import Aggregate, ChoiceStat, ScaleStat
from classfit.service.surveys import close, deploy, results, views
from classfit.service.surveys.templates import QuestionsRejected

router = APIRouter(prefix="/v1/admin", tags=["surveys"])

_ONE = {404: {"description": "설문이 없음"}}
_STATE = {**_ONE, 409: {"description": "지금 상태에서 할 수 없음(밀려난 설문 포함)"}}


# ── 응답 조립(강사 결과도 쓴다)


def survey_out(head: views.SurveyHead) -> SurveyOut:
    row = head.row
    return SurveyOut(
        id=row.id,
        course_id=row.course_id,
        course_title=head.course_title,
        client_name=head.client_name,
        template_id=row.template_id,
        template_name=row.template_name,
        status=head.status,
        open_on=row.open_on,
        close_on=row.close_on,
        closed_at=row.closed_at,
        reopened_at=row.reopened_at,
        current=row.current,
        responses=head.responses,
        total=head.total,
        locked=head.locked,
        created_at=row.created_at,
    )


def head_out(head: views.SurveyHead) -> SurveyHeadOut:
    row = head.row
    return SurveyHeadOut(
        survey_id=row.id,
        course_id=row.course_id,
        course_title=head.course_title,
        client_name=head.client_name,
        template_name=row.template_name,
        status=head.status,
        open_on=row.open_on,
        close_on=row.close_on,
        reopened_at=row.reopened_at,
        current=row.current,
        responses=head.responses,
        total=head.total,
        locked=head.locked,
    )


def rate_out(responses: int, total: int, percent: int | None) -> ResponseRateOut:
    return ResponseRateOut(responses=responses, total=total, percent=percent)


def _scale(stat: ScaleStat) -> ScaleStatOut:
    return ScaleStatOut(
        n=stat.n,
        avg=None if stat.avg is None else float(stat.avg),
        hundred=stat.hundred,
        positive_pct=stat.positive_pct,
        distribution={str(k): v for k, v in stat.distribution.items()},
    )


def _stat(stat: ScaleStat | ChoiceStat | None) -> ScaleStatOut | ChoiceStatOut | None:
    if isinstance(stat, ScaleStat):
        return _scale(stat)
    if isinstance(stat, ChoiceStat):
        return ChoiceStatOut(
            n=stat.n,
            values=[ValueCountOut(value=v, count=c) for v, c in stat.values],
        )
    return None


def results_body(
    questions: Sequence[Mapping[str, Any]], agg: Aggregate
) -> ResultsBodyOut:
    """문항 스냅샷(설문 문항 순)과 집계를 응답 모양으로. 주관식은 빈 값을 뺀 글자 목록(글자 순)이다."""
    return ResultsBodyOut(
        overall=None if agg.overall is None else _scale(agg.overall),
        areas=[
            AreaOut(
                area=a.area,
                n=a.n,
                avg=None if a.avg is None else float(a.avg),
                hundred=a.hundred,
                positive_pct=a.positive_pct,
                questions=list(a.questions),
            )
            for a in agg.areas
        ],
        questions=[
            QuestionResultOut(
                key=q["key"],
                text=q["text"],
                type=q["type"],
                area=q["area"],
                star=q["star"],
                is_overall=q["is_overall"],
                stat=_stat(agg.questions.get(q["key"])),
            )
            for q in questions
        ],
        texts=[
            TextResultOut(key=q["key"], text=q["text"], items=list(agg.texts[q["key"]]))
            for q in questions
            if q["key"] in agg.texts
        ],
    )


# rules.survey.DatesRejected 의 까닭 → 안내 글자
_DATES = {
    "open_before_today": "열림일이 오늘보다 앞입니다",
    "close_before_open": "닫힘일이 열림일보다 앞입니다",
    "close_before_today": "닫힘일이 오늘보다 앞입니다",
}


def _deploy_loc(reason: str) -> tuple[str, ...]:
    return ("open" if reason.startswith("open") else "close", "date")


def _patch_loc(reason: str, sent: set[str]) -> tuple[str, ...]:
    """문제 칸이 본문에 없으면(open_on 만 늦춰 저장된 닫힘일보다 뒤가 됨) 보낸 날짜 칸을 가리킨다."""
    field = "open_on" if reason.startswith("open") else "close_on"
    if field not in sent:
        field = next((f for f in ("open_on", "close_on") if f in sent), field)
    return (field,)


def _dates_invalid(exc: DatesRejected, loc: tuple[str, ...]) -> RequestValidationError:
    """강의마다 푼 날짜 · PATCH 결과 날짜가 어긋남 → 422. 배포는 그 강의 id 를 msg 에 담는다."""
    msg = _DATES.get(exc.reason, exc.reason)
    if exc.course_id is not None:
        msg = f"강의 {exc.course_id}: {msg}"
    return RequestValidationError(
        [{"loc": ("body", *loc), "msg": msg, "type": exc.reason}]
    )


# ── 끝점


@router.get("/surveys", response_model=Page[SurveyOut])
async def list_surveys(
    session: DbSession,
    caller: AdminCaller,
    today: Today,
    course_id: Annotated[int | None, Query(ge=1, lt=DB_ID_LIMIT)] = None,
    status: SurveyStatus | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[SurveyOut]:
    try:
        heads, next_cursor, has_more = await views.admin_list(
            session,
            caller,
            course_id=course_id,
            status=status,
            today=today,
            cursor=cursor,
            limit=limit,
        )
    except views.InvalidCursor:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "cursor"),
                    "msg": "깨진 커서입니다",
                    "type": "value_error",
                }
            ]
        ) from None
    return Page[SurveyOut](
        items=[survey_out(h) for h in heads],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post(
    "/surveys",
    response_model=DeployOut,
    status_code=201,
    responses={
        404: {"description": "양식·강의가 없음"},
        409: {"description": "현재 설문이 예약·열림인 강의 · 보관 강의(전부 0행)"},
        422: {"description": "모양 · 풀린 날짜가 오늘·열림일보다 앞"},
    },
)
async def deploy_surveys(
    body: DeployIn,
    request: Request,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> DeployOut:
    settings: Settings = request.app.state.settings
    try:
        rows = await deploy.deploy(
            session,
            course_ids=body.course_ids,
            template_id=body.template_id,
            open=body.open.model_dump(),
            close=body.close.model_dump(),
            today=today,
            close_days=settings.survey_close_days,
            actor=f"admin:{caller.id}",
        )
    except DatesRejected as exc:
        raise _dates_invalid(exc, _deploy_loc(exc.reason)) from None
    return DeployOut(
        items=[survey_out(h) for h in await views.heads_of(session, rows, today=today)]
    )


@router.patch(
    "/surveys/{survey_id}",
    response_model=SurveyOut,
    responses={**_STATE, 422: {"description": "모양 · 문항 교차 규칙 · 날짜 범위"}},
)
async def patch_survey(
    survey_id: IdPath,
    body: SurveyPatchIn,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> SurveyOut:
    try:
        row = await close.patch_survey(
            session,
            survey_id=survey_id,
            changes=body.model_dump(include=set(body.model_fields_set)),
            today=today,
            actor=f"admin:{caller.id}",
        )
    except QuestionsRejected as exc:
        raise questions_invalid(exc) from None
    except DatesRejected as exc:
        raise _dates_invalid(exc, _patch_loc(exc.reason, body.model_fields_set)) from None
    return survey_out(await views.head_of(session, row, today=today))


@router.post("/surveys/{survey_id}:close", response_model=SurveyOut, responses=_STATE)
async def close_survey(
    survey_id: IdPath, session: DbSession, caller: AdminCaller, today: Today
) -> SurveyOut:
    row = await close.close_survey(
        session, survey_id=survey_id, today=today, actor=f"admin:{caller.id}"
    )
    return survey_out(await views.head_of(session, row, today=today))


@router.post("/surveys/{survey_id}:reopen", response_model=SurveyOut, responses=_STATE)
async def reopen_survey(
    survey_id: IdPath, session: DbSession, caller: AdminCaller, today: Today
) -> SurveyOut:
    row = await close.reopen_survey(
        session, survey_id=survey_id, today=today, actor=f"admin:{caller.id}"
    )
    return survey_out(await views.head_of(session, row, today=today))


@router.get(
    "/surveys/{survey_id}/results", response_model=SurveyResultsOut, responses=_ONE
)
async def survey_results(
    survey_id: IdPath, session: DbSession, _: AdminCaller, today: Today
) -> SurveyResultsOut:
    view = await results.admin_results(session, survey_id=survey_id, today=today)
    body = results_body(view.head.row.questions, view.aggregate)
    return SurveyResultsOut(
        head=head_out(view.head),
        response_rate=rate_out(view.responses, view.total, view.percent),
        overall=body.overall,
        areas=body.areas,
        questions=body.questions,
        texts=body.texts,
    )
