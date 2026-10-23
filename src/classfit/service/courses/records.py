"""교육 기록 저장·확인(T7 결정 iii·v·xii·xiii). flush 까지만.

- 상태 판정은 service.rules.record 한 곳이다(after_save · after_confirm · changed_fields). none 은 행 없음이다.
  바뀐 칸은 본문 여섯 칸을 지금 행과 견준다. 강사 저장에 바뀐 칸이 없으면 쓰지 않는다(R4 — 확인도 그대로).
  관리자 저장은 ok 로 쓰되 이미 ok 이고 바뀐 칸이 없으면 쓰지 않는다(R5). 확인은 done 만 쓰고 ok 는 그대로(R7),
  기록이 없으면 409(R8).
- 판정은 범위 없는 getter(crud.record.session_context)로 없으면 404 → 강사는 그 세션의 지금 담당이 아니면 403(결정 v).
  강사 상태·강의 상태·일정 날짜는 보지 않는다(예정 차시·일차 미정 세션도 저장한다). 관리자는 모든 세션이다.
- 쓰기 셋은 첫 DB 쓰기 전에 강의 행을 잠그고(crud.course.lock_course), 잠근 뒤 세션(fresh=True)과 기록(fresh=True)을
  다시 읽어 404·403 과 넣기·고치기를 고른다(결정 xiii — 잠금을 기다린 사이 커밋된 재배정·저장을 본다). 그래서 같은
  세션의 두 저장이 겹쳐도 세션당 1행 유일에 걸리지 않는다.
- audit 은 바뀐 것이 있을 때만 1행: session_record.save(detail {from, to, fields} — 상태만 바뀌면 fields []) ·
  session_record.confirm(detail {from: "done", to: "ok"}). 진행 내용·비고는 싣지 않는다(결정 xii).
- crud 는 모듈 별칭(crud_*)의 속성으로 부른다 — 행동 시험의 감싸개·정적 시험이 그 꼴을 본다(T5 결정 xviii).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, Forbidden, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import instructor as crud_instructor
from classfit.crud import record as crud_record
from classfit.models import SessionRecord
from classfit.service.rules.record import (
    RecordFields,
    RecordRejected,
    after_confirm,
    after_save,
    changed_fields,
)

NO_SESSION = "세션이 없습니다"
NOT_MINE = "본인 세션의 기록만 쓸 수 있습니다"
NO_RECORD = "확인할 기록이 없습니다"


@dataclass(frozen=True)
class RecordView:
    """기록 한 행과 기록자 이름(강사면 instructor.name, 관리자는 이름 칸이 없어 None). 속성 이름이 응답 칸이다."""

    row: SessionRecord
    recorder_name: str | None

    @property
    def session_id(self) -> int:
        return self.row.session_id

    @property
    def status(self) -> str:
        return self.row.status

    @property
    def held_on(self) -> dt.date:
        return self.row.held_on

    @property
    def start_time(self) -> dt.time | None:
        return self.row.start_time

    @property
    def end_time(self) -> dt.time | None:
        return self.row.end_time

    @property
    def attendees(self) -> int | None:
        return self.row.attendees

    @property
    def content(self) -> str:
        return self.row.content

    @property
    def note(self) -> str | None:
        return self.row.note

    @property
    def recorded_by(self) -> str:
        return self.row.recorded_by_kind

    @property
    def recorded_by_name(self) -> str | None:
        return self.recorder_name

    @property
    def recorded_at(self) -> dt.datetime:
        return self.row.recorded_at

    @property
    def confirmed_at(self) -> dt.datetime | None:
        return self.row.confirmed_at


def fields_of(row: SessionRecord | None) -> RecordFields | None:
    """행의 본문 여섯 칸(없으면 None)."""
    if row is None:
        return None
    return RecordFields(
        held_on=row.held_on,
        start_time=row.start_time,
        end_time=row.end_time,
        attendees=row.attendees,
        content=row.content,
        note=row.note,
    )


def _status(row: SessionRecord | None) -> str:
    return "none" if row is None else row.status


def _require(
    context: crud_record.SessionContext | None, instructor_id: int | None
) -> crud_record.SessionContext:
    """없으면 NotFound, instructor_id 가 있고 그 세션의 지금 담당이 아니면 Forbidden."""
    if context is None:
        raise NotFound(NO_SESSION)
    if instructor_id is not None and context.row.instructor_id != instructor_id:
        raise Forbidden(NOT_MINE)
    return context


async def view_of(session: AsyncSession, row: SessionRecord) -> RecordView:
    """기록자 이름을 붙인다(강사 기록자만 이름이 있다)."""
    name = None
    if row.recorded_by_kind == "instructor":
        names = await crud_instructor.names_by_id(session, [row.recorded_by_id])
        name = names.get(row.recorded_by_id)
    return RecordView(row, name)


async def save_my_record(
    session: AsyncSession,
    *,
    instructor_id: int,
    session_id: int,
    fields: RecordFields,
    actor: str,
) -> RecordView:
    """담당 강사 저장(R1~R4). 없는 세션 404 · 남의 세션·미배정 403."""
    context = _require(
        await crud_record.session_context(session, session_id), instructor_id
    )
    if await crud_course.lock_course(session, context.course_id) is None:
        raise NotFound(NO_SESSION)
    _require(
        await crud_record.session_context(session, session_id, fresh=True),
        instructor_id,
    )
    row = await crud_record.get_record(session, session_id, fresh=True)
    before = _status(row)
    changed = changed_fields(fields_of(row), fields)
    after = after_save(before, "instructor", bool(changed))
    if row is not None and not changed and after == before:
        return await view_of(session, row)  # R4
    if row is None:
        row = await crud_record.insert_record(
            session,
            session_id=session_id,
            status=after,
            values=asdict(fields),
            by_kind="instructor",
            by_id=instructor_id,
            confirmed_by_id=None,
        )
    else:
        row = await crud_record.apply_record(
            session,
            row,
            status=after,
            values=asdict(fields),
            by_kind="instructor",
            by_id=instructor_id,
            confirmed_by_id=None,
        )
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="session_record.save",
        target_type="session",
        target_id=str(session_id),
        detail={"from": before, "to": after, "fields": changed},
    )
    return await view_of(session, row)


async def save_admin_record(
    session: AsyncSession,
    *,
    admin_id: int,
    session_id: int,
    fields: RecordFields,
    actor: str,
) -> RecordView:
    """관리자 저장(R5): 늘 ok · 기록자·확인자 관리자. 미배정 세션도 쓴다. 없는 세션 404."""
    context = _require(await crud_record.session_context(session, session_id), None)
    if await crud_course.lock_course(session, context.course_id) is None:
        raise NotFound(NO_SESSION)
    _require(await crud_record.session_context(session, session_id, fresh=True), None)
    row = await crud_record.get_record(session, session_id, fresh=True)
    before = _status(row)
    changed = changed_fields(fields_of(row), fields)
    after = after_save(before, "admin", bool(changed))
    if row is not None and not changed and after == before:
        return await view_of(session, row)  # 이미 ok 이고 같은 칸
    if row is None:
        row = await crud_record.insert_record(
            session,
            session_id=session_id,
            status=after,
            values=asdict(fields),
            by_kind="admin",
            by_id=admin_id,
            confirmed_by_id=admin_id,
        )
    else:
        row = await crud_record.apply_record(
            session,
            row,
            status=after,
            values=asdict(fields),
            by_kind="admin",
            by_id=admin_id,
            confirmed_by_id=admin_id,
        )
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="session_record.save",
        target_type="session",
        target_id=str(session_id),
        detail={"from": before, "to": after, "fields": changed},
    )
    return await view_of(session, row)


async def confirm_record(
    session: AsyncSession, *, admin_id: int, session_id: int, actor: str
) -> RecordView:
    """관리자 확인(R6~R8): done → ok · ok 는 그대로(audit 없음) · 기록 없음 409 · 없는 세션 404."""
    context = _require(await crud_record.session_context(session, session_id), None)
    if await crud_course.lock_course(session, context.course_id) is None:
        raise NotFound(NO_SESSION)
    _require(await crud_record.session_context(session, session_id, fresh=True), None)
    row = await crud_record.get_record(session, session_id, fresh=True)
    before = _status(row)
    try:
        after_confirm(before)
    except RecordRejected as exc:
        raise Conflict(NO_RECORD) from exc
    assert row is not None  # after_confirm 이 none 을 막았다
    if before == "done":
        row = await crud_record.confirm_row(session, row, admin_id=admin_id)
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="session_record.confirm",
            target_type="session",
            target_id=str(session_id),
            detail={"from": "done", "to": "ok"},
        )
    return await view_of(session, row)
