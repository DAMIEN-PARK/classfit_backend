"""admin_account 읽기·쓰기. 아이디 정규화(앞뒤 공백 제거 + 소문자)는 이 파일 한 곳이다. flush 까지만."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.models import AdminAccount


def normalize_login_id(login_id: str) -> str:
    return login_id.strip().lower()


async def get_admin_by_login(
    session: AsyncSession, login_id: str
) -> AdminAccount | None:
    stmt = select(AdminAccount).where(
        AdminAccount.login_id == normalize_login_id(login_id)
    )
    return await session.scalar(stmt)


async def insert_admin(
    session: AsyncSession, *, login_id: str, password_hash: str
) -> AdminAccount:
    """같은 아이디면 Conflict(409)."""
    row = AdminAccount(
        login_id=normalize_login_id(login_id), password_hash=password_hash
    )
    await flush_or_conflict(session, "같은 아이디의 관리자가 이미 있습니다", row)
    return row
