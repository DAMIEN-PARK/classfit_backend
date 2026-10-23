"""강사 홈 조립(기획안 I1 · T6 결정 xiv). 읽기만 한다.

- T6 까지의 표로 되는 칸만 준다: 강사 상태 · 셈(보관 안 한 범위 강의 · 상태별 · 내 세션 · 자료 있는 내 세션) ·
  강의 표(진행 → 준비 → 종료, 시작일, id — 산 코드와 코드 상태 포함) · 할 일(종료·보관 아닌 강의에서 첨부 0개인 내
  세션) · 안 낸 필수 서류 종류 · 가능 과정 셈(역량 + 활성 고유 과정 + 활성 커리큘럼).
- 미기록(T7 결정 xv): 종료·보관 아닌 범위 강의의 내 세션 가운데 일차 날짜 ≤ 오늘 ∧ 기록 없음(crud.record.record_todo_rows).
  항목 모양은 할 일과 같은 TodoRow, 상한도 HOME_TODO_MAX 다. 순서는 일차 날짜 → 강의 id → 교시(미정 뒤) → 세션 id.
- 목록·셈의 첫 WHERE 는 주체 범위다(crud.my_home). 수강생 개인 칸은 없다. 대기 강사도 같은 모양이다(빈 목록).
- 만족도 알림(T8 결정 xvi): 보관 안 한 범위 강의의 현재 설문 전부(상한 HOME_TODO_MAX) — 닫힘일 내림차순 → 설문 id 내림차순,
  상태는 오늘 기준 SQL 판(crud.survey.home_rows), 응답 수와 지금 등록 수를 붙인다. 종합 점수는 싣지 않는다(결과 끝점 몫).
  시수는 1차 제외라 칸이 없다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import instructor as crud_instructor
from classfit.crud import instructor_document as crud_instructor_document
from classfit.crud import invite_code as crud_code
from classfit.crud import my_home as crud_my_home
from classfit.crud import record as crud_record
from classfit.crud import survey as crud_survey
from classfit.crud import survey_response as crud_survey_response
from classfit.crud.scope import Subject
from classfit.service.courses.codes import code_state_of
from classfit.service.rules.status import CodeState

HOME_COURSES_MAX = 50
HOME_TODO_MAX = 20


@dataclass(frozen=True)
class MyHomeCourse:
    """강의 표 한 행. 칸 이름이 응답 칸과 같다(끝점이 from_attributes 로 읽는다)."""

    id: int
    title: str
    course_type: str | None
    client_name: str
    status: str  # 오늘 기준 강의 상태
    start_on: dt.date
    end_on: dt.date
    my_sessions: int
    my_ready: int  # 첨부가 1개 이상인 내 세션
    code: str | None  # 산 코드가 없으면 None
    code_state: CodeState | None


@dataclass(frozen=True)
class MyHomeSurvey:
    """만족도 알림 한 행(T8). 칸 이름이 응답 칸과 같다."""

    course_id: int
    course_title: str
    survey_id: int
    status: str  # 오늘 기준 설문 상태
    open_on: dt.date
    close_on: dt.date
    reopened_at: dt.datetime | None
    responses: int
    total: int  # 지금 등록 수


@dataclass(frozen=True)
class MyHome:
    status: str  # 강사 상태
    summary: dict[str, int]  # courses · running · prep · ended · my_sessions · my_ready
    courses: list[MyHomeCourse]
    courses_more: bool
    todo: list[crud_my_home.TodoRow]
    todo_more: bool
    documents_missing: list[str]  # 안 낸 필수 서류 종류 id, 종류 (sort, id) 순
    capable: int
    records_todo: list[crud_my_home.TodoRow]  # 지난 일차의 기록 없는 내 세션(T7)
    records_todo_more: bool
    surveys: list[MyHomeSurvey]  # 범위 강의의 현재 설문(T8)
    surveys_more: bool


async def home_of(session: AsyncSession, subject: Subject, *, today: dt.date) -> MyHome:
    instructor = await crud_instructor.get_instructor(session, subject, subject.id)
    if instructor is None:
        raise NotFound("강사가 없습니다")
    summary = await crud_my_home.course_summary(session, subject, today=today)
    rows, courses_more = await crud_my_home.course_rows(
        session, subject, today=today, limit=HOME_COURSES_MAX
    )
    todo, todo_more = await crud_my_home.todo_rows(
        session, subject, today=today, limit=HOME_TODO_MAX
    )
    records_todo, records_todo_more = await crud_record.record_todo_rows(
        session, subject, today=today, limit=HOME_TODO_MAX
    )
    surveys, surveys_more = await _surveys(session, subject, today=today)
    codes = await crud_code.live_codes(session, [r.course.id for r in rows])
    courses = []
    for r in rows:
        code = codes.get(r.course.id)
        courses.append(
            MyHomeCourse(
                id=r.course.id,
                title=r.course.title,
                course_type=r.course.course_type,
                client_name=r.course.client_name,
                status=r.status,
                start_on=r.course.start_on,
                end_on=r.course.end_on,
                my_sessions=r.my_sessions,
                my_ready=r.my_ready,
                code=None if code is None else code.code,
                code_state=None
                if code is None
                else code_state_of(code, r.course, today),
            )
        )
    documents = await crud_instructor_document.list_documents(session, instructor.id)
    return MyHome(
        status=instructor.status,
        summary=summary,
        courses=courses,
        courses_more=courses_more,
        todo=todo,
        todo_more=todo_more,
        documents_missing=[
            t.id for t, doc, _ in documents if t.required and doc is None
        ],
        capable=await crud_my_home.capable_count(session, subject),
        records_todo=records_todo,
        records_todo_more=records_todo_more,
        surveys=surveys,
        surveys_more=surveys_more,
    )


async def _surveys(
    session: AsyncSession, subject: Subject, *, today: dt.date
) -> tuple[list[MyHomeSurvey], bool]:
    rows, more = await crud_survey.home_rows(
        session, subject, today=today, limit=HOME_TODO_MAX
    )
    responses = await crud_survey_response.counts_for(
        session, [r.survey_id for r in rows]
    )
    totals = await crud_survey.enrollment_counts(session, {r.course_id for r in rows})
    return [
        MyHomeSurvey(
            course_id=r.course_id,
            course_title=r.course_title,
            survey_id=r.survey_id,
            status=r.status,
            open_on=r.open_on,
            close_on=r.close_on,
            reopened_at=r.reopened_at,
            responses=responses[r.survey_id],
            total=totals[r.course_id],
        )
        for r in rows
    ], more
