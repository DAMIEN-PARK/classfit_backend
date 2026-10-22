"""curriculum · curriculum_slot 읽기·쓰기. flush 까지만.

- 행 넣기 insert_curriculum 은 service.pool.curricula 만 부른다.
- 목록·관리자 단건의 첫 WHERE 는 주체 범위다(crud.scope.curriculum_scope). service 판정용 읽기는 범위 없는
  get_curriculum_any, 차시표 교체·수정은 lock_curriculum 이다(SELECT … FOR UPDATE, T4 결정 xix).
- 차시표는 통째 교체다: 전부 지우고 새로 넣는다. (커리큘럼, 일, 교시) 유일 위반은 Conflict(409)다 —
  입력 검사(service.rules.pool.slot_grid_errors)가 먼저 422 로 막는다(결정 xv).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.crud.pool import apply_changes
from classfit.crud.scope import Subject, curriculum_scope
from classfit.models import Curriculum, CurriculumSlot
from classfit.models.pool import POOL_FLAGS


async def insert_curriculum(session: AsyncSession, **fields: Any) -> Curriculum:
    """커리큘럼 1행(차시 없이). 같은 id 면 Conflict(409). 넣은 뒤 다시 읽어 서버 기본값을 채운다."""
    row = Curriculum(**fields)
    await flush_or_conflict(session, "같은 id 의 커리큘럼이 있습니다", row)
    await session.refresh(row)
    return row


async def get_curriculum(
    session: AsyncSession, subject: Subject, curriculum_id: str
) -> Curriculum | None:
    """범위 안의 커리큘럼 하나. 범위 밖이면 None."""
    stmt = (
        select(Curriculum)
        .where(curriculum_scope(subject))
        .where(Curriculum.id == curriculum_id)
    )
    return await session.scalar(stmt)


async def get_curriculum_any(
    session: AsyncSession, curriculum_id: str
) -> Curriculum | None:
    """범위 없는 읽기(service 판정용)."""
    return await session.get(Curriculum, curriculum_id)


async def lock_curriculum(
    session: AsyncSession, curriculum_id: str
) -> Curriculum | None:
    """커리큘럼 행을 SELECT … FOR UPDATE 로 잠그고 새로 읽는다. 없으면 None(T3 lock_instructor 꼴).

    두 차시표 교체가 겹치면 같은 (일, 교시) 23505 나 두 표의 합집합이 남는다. 교체·수정이 이 행 하나로 줄 선다.
    populate_existing: 잠금을 기다린 사이 커밋된 값을 identity map 의 옛 값이 가리지 않게 덮어 읽는다.
    """
    stmt = (
        select(Curriculum)
        .where(Curriculum.id == curriculum_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


def list_stmt(
    subject: Subject, *, reviewed: bool | None = None, active: bool | None = None
) -> Select[tuple[Curriculum]]:
    """커리큘럼 목록(비활성 포함, 필터는 관리자용). 첫 WHERE 는 주체 범위다. 순서 (id)."""
    stmt = select(Curriculum).where(curriculum_scope(subject))
    if reviewed is not None:
        stmt = stmt.where(Curriculum.reviewed.is_(reviewed))
    if active is not None:
        stmt = stmt.where(Curriculum.active.is_(active))
    return stmt.order_by(Curriculum.id)


async def update_curriculum(
    session: AsyncSession, row: Curriculum, **fields: Any
) -> list[str]:
    """내용 칸·플래그를 바꾼다. 바뀐 칸 이름(정렬)."""
    return await apply_changes(session, row, fields)


async def set_flags(session: AsyncSession, row: Curriculum, **flags: Any) -> list[str]:
    """플래그 reviewed·pub·active 와 reviewed_at 만. 바뀐 칸 이름(정렬)."""
    allowed = {*POOL_FLAGS, "reviewed_at"}
    if unknown := set(flags) - allowed:
        raise ValueError(f"플래그가 아니다: {sorted(unknown)}")
    return await apply_changes(session, row, flags)


async def list_slots(session: AsyncSession, curriculum_id: str) -> list[CurriculumSlot]:
    """그 커리큘럼의 차시. 순서 (일, 교시)."""
    stmt = (
        select(CurriculumSlot)
        .where(CurriculumSlot.curriculum_id == curriculum_id)
        .order_by(CurriculumSlot.day, CurriculumSlot.slot)
    )
    return list((await session.scalars(stmt)).all())


async def slots_by_curriculum(
    session: AsyncSession, curriculum_ids: Iterable[str]
) -> dict[str, list[CurriculumSlot]]:
    """커리큘럼마다 차시(목록 응답용). 차시가 없으면 키가 없다. 각 목록의 순서 (일, 교시)."""
    ids = list(curriculum_ids)
    if not ids:
        return {}
    stmt = (
        select(CurriculumSlot)
        .where(CurriculumSlot.curriculum_id.in_(ids))
        .order_by(CurriculumSlot.curriculum_id, CurriculumSlot.day, CurriculumSlot.slot)
    )
    out: dict[str, list[CurriculumSlot]] = {}
    for slot in (await session.scalars(stmt)).all():
        out.setdefault(slot.curriculum_id, []).append(slot)
    return out


async def replace_slots(
    session: AsyncSession, curriculum_id: str, slots: Sequence[Mapping[str, Any]]
) -> int:
    """차시표를 slots 로 통째 바꾼다(전부 삭제 → 삽입). 넣은 차시 수.

    slots 의 항목은 {day, slot, title, description?}. (일, 교시) 중복은 Conflict(409).
    """
    await session.execute(
        delete(CurriculumSlot).where(CurriculumSlot.curriculum_id == curriculum_id)
    )
    rows = [
        CurriculumSlot(
            curriculum_id=curriculum_id,
            day=s["day"],
            slot=s["slot"],
            title=s["title"],
            description=s.get("description"),
        )
        for s in slots
    ]
    if rows:
        await flush_or_conflict(session, "같은 일·교시의 차시가 둘입니다", *rows)
    return len(rows)

