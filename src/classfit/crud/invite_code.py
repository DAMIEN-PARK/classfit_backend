"""invite_code 읽기·쓰기. flush 까지만.

넣기는 여기 없다. 행은 service.courses.codes 의 issue_invite_code() 가 flush_or_conflict 로 넣는다(Design 5절 13).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import InviteCode


async def get_live_code(session: AsyncSession, course_id: int) -> InviteCode | None:
    """그 강의의 산 코드(replaced 가 아닌 행). 부분 유일 색인이 하나만 허락한다."""
    stmt = select(InviteCode).where(
        InviteCode.course_id == course_id, InviteCode.status != "replaced"
    )
    return await session.scalar(stmt)


async def live_codes(
    session: AsyncSession, course_ids: Collection[int]
) -> dict[int, InviteCode]:
    """강의마다 산 코드(replaced 가 아닌 행). 산 코드가 없는 강의는 키가 없다.

    범위로 걸러진 강의 id 만 받는다 — 홈이 course_scope 목록에서 뽑아 넘긴다.
    """
    ids = list(course_ids)
    if not ids:
        return {}
    stmt = select(InviteCode).where(
        InviteCode.course_id.in_(ids), InviteCode.status != "replaced"
    )
    return {row.course_id: row for row in (await session.scalars(stmt)).all()}


async def find_course_id_by_code(session: AsyncSession, code: str) -> int | None:
    """그 코드의 강의 id 만(replaced 행 포함). ORM 행을 세션에 올리지 않는다.

    입장은 잠금 전에 이것만 읽고, 강의 행을 잠근 뒤 get_by_code_fresh 로 다시 읽는다(T2b 결정 ii).
    """
    return await session.scalar(
        select(InviteCode.course_id).where(InviteCode.code == code)
    )


async def get_by_code_fresh(session: AsyncSession, code: str) -> InviteCode | None:
    """그 코드의 행(replaced 포함)을 DB 값으로 덮어 읽는다. 잠금을 기다린 사이의 재발급·정지를 놓치지 않게."""
    stmt = (
        select(InviteCode)
        .where(InviteCode.code == code)
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def update_code(
    session: AsyncSession, row: InviteCode, **fields: Any
) -> InviteCode:
    """상태·만료일·정원을 바꾸고 flush. replaced 표시도 이것으로 한다(status="replaced")."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    return row
