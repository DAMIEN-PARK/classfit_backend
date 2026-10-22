"""초대코드의 단일 진입점(Design 5절 13·16). 행은 issue_invite_code() 에서만 만든다.

- 코드는 rules.invite 의 알파벳으로 secrets.choice 6자다. _new_invite_code 는 이 파일 밖에서 부르지 않는다.
  (T1 의 인증 코드 도우미 _new_code 와 이름을 달리한다. T1 단일 진입 시험이 그 이름을 센다)
- 넣기는 flush_or_conflict 로 한다. 코드 글자가 겹친 유일 위반(23505)이면 새 행·새 코드로 MAX_TRIES 번까지,
  그래도 안 되면 409. 강의에 산 코드가 이미 있어 부분 유일 색인 uq_invite_code_course_live 에 걸리면
  새 코드로도 풀리지 않으므로 다시 넣지 않고 바로 409 다.
- 재발급은 산 행을 replaced 로 바꿔 flush 한 뒤 새 행을 넣는다. 만료일·정원은 옛 행에서 옮긴다(T2a 계획 결정 ii).
- 재개는 강의가 ended 면 409 다. 정지·재발급은 종료 강의에서도 된다(상태는 계산상 stopped, 결정 iii).
- 정지·재개·수정은 (행, 바뀌었는지)를 돌려준다. 이미 그 상태거나 같은 값이면 쓰지 않고, 끝점은 그때 audit 을 쓰지 않는다.
- 코드 행을 바꾸는 네 문(재발급·정지·재개·수정)은 맨 앞에서 그 강의 행을 잠근다(T2b 계획 결정 v). 입장·강의 삭제와
  같은 행이라 줄을 선다. 바뀌는 코드 행이 아니라 고정된 강의 행을 잠가, 둘째 재발급이 산 코드 행을 잃지 않는다.
"""

from __future__ import annotations

import secrets
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import course as crud_course
from classfit.crud import invite_code as crud_code
from classfit.crud.flush import flush_or_conflict
from classfit.models import Course, InviteCode
from classfit.service.rules.invite import INVITE_ALPHABET, INVITE_LENGTH
from classfit.service.rules.status import (
    CodeState,
    CourseStatus,
    code_state_at,
    course_status_at,
)

MAX_TRIES = 5
LIVE_INDEX = "uq_invite_code_course_live"  # 강의당 산 코드 1개(0003)


def course_status_of(course: Course, today: date) -> CourseStatus:
    """행의 오늘 상태(rules.status.course_status_at). status 칸은 CHECK 가 세 값으로 막는다."""
    stored: CourseStatus = course.status  # type: ignore[assignment]
    return course_status_at(
        start_on=course.start_on,
        end_on=course.end_on,
        status=stored,
        status_manual=course.status_manual,
        today=today,
    )


def code_state_of(code: InviteCode, course: Course, today: date) -> CodeState:
    """코드 행의 오늘 상태(rules.status.code_state_at). 강의 상태는 계산값을 넘긴다."""
    stored = code.status
    return code_state_at(
        code_status=stored,  # type: ignore[arg-type]
        expires_on=code.expires_on,
        course_status=course_status_of(course, today),
        today=today,
    )


def _violated_constraint(exc: Conflict) -> str | None:
    """flush_or_conflict 는 IntegrityError 를 원인(__cause__)으로 달아 Conflict 로 바꾼다. 그 제약 이름."""
    diag = getattr(getattr(exc.__cause__, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def _new_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


async def issue_invite_code(
    session: AsyncSession,
    *,
    course_id: int,
    expires_on: date,
    max_seats: int | None = None,
) -> InviteCode:
    """산(active) 코드 1행을 넣고 flush 한다. 다 겹치면 Conflict(409)."""
    for _ in range(MAX_TRIES):
        row = InviteCode(
            course_id=course_id,
            code=_new_invite_code(),
            status="active",
            expires_on=expires_on,
            max_seats=max_seats,
        )
        try:
            await flush_or_conflict(session, "초대코드가 겹쳤습니다", row)
        except Conflict as exc:
            if _violated_constraint(exc) == LIVE_INDEX:
                raise Conflict("이 강의에 산 초대코드가 이미 있습니다") from exc
            continue
        return row
    raise Conflict(
        f"초대코드를 {MAX_TRIES}번 만들었지만 모두 겹쳤습니다. 다시 시도하세요"
    )


async def live_code(session: AsyncSession, course_id: int) -> InviteCode:
    row = await crud_code.get_live_code(session, course_id)
    if row is None:
        raise NotFound("이 강의의 초대코드가 없습니다")
    return row


async def _lock(session: AsyncSession, course_id: int) -> Course:
    """강의 행을 FOR UPDATE 로 잠그고 새로 읽는다(결정 v). 그 사이 지워졌으면 404."""
    course = await crud_course.lock_course(session, course_id)
    if course is None:
        raise NotFound("강의가 없습니다")
    return course


async def reissue_invite_code(session: AsyncSession, course_id: int) -> InviteCode:
    """옛 산 행을 replaced 로 → flush → 새 행. 옛 코드는 바로 무효다(기획안 5-4)."""
    await _lock(session, course_id)
    old = await live_code(session, course_id)
    expires_on, max_seats = old.expires_on, old.max_seats
    await crud_code.update_code(session, old, status="replaced")
    return await issue_invite_code(
        session, course_id=course_id, expires_on=expires_on, max_seats=max_seats
    )


async def pause_invite_code(
    session: AsyncSession, course_id: int
) -> tuple[InviteCode, bool]:
    """(행, 바뀌었는지). 이미 paused 면 쓰지 않는다."""
    await _lock(session, course_id)
    row = await live_code(session, course_id)
    if row.status == "paused":
        return row, False
    await crud_code.update_code(session, row, status="paused")
    return row, True


async def resume_invite_code(
    session: AsyncSession, course_id: int, *, today: date
) -> tuple[InviteCode, bool]:
    """(행, 바뀌었는지). 산 코드가 없으면 404 가 먼저, 종료(계산값 ended) 강의면 409. 이미 active 면 쓰지 않는다.

    종료 판정은 잠그며 새로 읽은 강의 행(populate_existing)으로 한다.
    """
    course = await _lock(session, course_id)
    row = await live_code(session, course_id)
    if course_status_of(course, today) == "ended":
        raise Conflict("종료된 강의의 초대코드는 다시 열 수 없습니다")
    if row.status == "active":
        return row, False
    await crud_code.update_code(session, row, status="active")
    return row, True


async def update_invite_code(
    session: AsyncSession, course_id: int, changes: dict[str, Any]
) -> tuple[InviteCode, list[str]]:
    """만료일·정원을 바꾼다. (행, 실제로 바뀐 칸 이름). 준 칸 중 현재 값과 다른 칸만 쓴다."""
    await _lock(session, course_id)
    row = await live_code(session, course_id)
    changed = {k: v for k, v in changes.items() if getattr(row, k) != v}
    if changed:
        await crud_code.update_code(session, row, **changed)
    return row, sorted(changed)
