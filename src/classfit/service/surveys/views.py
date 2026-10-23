"""설문 읽기 모양(T8 결정 viii·xi·xxv): 양식 한 행 TemplateView · 설문 머리 SurveyHead · 관리자 목록. 읽기만 한다.

- 속성 이름이 응답 칸 이름이다(끝점이 from_attributes 로 읽는다). 사람 칸은 없다.
- 머리는 설문 행 + 강의 제목·고객사 + 오늘 상태 + 응답 수 + 지금 등록 수(응답률 분모) + 문항 잠김(응답 ≥ 1)이다.
  여러 설문의 머리는 질의 셋(강의 머리 · 응답 수 · 등록 수)으로 한 번에 만든다(heads_of).
- 목록은 crud.survey.list_stmt(첫 WHERE course_scope) + 키셋 커서. 깨진 커서만 InvalidCursor(ValueError)로 바꾼다
  (끝점이 422 loc ["query","cursor"]) — keyset_page 호출만 감싼다.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import survey as crud_survey
from classfit.crud import survey_response as crud_survey_response
from classfit.crud import survey_template as crud_survey_template
from classfit.crud.page import keyset_page
from classfit.crud.scope import Subject
from classfit.models import Survey, SurveyTemplate
from classfit.service.rules.survey import SurveyStatus, status_at

NO_TEMPLATE = "양식이 없습니다"


class InvalidCursor(ValueError):
    """깨진 키셋 커서. 끝점은 이 예외만 422 loc ["query","cursor"] 로 바꾼다."""


@dataclass(frozen=True)
class TemplateView:
    """양식 한 행과 그 양식으로 배포한 설문 수(deployed — 밀려난 설문 포함)."""

    row: SurveyTemplate
    deployed: int

    @property
    def id(self) -> int:
        return self.row.id

    @property
    def name(self) -> str:
        return self.row.name

    @property
    def note(self) -> str | None:
        return self.row.note

    @property
    def is_default(self) -> bool:
        return self.row.is_default

    @property
    def questions(self) -> list[dict[str, Any]]:
        return self.row.questions

    @property
    def created_at(self) -> dt.datetime:
        return self.row.created_at

    @property
    def updated_at(self) -> dt.datetime:
        return self.row.updated_at


@dataclass(frozen=True)
class SurveyHead:
    """설문 머리. 목록 항목(SurveyOut)과 결과 머리(SurveyHeadOut)가 같은 값을 읽는다 — created_at·closed_at 은 목록에만 싣는다."""

    row: Survey
    course_title: str
    client_name: str
    status: SurveyStatus  # 오늘 기준
    responses: int
    total: int  # 지금 등록 수
    locked: bool  # 응답 ≥ 1 → 문항 잠김

    @property
    def id(self) -> int:
        return self.row.id

    @property
    def survey_id(self) -> int:
        return self.row.id

    @property
    def course_id(self) -> int:
        return self.row.course_id

    @property
    def template_id(self) -> int | None:
        return self.row.template_id

    @property
    def template_name(self) -> str:
        return self.row.template_name

    @property
    def open_on(self) -> dt.date:
        return self.row.open_on

    @property
    def close_on(self) -> dt.date:
        return self.row.close_on

    @property
    def closed_at(self) -> dt.datetime | None:
        return self.row.closed_at

    @property
    def reopened_at(self) -> dt.datetime | None:
        return self.row.reopened_at

    @property
    def current(self) -> bool:
        return self.row.current

    @property
    def created_at(self) -> dt.datetime:
        return self.row.created_at


def status_of(row: Survey, today: dt.date) -> SurveyStatus:
    return status_at(
        open_on=row.open_on, close_on=row.close_on, closed_at=row.closed_at, today=today
    )


def head_from(
    row: Survey,
    *,
    course_title: str,
    client_name: str,
    responses: int,
    total: int,
    today: dt.date,
) -> SurveyHead:
    return SurveyHead(
        row=row,
        course_title=course_title,
        client_name=client_name,
        status=status_of(row, today),
        responses=responses,
        total=total,
        locked=responses > 0,
    )


async def heads_of(
    session: AsyncSession, rows: Sequence[Survey], *, today: dt.date
) -> list[SurveyHead]:
    """설문들의 머리(rows 순서). 질의 셋 — 강의 머리 · 응답 수 · 등록 수."""
    headers = await crud_survey.course_header(session, [r.id for r in rows])
    responses = await crud_survey_response.counts_for(session, [r.id for r in rows])
    totals = await crud_survey.enrollment_counts(session, {r.course_id for r in rows})
    return [
        head_from(
            r,
            course_title=headers[r.id][0],
            client_name=headers[r.id][1],
            responses=responses[r.id],
            total=totals[r.course_id],
            today=today,
        )
        for r in rows
    ]


async def head_of(session: AsyncSession, row: Survey, *, today: dt.date) -> SurveyHead:
    (head,) = await heads_of(session, [row], today=today)
    return head


async def admin_list(
    session: AsyncSession,
    subject: Subject,
    *,
    course_id: int | None,
    status: str | None,
    today: dt.date,
    cursor: str | None,
    limit: int,
) -> tuple[list[SurveyHead], str | None, bool]:
    """관리자 설문 목록 한 쪽 — (머리들, 다음 커서, 더 있는지). (created_at, id) 내림차순, 밀려난 설문도 든다."""
    stmt = crud_survey.list_stmt(
        subject, course_id=course_id, status=status, today=today
    )
    try:
        rows, next_cursor, has_more = await keyset_page(session, stmt, cursor, limit)
    except ValueError as exc:
        raise InvalidCursor(str(exc)) from exc
    return await heads_of(session, rows, today=today), next_cursor, has_more


async def template_views(
    session: AsyncSession, rows: Sequence[SurveyTemplate]
) -> list[TemplateView]:
    deployed = await crud_survey_template.deployed_counts(session, [r.id for r in rows])
    return [TemplateView(r, deployed[r.id]) for r in rows]


async def template_view(session: AsyncSession, row: SurveyTemplate) -> TemplateView:
    (view,) = await template_views(session, [row])
    return view


async def list_templates(session: AsyncSession) -> list[TemplateView]:
    """양식 전부(이름 → id). 수십 개라 커서가 없다."""
    return await template_views(
        session, await crud_survey_template.list_templates(session)
    )


async def get_template(session: AsyncSession, template_id: int) -> TemplateView:
    row = await crud_survey_template.get_template(session, template_id)
    if row is None:
        raise NotFound(NO_TEMPLATE)
    return await template_view(session, row)
