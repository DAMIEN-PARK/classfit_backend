"""만족도 결과 모양 — 관리자 A5 · 강사 I7(T8 계획 결정 x·xi·xii·xiii).

- 집계만 싣는다. 사람 칸·응답 행 id·제출 시각·응답 원문 목록이 없다(Design 1절 만족도 공개 범위 · 원칙 10) — 주관식은
  texts[].items(빈 값을 뺀 글자 목록, 글자 순)이고 선택형·척도는 값마다의 수다. 머리(SurveyHeadOut)에도 시각 칸이 없다.
- 척도 지표: n(1..5 응답 수) · avg(산술 평균, 소수 둘째 자리) · hundred(100점 환산 = 평균 × 20) · positive_pct(4·5점
  비율) · distribution("1"~"5" 의 수). 응답 0건이면 avg·hundred·positive_pct 는 null 이다(0점처럼 보이지 않게).
- 영역은 그 영역 척도 응답 전체의 평균(응답 가중)이고 questions 는 그 영역의 문항 key 다. overall 은 is_overall 문항의
  지표(없거나 응답 0건이면 null). 산식은 service.rules.survey_stats 한 곳이다.
- 응답률은 응답 수 ÷ 조회 시점 등록 수(정수 %, 등록 0 이면 null).
- 강사 결과는 마감 뒤 + 최소 응답 수 이상일 때만 results 를 싣는다(아니면 visible false · reason). 응답률은 늘 준다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from classfit.schemas.survey import QuestionType, SurveyHeadOut


class ScaleStatOut(BaseModel):
    n: int
    avg: float | None
    hundred: int | None
    positive_pct: int | None
    distribution: dict[str, int]  # "1"~"5"


class ValueCountOut(BaseModel):
    value: str
    count: int


class ChoiceStatOut(BaseModel):
    n: int
    values: list[ValueCountOut]  # 수 내림차순 → 글자 순, 직접 입력 값도 각자 한 값


class AreaOut(BaseModel):
    area: str
    n: int
    avg: float | None
    hundred: int | None
    positive_pct: int | None
    questions: list[str]  # 그 영역의 척도 문항 key, 양식 순


class QuestionResultOut(BaseModel):
    key: str
    text: str
    type: QuestionType
    area: str | None
    star: bool
    is_overall: bool
    stat: ScaleStatOut | ChoiceStatOut | None  # 주관식·안내문은 null


class TextResultOut(BaseModel):
    key: str
    text: str
    items: list[str]


class ResponseRateOut(BaseModel):
    responses: int
    total: int
    percent: int | None


class ResultsBodyOut(BaseModel):
    overall: ScaleStatOut | None
    areas: list[AreaOut]  # 양식에 나온 영역 순
    questions: list[QuestionResultOut]  # 양식 순
    texts: list[TextResultOut]


class SurveyResultsOut(BaseModel):
    head: SurveyHeadOut
    response_rate: ResponseRateOut
    overall: ScaleStatOut | None
    areas: list[AreaOut]
    questions: list[QuestionResultOut]
    texts: list[TextResultOut]


class MySurveyResultsOut(BaseModel):
    head: SurveyHeadOut
    response_rate: ResponseRateOut
    visible: bool
    reason: Literal["not_closed", "below_minimum"] | None
    min_responses: int
    results: ResultsBodyOut | None
