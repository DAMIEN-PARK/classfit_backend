"""초대코드 조회(lookup_code)와 입장(enter_course). 결과 값만 돌려주고 예외를 던지지 않는다. flush 까지만.

판정 순서(T2b 계획 결정 ii):
  형식(혼동 문자 먼저) → 코드로 course_id 스칼라만 읽기 → 강의 행 잠금(lock_course, 없으면 not_found)
  → 코드 행을 populate_existing 으로 다시 읽기(없거나 replaced 면 not_found) → 이 강의에 그 이메일 등록이 있으면
  재입장(상태 무관, ADR-002 결정 4) → 코드 상태(stopped → paused → expired) → 정원 → 이름 필수 → 새 등록.
- 잠그기 전에는 코드·강의 ORM 행을 세션에 올리지 않는다. 잠금을 기다린 사이 커밋된 replaced·paused 를
  identity map 의 옛 행으로 놓치지 않게, 잠금 뒤에 새로 읽는다(orm/loading.py:1088-1094).
- 상태는 rules 의 course_status_at·code_state_at 를 직접 부른다(service.courses 는 계약 ② 밖).
- 재입장은 들어온 이름·부서를 무시하고 그 강의 enrollment 의 이름을 돌려준다(결정 iii, r3 N9).
- 정원은 그 강의 enrollment 수 ≥ 산 코드의 max_seats 다(결정 v). 준비 중 강의는 입장을 받고 notice 를 단다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import course as crud_course
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import invite_code as crud_code
from classfit.crud import learner as crud_learner
from classfit.models import Course, InviteCode
from classfit.service.rules.invite import parse_invite_input
from classfit.service.rules.status import (
    CodeState,
    CourseStatus,
    code_state_at,
    course_status_at,
)

LookupState = Literal["active", "preparing", "ended", "expired", "paused", "full"]
EnterOutcome = Literal[
    "created",
    "reentered",
    "confusable",
    "malformed",
    "not_found",
    "ended",
    "expired",
    "paused",
    "full",
    "name_required",
]
# 코드 상태 → 막힌 이유. replaced 는 잠금 뒤 다시 읽기에서 not_found 로 먼저 빠진다
_BLOCKED: dict[CodeState, Literal["ended", "paused", "expired"]] = {
    "stopped": "ended",
    "paused": "paused",
    "expired": "expired",
}


@dataclass(frozen=True)
class LookupResult:
    outcome: Literal["ok", "confusable", "malformed", "not_found"]
    course: Course | None = None
    course_status: CourseStatus | None = None
    state: LookupState | None = None
    notice: str | None = None

    @property
    def accepts_new(self) -> bool:
        """새 이메일의 등록을 받는지. 막힌 상태여도 기존 등록자는 재입장한다."""
        return self.state in ("active", "preparing")


@dataclass(frozen=True)
class EnterResult:
    outcome: EnterOutcome
    learner_id: int | None = None
    course_id: int | None = None
    name: str | None = None
    notice: str | None = None


def preparing_notice(course: Course, status: CourseStatus) -> str | None:
    """준비 중(prep) 강의의 안내 글자(기획안 P3). 그 밖은 None."""
    if status != "prep":
        return None
    return f"준비 중인 강의입니다. 시작일 {course.start_on.isoformat()}"


def _course_status(course: Course, today: date) -> CourseStatus:
    stored: CourseStatus = course.status  # type: ignore[assignment]  # CHECK 가 세 값으로 막는다
    return course_status_at(
        start_on=course.start_on,
        end_on=course.end_on,
        status=stored,
        status_manual=course.status_manual,
        today=today,
    )


def _code_state(code: InviteCode, status: CourseStatus, today: date) -> CodeState:
    return code_state_at(
        code_status=code.status,  # type: ignore[arg-type]  # CHECK 가 세 값으로 막는다
        expires_on=code.expires_on,
        course_status=status,
        today=today,
    )


async def _seats_full(session: AsyncSession, code: InviteCode) -> bool:
    if code.max_seats is None:
        return False
    taken = await crud_enrollment.count_enrollments(session, code.course_id)
    return taken >= code.max_seats


async def lookup_code(
    session: AsyncSession, *, raw_code: str, today: date
) -> LookupResult:
    """산 코드면 상태와 무관하게 ok + 강의 카드 + state(결정 i). 쓰지 않는다."""
    code = parse_invite_input(raw_code)
    if code == "confusable" or code == "malformed":
        return LookupResult(code)
    row = await crud_code.get_by_code_fresh(session, code)
    course = (
        await crud_course.get_course(session, row.course_id)
        if row is not None and row.status != "replaced"
        else None
    )
    if row is None or course is None:
        return LookupResult("not_found")
    status = _course_status(course, today)
    blocked = _BLOCKED.get(_code_state(row, status, today))
    state: LookupState
    if blocked is not None:
        state = blocked
    elif await _seats_full(session, row):
        state = "full"
    else:
        state = "preparing" if status == "prep" else "active"
    return LookupResult(
        "ok",
        course=course,
        course_status=status,
        state=state,
        notice=preparing_notice(course, status),
    )


async def enter_course(
    session: AsyncSession,
    *,
    raw_code: str,
    email: str,
    name: str | None,
    dept: str | None,
    today: date,
) -> EnterResult:
    """email 은 스키마가 정규화한 값(앞뒤 공백 없음 · 소문자)이다. 새 등록만 learner·enrollment 를 쓴다."""
    code = parse_invite_input(raw_code)
    if code == "confusable" or code == "malformed":
        return EnterResult(code)
    course_id = await crud_code.find_course_id_by_code(session, code)
    if course_id is None:
        return EnterResult("not_found")
    # 같은 강의의 입장·코드 관리·강의 삭제를 줄 세운다(결정 v). None 이면 그 사이 강의가 지워졌다
    course = await crud_course.lock_course(session, course_id)
    if course is None:
        return EnterResult("not_found")
    row = await crud_code.get_by_code_fresh(session, code)
    if row is None or row.status == "replaced" or row.course_id != course_id:
        return EnterResult("not_found")
    status = _course_status(course, today)
    notice = preparing_notice(course, status)

    learner = await crud_learner.find_learner(session, email)
    if learner is not None:
        existing = await crud_enrollment.find_enrollment(session, course_id, learner.id)
        if existing is not None:
            return EnterResult(
                "reentered",
                learner_id=learner.id,
                course_id=course_id,
                name=existing.name,
                notice=notice,
            )

    blocked = _BLOCKED.get(_code_state(row, status, today))
    if blocked is not None:
        return EnterResult(blocked)
    if await _seats_full(session, row):
        return EnterResult("full")
    if name is None:
        return EnterResult("name_required")

    if learner is None:
        learner = await crud_learner.get_or_create_learner(session, email)
    enrollment = await crud_enrollment.insert_enrollment(
        session, course_id=course_id, learner_id=learner.id, name=name, dept=dept
    )
    return EnterResult(
        "created",
        learner_id=learner.id,
        course_id=course_id,
        name=enrollment.name,
        notice=notice,
    )
