"""섹션·세션 넣기·고치기·지우기. flush 까지만.

- 다른 강의의 섹션은 404 다(없는 섹션과 같다). 그 강의에 없는 일차를 세션에 주면 409 다(T2a 계획 결정 v).
- 교시(slot)는 일차가 있어야 한다. 일차만 비우면 교시도 같이 비운다.
- 예외 시각(time_start·time_end)은 둘 다 있거나 둘 다 없고, 시작이 앞이다.
- 섹션·세션을 지우기 전에 그 아래 첨부와 파일 행을 같은 트랜잭션에서 지운다(T2b 계획 결정 ix).
  session_attachment.session_id 는 NO ACTION 이라 남기면 23503 이다. 바이트는 gc 몫이다.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import schedule as crud_schedule
from classfit.models import CourseSession, Section
from classfit.schemas.course import SectionIn, SectionPatchIn, SessionIn, SessionPatchIn


async def _section(session: AsyncSession, course_id: int, section_id: int) -> Section:
    row = await crud_schedule.get_section(session, course_id, section_id)
    if row is None:
        raise NotFound("이 강의의 섹션이 없습니다")
    return row


async def _require_day(session: AsyncSession, course_id: int, day_no: int) -> None:
    if await crud_schedule.get_day(session, course_id, day_no) is None:
        raise Conflict(f"이 강의에 {day_no}일차가 없습니다")


async def add_section(
    session: AsyncSession, course_id: int, body: SectionIn
) -> Section:
    return await crud_schedule.insert_section(session, course_id, **body.model_dump())


async def patch_section(
    session: AsyncSession, course_id: int, section_id: int, body: SectionPatchIn
) -> Section:
    row = await _section(session, course_id, section_id)
    return await crud_schedule.apply_fields(session, row, body.changes())


async def remove_section(
    session: AsyncSession, course_id: int, section_id: int
) -> None:
    """그 섹션의 세션도 같이 지워진다(FK CASCADE). 첨부·파일 행은 먼저 지운다."""
    await _section(session, course_id, section_id)
    await crud_attachment.delete_attachments_under(session, section_id=section_id)
    await crud_schedule.delete_section(session, section_id)


async def add_session(
    session: AsyncSession, course_id: int, section_id: int, body: SessionIn
) -> CourseSession:
    await _section(session, course_id, section_id)
    if body.day_no is not None:
        await _require_day(session, course_id, body.day_no)
    return await crud_schedule.insert_session(session, section_id, **body.model_dump())


async def _session(session: AsyncSession, session_id: int) -> tuple[CourseSession, int]:
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound("세션이 없습니다")
    return found


async def patch_session(
    session: AsyncSession, session_id: int, body: SessionPatchIn
) -> CourseSession:
    row, course_id = await _session(session, session_id)
    changes = body.changes()
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
    return await crud_schedule.apply_fields(session, row, changes)


async def remove_session(session: AsyncSession, session_id: int) -> None:
    await _session(session, session_id)
    await crud_attachment.delete_attachments_under(session, session_id=session_id)
    await crud_schedule.delete_session(session, session_id)
