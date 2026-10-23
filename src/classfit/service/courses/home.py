"""강사 홈 조립(기획안 I1 · T6 결정 xiv). 읽기만 한다.

- T6 까지의 표로 되는 칸만 준다: 강사 상태 · 셈(보관 안 한 범위 강의 · 상태별 · 내 세션 · 자료 있는 내 세션) ·
  강의 표(진행 → 준비 → 종료, 시작일, id — 산 코드와 코드 상태 포함) · 할 일(종료·보관 아닌 강의에서 첨부 0개인 내
  세션) · 안 낸 필수 서류 종류 · 가능 과정 셈(역량 + 활성 고유 과정 + 활성 커리큘럼).
- 목록·셈의 첫 WHERE 는 주체 범위다(crud.my_home). 수강생 개인 칸은 없다. 대기 강사도 같은 모양이다(빈 목록).
- 만족도 알림(T8)·미기록(T7)·시수(1차 제외)는 칸이 없다.
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
class MyHome:
    status: str  # 강사 상태
    summary: dict[str, int]  # courses · running · prep · ended · my_sessions · my_ready
    courses: list[MyHomeCourse]
    courses_more: bool
    todo: list[crud_my_home.TodoRow]
    todo_more: bool
    documents_missing: list[str]  # 안 낸 필수 서류 종류 id, 종류 (sort, id) 순
    capable: int


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
    )
