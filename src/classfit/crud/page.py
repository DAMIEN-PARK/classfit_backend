"""키셋 페이지: (created_at, id) 내림차순, limit+1 행으로 has_more 를 안다(Design 5절 2).

stmt 는 `select(Model)` 이고 주체 범위 WHERE(crud/scope.py)를 이미 단 것이다. 커서 조건은 그 뒤에 더한다.
모델은 created_at · id 칸이 있어야 한다. 깨진 커서는 decode_cursor 의 ValueError 그대로다(끝점이 422 로).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.cursor import decode_cursor, encode_cursor


async def keyset_page[M](
    session: AsyncSession, stmt: Select[tuple[M]], cursor: str | None, limit: int
) -> tuple[list[M], str | None, bool]:
    """(items, next_cursor, has_more). 마지막 쪽이면 next_cursor 는 None."""
    if limit < 1:
        raise ValueError("limit 은 1 이상")
    entity: Any = stmt.column_descriptions[0]["entity"]
    created_at, id_ = entity.created_at, entity.id
    if cursor is not None:
        t, i = decode_cursor(cursor)
        # 오른쪽을 맨 튜플로 둬야 바인드가 칸 타입(BIGINT)을 따른다. tuple_(t, i) 는 INTEGER 로 캐스트한다
        stmt = stmt.where(tuple_(created_at, id_) < (t, i))
    stmt = stmt.order_by(created_at.desc(), id_.desc()).limit(limit + 1)
    rows = list((await session.scalars(stmt)).all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id) if has_more else None
    )
    return items, next_cursor, has_more
