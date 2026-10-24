"""mail_outbox 쓰기·읽기. 같은 요청 트랜잭션에 넣고 flush 까지만(보내지 않는다, ADR-003 결정 5).

보냄 표시(scripts.outbox_preview --apply)는 행마다 lock_unsent 로 잡고 다시 읽은 뒤 mark_sent 한다 — 그 사이 inquiry_gc 가
그 행을 지우고 커밋하면 잠그지 않고 읽은 행의 UPDATE 가 0행(StaleDataError)이 된다(T9b codex 구현 리뷰 1차 ①). 순서는 id
오름차순이라 inquiry_gc 의 잠금(문의 → outbox, id 오름차순)과 방향이 같다.
"""

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


async def unsent(
    session: AsyncSession, *, limit: int | None = None
) -> list[MailOutbox]:
    """안 보낸 행, 넣은 순서대로. limit 이 있으면 앞 limit 행만(안 보낸 행 전부를 메모리에 올리지 않게, T9b 결정 xxiv)."""
    stmt = (
        select(MailOutbox).where(MailOutbox.sent_at.is_(None)).order_by(MailOutbox.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list((await session.scalars(stmt)).all())


async def lock_unsent(session: AsyncSession, outbox_id: int) -> MailOutbox | None:
    """그 안 보낸 행을 FOR UPDATE 로 잡고 새로 읽는다. 그 사이 지워졌거나 보냄 표시가 됐으면 None."""
    stmt = (
        select(MailOutbox)
        .where(MailOutbox.id == outbox_id, MailOutbox.sent_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def mark_sent(session: AsyncSession, row: MailOutbox) -> None:
    row.sent_at = datetime.now(UTC)
    await session.flush()
