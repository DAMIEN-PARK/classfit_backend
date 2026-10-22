"""강의 상태와 초대코드 상태의 판정(Python 판). 오늘은 인자로 받는다(Design 5절 15).

강의 상태의 SQL 판은 crud/course.py 의 course_status_sql 한 곳이고, 경계는 이 파일과 같다.
- 강의: 수동 지정이면 저장값. 아니면 today > end_on → ended, today ≥ start_on → running, 그 밖 prep.
  종료일 당일은 running 이고 다음 날부터 ended 다(T2a 계획 착수 조건 결정 iii, 기획안 5-3).
- 코드: replaced → stopped(강의 ended) → paused → expired → active 순서로 먼저 맞는 것이다.
  만료일 당일까지 유효하다(결정 iii). 정원 마감은 enrollment 를 세는 T2b 몫이다.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

CourseStatus = Literal["prep", "running", "ended"]
CodeStatus = Literal["active", "paused", "replaced"]
CodeState = Literal["active", "paused", "replaced", "stopped", "expired"]


def course_status_at(
    *,
    start_on: date,
    end_on: date,
    status: CourseStatus,
    status_manual: bool,
    today: date,
) -> CourseStatus:
    """오늘의 강의 상태. status_manual 이면 저장된 status 가 날짜 규칙을 이긴다."""
    if status_manual:
        return status
    if today > end_on:
        return "ended"
    if today >= start_on:
        return "running"
    return "prep"


def code_state_at(
    *,
    code_status: CodeStatus,
    expires_on: date,
    course_status: CourseStatus,
    today: date,
) -> CodeState:
    """오늘의 초대코드 상태. course_status 는 course_status_at 의 결과(계산값)다."""
    if code_status == "replaced":
        return "replaced"
    if course_status == "ended":
        return "stopped"
    if code_status == "paused":
        return "paused"
    if today > expires_on:
        return "expired"
    return "active"
