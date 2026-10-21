"""유일 위반만 409 로 바꾸는 flush(Design 5절 5). sqlstate 비교는 이 한 곳에만 둔다.

rows 는 SAVEPOINT 안에서 add 한다. begin_nested() 는 SAVEPOINT 를 열기 전에 그때까지 쌓인 변경을
먼저 flush 하므로(SQLAlchemy 규칙), 위반이 날 수 있는 행은 여기로 넘겨야 실패가 SAVEPOINT 안에 갇히고
바깥 요청 트랜잭션이 산다. 실패한 SAVEPOINT 를 되돌리면 세션의 객체는 만료되니, 409 뒤에 계속 쓰려면 다시 읽는다.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict

UNIQUE_VIOLATION = "23505"


async def flush_or_conflict(session: AsyncSession, message: str, *rows: object) -> None:
    """rows 를 넣고 flush 한다. 유일 위반(23505)만 Conflict, CHECK(23514)·FK(23503) 등은 다시 던진다(→ 500)."""
    try:
        async with session.begin_nested():
            session.add_all(rows)
            await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:
            raise Conflict(message) from exc
        raise
