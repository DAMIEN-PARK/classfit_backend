"""invite_code 읽기·쓰기. flush 까지만.

넣기는 여기 없다. 행은 service.courses.codes 의 issue_invite_code() 가 flush_or_conflict 로 넣는다(Design 5절 13).
"""

from __future__ import annotations

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


async def update_code(
    session: AsyncSession, row: InviteCode, **fields: Any
) -> InviteCode:
    """상태·만료일·정원을 바꾸고 flush. replaced 표시도 이것으로 한다(status="replaced")."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    return row
