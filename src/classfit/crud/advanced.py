"""advanced_course(심화 과정) 읽기·쓰기. flush 까지만. 관리자 전용이라 주체 범위가 없다(끝점이 AdminCaller 다)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.crud.pool import apply_changes
from classfit.models import AdvancedCourse


async def insert_advanced(session: AsyncSession, **fields: Any) -> AdvancedCourse:
    """심화 과정 1행. 같은 id 면 Conflict(409). 넣은 뒤 다시 읽어 서버 기본값을 채운다."""
    row = AdvancedCourse(**fields)
    await flush_or_conflict(session, "같은 id 의 심화 과정이 있습니다", row)
    await session.refresh(row)
    return row


async def get_advanced(session: AsyncSession, advanced_id: str) -> AdvancedCourse | None:
    return await session.get(AdvancedCourse, advanced_id)


def list_stmt(*, active: bool | None = None) -> Select[tuple[AdvancedCourse]]:
    """심화 목록(관리자, 비활성 포함). 순서 (id)."""
    stmt = select(AdvancedCourse)
    if active is not None:
        stmt = stmt.where(AdvancedCourse.active.is_(active))
    return stmt.order_by(AdvancedCourse.id)


async def list_advanced(
    session: AsyncSession, *, active: bool | None = None
) -> list[AdvancedCourse]:
    return list((await session.scalars(list_stmt(active=active))).all())


async def update_advanced(
    session: AsyncSession, row: AdvancedCourse, **fields: Any
) -> list[str]:
    """내용 칸·pub·active 를 바꾼다. 바뀐 칸 이름(정렬)."""
    return await apply_changes(session, row, fields)
