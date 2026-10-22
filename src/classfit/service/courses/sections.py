"""섹션·세션 넣기·고치기·지우기. flush 까지만.

- 다른 강의의 섹션은 404 다(없는 섹션과 같다). 그 강의에 없는 일차를 세션에 주면 409 다(T2a 계획 결정 v).
- 교시(slot)는 일차가 있어야 한다. 일차만 비우면 교시도 같이 비운다.
- 예외 시각(time_start·time_end)은 둘 다 있거나 둘 다 없고, 시작이 앞이다.
- 섹션·세션을 지우기 전에 그 아래 첨부와 파일 행을 같은 트랜잭션에서 지운다(T2b 계획 결정 ix).
  session_attachment.session_id 는 NO ACTION 이라 남기면 23503 이다. 바이트는 gc 몫이다.
- 쓰기 함수 여섯 전부가 맨 앞에서 강의 행을 잠그고(crud.course.lock_course), 판정에 쓰는 섹션·일차·세션은 잠근 뒤
  읽는다(T5 결정 xviii). 그래서 이 파일의 잠금 순서는 전부 course → 섹션·일차·세션 행이고, 배정·풀 배치·일차 바꾸기와
  같은 강의 행 하나로 줄 선다. 세션 id 만 받는 함수는 강의 id 를 얻으려 한 번 읽은 뒤 잠그고 다시 읽는다.
  이 파일에 쓰기 함수를 더하면 같은 규약을 따른다(tests/integration/test_db_assign.py 가 쓰기 함수 목록을 잰다).
- 세션 PATCH 의 instructor_id(T5 결정 vii): 잠금 안에서 PATCH 전체를 검증·적용한 뒤 assign.assign_locked 가 배정·
  기본 강의안·audit·outbox 를 쓴다(그래서 기록의 세션 제목은 이번 PATCH 가 준 새 제목이다). apply_fields 로
  instructor_id 를 직접 쓰지 않는다.
- sections ↔ assign 상호 import — `from classfit.service.courses import <모듈>` 꼴과 속성 호출(assign.assign_locked)을
  유지한다(함수를 직접 import 하면 순환 중 ImportError, T5 리뷰 Nit 3).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import course as crud_course
from classfit.crud import schedule as crud_schedule
from classfit.models import CourseSession, Section
from classfit.schemas.course import SectionIn, SectionPatchIn, SessionIn, SessionPatchIn
from classfit.service.courses import assign

_NO_SECTION = "이 강의의 섹션이 없습니다"
_NO_SESSION = "세션이 없습니다"


async def section_in_course(
    session: AsyncSession, course_id: int, section_id: int
) -> Section:
    """그 강의의 섹션. 없거나 다른 강의의 섹션이면 NotFound."""
    row = await crud_schedule.get_section(session, course_id, section_id)
    if row is None:
        raise NotFound(_NO_SECTION)
    return row


async def _require_day(session: AsyncSession, course_id: int, day_no: int) -> None:
    if await crud_schedule.get_day(session, course_id, day_no) is None:
        raise Conflict(f"이 강의에 {day_no}일차가 없습니다")


async def add_section(
    session: AsyncSession, course_id: int, body: SectionIn
) -> Section:
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound("강의가 없습니다")
    return await crud_schedule.insert_section(session, course_id, **body.model_dump())


async def patch_section(
    session: AsyncSession, course_id: int, section_id: int, body: SectionPatchIn
) -> Section:
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(_NO_SECTION)
    row = await section_in_course(session, course_id, section_id)
    return await crud_schedule.apply_fields(session, row, body.changes())


async def remove_section(
    session: AsyncSession, course_id: int, section_id: int
) -> None:
    """그 섹션의 세션도 같이 지워진다(FK CASCADE). 첨부·파일 행은 먼저 지운다."""
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(_NO_SECTION)
    await section_in_course(session, course_id, section_id)
    await crud_attachment.delete_attachments_under(session, section_id=section_id)
    await crud_schedule.delete_section(session, section_id)


async def add_session(
    session: AsyncSession, course_id: int, section_id: int, body: SessionIn
) -> CourseSession:
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(_NO_SECTION)
    await section_in_course(session, course_id, section_id)
    if body.day_no is not None:
        await _require_day(session, course_id, body.day_no)
    return await crud_schedule.insert_session(session, section_id, **body.model_dump())


async def _session(session: AsyncSession, session_id: int) -> tuple[CourseSession, int]:
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_SESSION)
    return found


async def patch_session(
    session: AsyncSession, session_id: int, body: SessionPatchIn, *, actor: str
) -> CourseSession:
    """칸을 바꾼다. instructor_id 가 오면 다른 칸을 다 적용한 뒤 배정을 기록한다(null 은 해제, 상태를 보지 않는다)."""
    _, course_id = await _session(session, session_id)
    course = await crud_course.lock_course(session, course_id)
    if course is None:
        raise NotFound(_NO_SESSION)
    found = await crud_schedule.get_session_and_course(session, session_id, fresh=True)
    if found is None:
        raise NotFound(_NO_SESSION)
    row, course_id = found
    changes = body.changes()
    assigning = "instructor_id" in changes
    target = changes.pop("instructor_id", None)
    instructor = None
    if target is not None:
        instructor = await assign.lock_assignable(session, target)
    if "day_no" in changes and changes["day_no"] is None and "slot" not in changes:
        changes["slot"] = None
    day_no = changes.get("day_no", row.day_no)
    if changes.get("slot", row.slot) is not None and day_no is None:
        raise Conflict("교시는 일차가 있어야 합니다")
    if changes.get("day_no") is not None:
        await _require_day(session, course_id, changes["day_no"])
    start = changes.get("time_start", row.time_start)
    end = changes.get("time_end", row.time_end)
    if (start is None) != (end is None) or (start is not None and start >= end):
        raise Conflict("예외 시각은 시작·끝을 같이 두고 시작이 앞이어야 합니다")
    row = await crud_schedule.apply_fields(session, row, changes)
    if assigning:
        await assign.assign_locked(
            session, course=course, rows=[row], instructor=instructor, actor=actor
        )
    return row


async def remove_session(session: AsyncSession, session_id: int) -> None:
    _, course_id = await _session(session, session_id)
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(_NO_SESSION)
    if (
        await crud_schedule.get_session_and_course(session, session_id, fresh=True)
        is None
    ):
        raise NotFound(_NO_SESSION)
    await crud_attachment.delete_attachments_under(session, session_id=session_id)
    await crud_schedule.delete_session(session, session_id)
