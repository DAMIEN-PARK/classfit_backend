"""목록 응답 모양 {items, next_cursor, has_more}(Design 5절 2). 커서는 core/cursor.py."""

from __future__ import annotations

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool
