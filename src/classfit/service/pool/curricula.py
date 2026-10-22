"""강사 커리큘럼(기획안 I3 :567, T4 결정 i·vi·xi·xv·xix). flush 까지만.

- 만들기: id cur-<강사 id>-<n>, 차시표 없이 → audit curriculum.create.
- 판정 순서는 404 → 403 → 409 다(결정 i). 차시표 교체·수정은 맨 앞에서 lock_curriculum 으로 행을 잠근다(결정 xix) —
  두 교체가 겹쳐 (일, 교시) 23505 나 합집합이 남지 않게, 격자 축소 검사도 잠근 뒤 읽는다.
- 차시표는 통째 교체다. 격자(일수 × slots_per_day) 밖·중복은 GridViolation(422). 같은 차시표면 아무것도 쓰지 않는다.
- 일수·시각·교시를 줄여 기존 차시가 격자 밖이 되면 GridViolation(먼저 차시표를 줄인다). 시작 ≥ 끝도 GridViolation 이다
  (PATCH 가 한쪽만 바꿔 CHECK 23514 → 500 이 되지 않게).
- 내용 칸이나 차시표가 바뀌면 reviewed=false, pub·active 는 그대로다(결정 vi). 지우기는 active=false 다(결정 xi, 잠금 없음).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, Forbidden, NotFound
from classfit.crud import curriculum as crud_curriculum
from classfit.crud import pool as crud_pool
from classfit.crud.audit import insert_audit
from classfit.crud.scope import owned_by
from classfit.models import Curriculum
from classfit.models.curriculum import CURRICULUM_CONTENT_FIELDS
from classfit.service.pool.common import (
    GridViolation,
    as_instructor,
    clean_fields,
    instructor_actor,
    violation,
)
from classfit.service.rules import pool as rules

TARGET = "curriculum"
GRID_FIELDS = ("days", "start_time", "end_time", "slot_min", "break_min")
_GRID_MSG = {
    "day": "일이 커리큘럼 일수 밖입니다",
    "slot": "교시가 하루 교시 수 밖입니다",
    "duplicate": "같은 일·교시의 차시가 앞에 있습니다",
}


def _check_owner(row: Curriculum | None, instructor_id: int) -> Curriculum:
    if row is None:
        raise NotFound("커리큘럼이 없습니다")
    if not owned_by(as_instructor(instructor_id), row.instructor_id):
        raise Forbidden("본인의 커리큘럼만 다룰 수 있습니다")
    return row


def _writable(row: Curriculum | None, instructor_id: int) -> Curriculum:
    row = _check_owner(row, instructor_id)
    if not row.active:
        raise Conflict("사용 중지된 커리큘럼은 고칠 수 없습니다")
    return row


def _slot_key(slot: Any) -> tuple[int, int, str, str | None]:
    if isinstance(slot, Mapping):
        return slot["day"], slot["slot"], slot["title"], slot.get("description")
    return slot.day, slot.slot, slot.title, slot.description


async def _reset_review(session: AsyncSession, row: Curriculum) -> None:
    if row.reviewed:
        await crud_curriculum.set_flags(session, row, reviewed=False)


async def create_curriculum(
    session: AsyncSession, *, instructor_id: int, fields: Mapping[str, Any]
) -> Curriculum:
    """fields 는 내용 칸(CURRICULUM_CONTENT_FIELDS 안). 새 행을 다시 읽어 돌려준다."""
    content = clean_fields(fields, CURRICULUM_CONTENT_FIELDS)
    new_id = await crud_pool.next_id(session, "cur", instructor_id, make=rules.pool_id)
    row = await crud_curriculum.insert_curriculum(
        session,
        id=new_id,
        instructor_id=instructor_id,
        reviewed=False,
        pub=False,
        active=True,
        **content,
    )
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="curriculum.create",
        target_type=TARGET,
        target_id=row.id,
    )
    return row


async def get_own_curriculum(
    session: AsyncSession, *, instructor_id: int, curriculum_id: str
) -> Curriculum:
    """본인 커리큘럼(비활성 포함). 없으면 NotFound, 남의 것이면 Forbidden."""
    row = await crud_curriculum.get_curriculum_any(session, curriculum_id)
    return _check_owner(row, instructor_id)


async def patch_curriculum(
    session: AsyncSession,
    *,
    instructor_id: int,
    curriculum_id: str,
    changes: Mapping[str, Any],
) -> list[str]:
    """내용 칸을 바꾼다. 바뀐 칸 이름(정렬)."""
    row = _writable(
        await crud_curriculum.lock_curriculum(session, curriculum_id), instructor_id
    )
    content = clean_fields(changes, CURRICULUM_CONTENT_FIELDS)
    grid = {name: content.get(name, getattr(row, name)) for name in GRID_FIELDS}
    touched = [name for name in GRID_FIELDS if name in content]
    if grid["start_time"] >= grid["end_time"]:
        clock = [n for n in ("start_time", "end_time") if n in content]
        raise GridViolation(
            "시작 시각이 끝 시각보다 앞이어야 합니다",
            [violation(("body", n), "시작 < 끝이어야 합니다", "time_order") for n in clock],
        )
    if touched:
        per_day = rules.slots_per_day(
            grid["start_time"], grid["end_time"], grid["slot_min"], grid["break_min"]
        )
        slots = [
            {"day": s.day, "slot": s.slot}
            for s in await crud_curriculum.list_slots(session, row.id)
        ]
        if rules.slot_grid_errors(grid["days"], per_day, slots):
            raise GridViolation(
                "기존 차시가 격자 밖이 됩니다. 먼저 차시표를 줄이세요",
                [
                    violation(("body", n), "기존 차시가 격자 밖이 됩니다", "slots_out_of_grid")
                    for n in touched
                ],
            )
    changed = await crud_curriculum.update_curriculum(session, row, **content)
    if not changed:
        return []
    await _reset_review(session, row)
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="curriculum.update",
        target_type=TARGET,
        target_id=row.id,
        detail={"changed": changed},
    )
    return changed


async def replace_slots(
    session: AsyncSession,
    *,
    instructor_id: int,
    curriculum_id: str,
    slots: Sequence[Mapping[str, Any]],
) -> int:
    """차시표를 통째 바꾼다. 차시 수. slots 항목은 {day, slot, title, description?}."""
    row = _writable(
        await crud_curriculum.lock_curriculum(session, curriculum_id), instructor_id
    )
    per_day = rules.slots_per_day(
        row.start_time, row.end_time, row.slot_min, row.break_min
    )
    if errors := rules.slot_grid_errors(row.days, per_day, slots):
        raise GridViolation(
            "차시표가 격자 밖이거나 겹칩니다",
            [
                violation(
                    ("body", "slots", i) if why == "duplicate" else ("body", "slots", i, why),
                    _GRID_MSG[why],
                    "duplicate" if why == "duplicate" else "out_of_grid",
                )
                for i, why in errors
            ],
        )
    before = sorted(_slot_key(s) for s in await crud_curriculum.list_slots(session, row.id))
    if before == sorted(_slot_key(s) for s in slots):
        return len(slots)
    count = await crud_curriculum.replace_slots(session, row.id, slots)
    await _reset_review(session, row)
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="curriculum.slots",
        target_type=TARGET,
        target_id=row.id,
        detail={"count": count},
    )
    return count


async def deactivate_curriculum(
    session: AsyncSession, *, instructor_id: int, curriculum_id: str
) -> bool:
    """active=false(잠금 없이 한 행). 이번에 껐으면 True, 이미 꺼져 있었으면 False(audit 없음)."""
    row = await get_own_curriculum(
        session, instructor_id=instructor_id, curriculum_id=curriculum_id
    )
    if not row.active:
        return False
    await crud_curriculum.set_flags(session, row, active=False)
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="curriculum.deactivate",
        target_type=TARGET,
        target_id=row.id,
    )
    return True
