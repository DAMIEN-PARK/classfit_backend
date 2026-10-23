"""T8 시험 도우미: 오늘 · 기본 양식 답 · 배포 · 수강생 둘 · 제출 · 응답 키 집합.

- 시험 강의는 2026-11-02(월)부터 4일(tests/fixtures/courses.py DEFAULTS, 끝 날 11-05)이라 TODAY_RUNNING = 11-03(진행 중),
  TODAY_AFTER = 11-20(종료 + 14 = 11-19 다음 날 — 기본 닫힘일이 지났다).
- deploy_to 는 운영 경로 service.surveys.deploy.deploy 를 부른다(기본 열림 now · 닫힘 end_plus_14 · 기본 양식).
- ANSWERS_OK 는 기본 양식 24문항 가운데 안내문 말고 전부, ANSWERS_REQUIRED_ONLY 는 필수 17문항만 채운 답이다.
- submit 은 본 설문판(survey_id · questions_hash)을 받아 보낸다. submit_current 는 수강생 조회로 그 둘을 읽어 보낸다.
- 키 집합은 응답 모양의 정확한 키(==)다(T8 결정 xxv). 분포(distribution)의 키는 "1"~"5" 다(DISTRIBUTION_KEYS).
  RESULTS_KEYS·MY_RESULTS_KEYS 는 재귀 허용 집합(tests/fixtures/enter.py json_keys 와 ==)이고, 맨 위 키는
  RESULTS_TOP_KEYS·MY_RESULTS_TOP_KEYS 다.
  RESULT_FORBIDDEN_KEYS 는 결과(A5·I7)에 있으면 안 되는 키다. tests/fixtures/enter.py 의 PERSONAL_KEYS 는 바꾸지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import survey_template as crud_survey_template
from classfit.models import Survey
from classfit.service.surveys.deploy import deploy
from tests.fixtures.enter import bearer, enter_learner

TODAY_RUNNING = date(2026, 11, 3)
TODAY_AFTER = date(2026, 11, 20)
CLOSE_DAYS = 14
LEARNER = "/v1/learner/courses"

ANSWERS_REQUIRED_ONLY: dict[str, Any] = {
    "dept": "영업",
    "job": "영업·마케팅",
    "exp": "가끔 사용",
    "part": "전체 참여",
    "b01": 5,
    "b02": 4,
    "b03": 4,
    "b04": 5,
    "b05": 5,
    "b06": 4,
    "b07": 4,
    "b08": 3,
    "b09": 4,
    "b10": 5,
    "b11": 4,
    "b12": 5,
    "overall": 5,
}
ANSWERS_OK: dict[str, Any] = ANSWERS_REQUIRED_ONLY | {
    "c1": "보안 마스킹 기준",
    "c2": "실습 시간이 더 있으면 좋겠다",
    "c3": "부서별 자동화 사례",
    "next_type": ["심화 실습"],
    "next_when": "3개월 이내",
    "next_how": "혼합",
}

QUESTION_KEYS = frozenset(
    {
        "key",
        "type",
        "text",
        "area",
        "required",
        "star",
        "is_overall",
        "options",
        "custom",
    }
)
TEMPLATE_KEYS = frozenset(
    {
        "id",
        "name",
        "note",
        "is_default",
        "questions",
        "deployed",
        "created_at",
        "updated_at",
    }
)
SURVEY_KEYS = frozenset(
    {
        "id",
        "course_id",
        "course_title",
        "client_name",
        "template_id",
        "template_name",
        "status",
        "open_on",
        "close_on",
        "closed_at",
        "reopened_at",
        "current",
        "responses",
        "total",
        "locked",
        "created_at",
    }
)
# 결과 머리 — 시각 칸(created_at · closed_at)이 없다
HEAD_KEYS = frozenset(
    {
        "survey_id",
        "course_id",
        "course_title",
        "client_name",
        "template_name",
        "status",
        "open_on",
        "close_on",
        "reopened_at",
        "current",
        "responses",
        "total",
        "locked",
    }
)
LEARNER_SURVEY_KEYS = frozenset({"status", "survey", "responded", "prefill_dept"})
LEARNER_SURVEY_BODY_KEYS = frozenset(
    {"id", "open_on", "close_on", "questions_hash", "questions"}
)
RESPONSE_RATE_KEYS = frozenset({"responses", "total", "percent"})
SCALE_STAT_KEYS = frozenset({"n", "avg", "hundred", "positive_pct", "distribution"})
DISTRIBUTION_KEYS = frozenset({"1", "2", "3", "4", "5"})
CHOICE_STAT_KEYS = frozenset({"n", "values"})
VALUE_COUNT_KEYS = frozenset({"value", "count"})
AREA_KEYS = frozenset({"area", "n", "avg", "hundred", "positive_pct", "questions"})
QUESTION_RESULT_KEYS = frozenset(
    {"key", "text", "type", "area", "star", "is_overall", "stat"}
)
TEXT_RESULT_KEYS = frozenset({"key", "text", "items"})
RESULTS_BODY_KEYS = frozenset({"overall", "areas", "questions", "texts"})
RESULTS_TOP_KEYS = RESULTS_BODY_KEYS | {"head", "response_rate"}
MY_RESULTS_TOP_KEYS = frozenset(
    {"head", "response_rate", "visible", "reason", "min_responses", "results"}
)
# 결과 안쪽(척도·선택형·영역·문항·주관식)에 나오는 키
_STAT_KEYS = (
    SCALE_STAT_KEYS
    | DISTRIBUTION_KEYS
    | CHOICE_STAT_KEYS
    | VALUE_COUNT_KEYS
    | AREA_KEYS
    | QUESTION_RESULT_KEYS
    | TEXT_RESULT_KEYS
)
# 재귀 허용 집합(json_keys == 로 잰다): A5 전체 · I7 공개(visible)일 때 전체. 숨김이면 results 가 null 이라 이 집합의 부분이다
RESULTS_KEYS = RESULTS_TOP_KEYS | HEAD_KEYS | RESPONSE_RATE_KEYS | _STAT_KEYS
MY_RESULTS_KEYS = (
    MY_RESULTS_TOP_KEYS | RESULTS_BODY_KEYS | HEAD_KEYS | RESPONSE_RATE_KEYS | _STAT_KEYS
)
PORTAL_SURVEY_KEYS = frozenset({"id", "status", "open_on", "close_on"})
HOME_SURVEY_KEYS = frozenset(
    {
        "course_id",
        "course_title",
        "survey_id",
        "status",
        "open_on",
        "close_on",
        "reopened_at",
        "responses",
        "total",
    }
)
# 결과(A5·I7)에 있으면 안 되는 키(Design 1절 만족도 공개 범위 · codex 1차 #3)
RESULT_FORBIDDEN_KEYS = frozenset(
    {
        "submitted_at",
        "enrollment_id",
        "learner_id",
        "email",
        "name",
        "phone",
        "answers",
        "created_at",
    }
)


async def default_template_id(session: AsyncSession) -> int:
    row = await crud_survey_template.default_template(session)
    assert row is not None, "기본 양식 시드가 없다"
    return row.id


async def deploy_to(
    session: AsyncSession,
    course_ids: Sequence[int],
    *,
    template_id: int | None = None,
    open: dict[str, Any] | None = None,
    close: dict[str, Any] | None = None,
    today: date = TODAY_RUNNING,
) -> list[Survey]:
    """운영 경로로 배포한다(기본 양식 · 열림 now · 닫힘 end_plus_14 · actor admin:1)."""
    if template_id is None:
        template_id = await default_template_id(session)
    return await deploy(
        session,
        course_ids=course_ids,
        template_id=template_id,
        open=open or {"mode": "now"},
        close=close or {"mode": "end_plus_14"},
        today=today,
        close_days=CLOSE_DAYS,
        actor="admin:1",
    )


async def enter_two(client: httpx.AsyncClient, code: str) -> list[dict[str, str]]:
    """수강생 둘(가명1 · 영업 / 가명2 · 부서 없음)을 입장시켜 Bearer 헤더 둘."""
    headers = []
    for i, dept in ((1, "영업"), (2, None)):
        extra = {} if dept is None else {"dept": dept}
        r = await enter_learner(client, code, f"s{i}@example.com", f"가명{i}", **extra)
        assert r.status_code in (200, 201), r.text
        headers.append(bearer(r.json()["access_token"]))
    return headers


async def submit(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    course_id: int,
    *,
    survey_id: int,
    questions_hash: str,
    answers: dict[str, Any] = ANSWERS_OK,
) -> httpx.Response:
    return await client.post(
        f"{LEARNER}/{course_id}/survey/responses",
        headers=headers,
        json={
            "survey_id": survey_id,
            "questions_hash": questions_hash,
            "answers": answers,
        },
    )


async def submit_current(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    course_id: int,
    answers: dict[str, Any] = ANSWERS_OK,
) -> httpx.Response:
    """수강생 조회로 지금 열린 설문의 id·해시를 읽어 제출한다(열린 설문이 없으면 실패)."""
    r = await client.get(f"{LEARNER}/{course_id}/survey", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()["survey"]
    assert body is not None, r.text
    return await submit(
        client,
        headers,
        course_id,
        survey_id=body["id"],
        questions_hash=body["questions_hash"],
        answers=answers,
    )
