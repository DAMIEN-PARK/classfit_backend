"""mail_outbox 쓰기·읽기. 같은 요청 트랜잭션에 넣고 flush 까지만(보내지 않는다, ADR-003 결정 5)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import MailOutbox


async def enqueue(
    session: AsyncSession, *, kind: str, params: dict[str, Any], to: str
) -> MailOutbox:
    row = MailOutbox(kind=kind, params=params, to=to)
    session.add(row)
    await session.flush()
    return row


async def unsent(session: AsyncSession) -> list[MailOutbox]:
    """안 보낸 행, 넣은 순서대로."""
    stmt = (
        select(MailOutbox).where(MailOutbox.sent_at.is_(None)).order_by(MailOutbox.id)
    )
    return list((await session.scalars(stmt)).all())


async def mark_sent(session: AsyncSession, row: MailOutbox) -> None:
    row.sent_at = datetime.now(UTC)
    await session.flush()
