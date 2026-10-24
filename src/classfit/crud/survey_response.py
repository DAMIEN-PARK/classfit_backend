"""survey_response(설문 응답) 넣기·읽기와 결과 읽기(T8 결정 ix·xi·xii·xiv). flush 까지만.

- 응답 행은 넣기만 한다(고치기·지우기 없음). (설문, 등록) 하나 — 두 번째는 유일 제약이 409 로 뒷받침한다(insert_response).
  잠금은 부르는 쪽이 설문 행(crud.survey.lock_survey)을 먼저 잡는다(결정 xix).
- 집계는 answers 만 읽는다. 응답 id · enrollment_id · submitted_at 은 결과 읽기에서 고르지 않는다(Design 1절 만족도 공개 범위).
- 결과 읽기는 한 문장이다: survey_with_answers(A5) · current_with_answers(I7)가 설문 행 · 강의 행(머리의 제목·고객사) ·
  답 배열(coalesce(jsonb_agg(answers), '[]'))을 SELECT 하나로 읽어 상태·응답 수·집계가 한 스냅샷이다(READ COMMITTED 는
  문장마다 스냅샷이 다르다, codex 1차 #9). populate_existing 으로 같은 트랜잭션이 앞서 적재한 칸을 덮는다.
- 명단의 응답 여부는 responded_ids(등록 id 집합)만 준다 — 답과 잇는 칸이 없다(결정 xiv).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from classfit.crud.flush import flush_or_conflict
from classfit.models import Course, Survey, SurveyResponse

ALREADY = "이미 응답한 설문입니다"
# (설문, 그 강의, 응답들의 answers)
SurveyAnswers = tuple[Survey, Course, list[dict[str, Any]]]


async def insert_response(
    session: AsyncSession,
    *,
    survey_id: int,
    enrollment_id: int,
    answers: dict[str, Any],
) -> SurveyResponse:
    row = SurveyResponse(
        survey_id=survey_id, enrollment_id=enrollment_id, answers=answers
    )
    await flush_or_conflict(session, ALREADY, row)
    return row


async def find_response(
    session: AsyncSession,
    survey_id: int,
    enrollment_id: int,
    *,
    fresh: bool = False,
) -> SurveyResponse | None:
    stmt = select(SurveyResponse).where(
        SurveyResponse.survey_id == survey_id,
        SurveyResponse.enrollment_id == enrollment_id,
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def count_responses(session: AsyncSession, survey_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(SurveyResponse)
        .where(SurveyResponse.survey_id == survey_id)
    )
    return await session.scalar(stmt) or 0


async def counts_for(
    session: AsyncSession, survey_ids: Collection[int]
) -> dict[int, int]:
    """설문 id → 응답 수(한 문장 GROUP BY). 응답이 없으면 0."""
    wanted = list(survey_ids)
    counts = dict.fromkeys(wanted, 0)
    if not wanted:
        return counts
    stmt = (
        select(SurveyResponse.survey_id, func.count())
        .where(SurveyResponse.survey_id.in_(wanted))
        .group_by(SurveyResponse.survey_id)
    )
    for survey_id, n in (await session.execute(stmt)).all():
        counts[survey_id] = n
    return counts


async def responded_ids(
    session: AsyncSession, survey_id: int, enrollment_ids: Collection[int]
) -> set[int]:
    """준 등록 가운데 그 설문에 응답한 등록 id(명단 한 쪽 ≤ 100행 — 질의 한 번)."""
    wanted = list(enrollment_ids)
    if not wanted:
        return set()
    stmt = select(SurveyResponse.enrollment_id).where(
        SurveyResponse.survey_id == survey_id,
        SurveyResponse.enrollment_id.in_(wanted),
    )
    return set((await session.scalars(stmt)).all())


def _answers() -> ColumnElement[Any]:
    """바깥 survey 행의 응답 answers 배열(응답 0건이면 NULL 이 아니라 빈 배열). answers 말고는 고르지 않는다."""
    return (
        select(
            func.coalesce(
                func.jsonb_agg(SurveyResponse.answers),
                literal_column("'[]'::jsonb", type_=JSONB),
                type_=JSONB,
            )
        )
        .where(SurveyResponse.survey_id == Survey.id)
        .correlate(Survey)
        .scalar_subquery()
    )


async def _with_answers(
    session: AsyncSession, *where: ColumnElement[bool]
) -> SurveyAnswers | None:
    stmt = (
        select(Survey, Course, _answers())
        .join(Course, Course.id == Survey.course_id)
        .where(*where)
        .execution_options(populate_existing=True)
    )
    found = (await session.execute(stmt)).first()
    if found is None:
        return None
    return found[0], found[1], list(found[2])


async def survey_with_answers(
    session: AsyncSession, survey_id: int
) -> SurveyAnswers | None:
    """A5: 그 설문 행 · 강의 행 · 답 배열을 SELECT 하나로. 없으면 None."""
    return await _with_answers(session, Survey.id == survey_id)


async def current_with_answers(
    session: AsyncSession, course_id: int
) -> SurveyAnswers | None:
    """I7: 그 강의의 현재 설문 행 · 강의 행 · 답 배열을 SELECT 하나로. 현재 설문이 없으면 None."""
    return await _with_answers(
        session, Survey.course_id == course_id, Survey.current.is_(True)
    )
