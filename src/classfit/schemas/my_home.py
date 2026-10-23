"""강사 홈·초대코드·명단 모양(T6 계획 결정 xiii·xiv·xxi).

- 홈은 화면 단위 조립이다: 강사 상태 · 강의 셈 · 배정 강의 표(courses_more) · 강의안 없는 내 세션 할 일(todo_more) ·
  안 낸 필수 서류 종류 id · 가능 과정 수. 강의는 보관 안 한 배정 강의이고 상태는 오늘 기준 계산값이다.
  수강생 개인 칸은 없다. 만족도 알림(T8) 칸은 아직 없다.
- 미기록(T7 결정 xv)은 종료·보관 아닌 범위 강의의 내 세션 가운데 일차 날짜 ≤ 오늘 ∧ 기록 없음이다(records_todo ·
  records_todo_more). 항목 모양은 할 일과 같은 MyTodoOut 이다.
- 초대코드는 관리자 InviteCodeOut 칸 + enrolled(등록 수)다. 강사는 읽기만 한다(재발급·정지·정원 경로 없음).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from classfit.schemas.course import CourseStatus
from classfit.schemas.instructor import InstructorStatus
from classfit.schemas.invite_code import CodeState, InviteCodeOut


class MyHomeSummaryOut(BaseModel):
    courses: int
    running: int
    prep: int
    ended: int
    my_sessions: int
    my_ready: int  # 첨부가 하나라도 있는 내 세션


class MyHomeCourseOut(BaseModel):
    id: int
    title: str
    course_type: str | None
    client_name: str
    status: CourseStatus
    start_on: dt.date
    end_on: dt.date
    my_sessions: int
    my_ready: int
    code: str | None  # 산 초대코드(없으면 null)
    code_state: CodeState | None


class MyTodoOut(BaseModel):
    """내 세션 하나 — 할 일(첨부 0개)과 미기록(T7) 항목이 같은 모양이다."""

    course_id: int
    course_title: str
    section_id: int
    section_title: str
    session_id: int
    session_title: str
    day_no: int | None
    slot: int | None


class MyHomeOut(BaseModel):
    status: InstructorStatus
    summary: MyHomeSummaryOut
    courses: list[MyHomeCourseOut]  # 진행 → 준비 → 종료, 시작일, id
    courses_more: bool
    todo: list[MyTodoOut]  # 강의 시작일, 강의 id, 일차(미정은 뒤), 교시, 세션 id
    todo_more: bool
    records_todo: list[MyTodoOut]  # 일차 날짜, 강의 id, 교시(미정은 뒤), 세션 id
    records_todo_more: bool
    documents_missing: list[str]  # 안 낸 필수 서류 종류 id, 종류 (sort, id) 순
    capable: int  # 내 역량 + 활성 고유 과정 + 활성 커리큘럼


class MyInviteCodeOut(InviteCodeOut):
    enrolled: int  # 그 강의 등록 수


class MyRosterOut(BaseModel):
    """강사 명단은 이메일·전화·id 칸을 싣지 않는다(키셋 커서 안의 id 는 제외, T6 결정 xxi, 정본과 다름 — spec 3절).

    name·dept 는 그 강의 등록의 값, enrolled_at 은 등록일(입장한 때)이다.
    """

    name: str
    dept: str | None
    enrolled_at: dt.datetime
