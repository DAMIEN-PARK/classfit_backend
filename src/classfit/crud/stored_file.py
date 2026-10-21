"""stored_file 읽기·쓰기. key 는 여기서 만든다(불투명, 같은 sha256 이라도 행마다 다르다). flush 까지만."""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import StoredFile


async def insert_stored_file(
    session: AsyncSession,
    *,
    sha256: str,
    owner_kind: str,
    owner_id: int,
    content_type: str,
    size: int,
) -> StoredFile:
    row = StoredFile(
        key=secrets.token_urlsafe(16),
        sha256=sha256,
        owner_kind=owner_kind,
        owner_id=owner_id,
        content_type=content_type,
        size=size,
    )
    session.add(row)
    await session.flush()
    return row


async def get_by_key(session: AsyncSession, key: str) -> StoredFile | None:
    return await session.scalar(select(StoredFile).where(StoredFile.key == key))


async def referenced_sha256(session: AsyncSession) -> set[str]:
    """행이 하나라도 가리키는 sha256 집합(gc 가 지우지 않을 바이트)."""
    return set((await session.scalars(select(StoredFile.sha256).distinct())).all())
