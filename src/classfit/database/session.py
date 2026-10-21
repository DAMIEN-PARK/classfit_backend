"""엔진 · 세션 팩토리.

트랜잭션 주인은 호출자다. API 는 app.deps.db(요청 1개 = 트랜잭션 1개), 관리 명령은
main_async 한 곳. service·crud 는 flush 까지만 한다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from classfit.core.config import DRIVER_PREFIX


def make_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """드라이버는 psycopg 하나. 다른 주소는 기동 때 거부한다(값은 메시지에 넣지 않는다)."""
    if not url.startswith(DRIVER_PREFIX):
        raise RuntimeError(f"DB 주소는 {DRIVER_PREFIX} 로 시작해야 합니다")
    kwargs.setdefault("pool_pre_ping", True)
    return create_async_engine(url, **kwargs)


def make_session_factory(
    bind: AsyncEngine | AsyncConnection, **kwargs: Any
) -> async_sessionmaker[AsyncSession]:
    """expire_on_commit=False: 커밋 뒤 응답 직렬화에서 lazy load 가 터지지 않게."""
    kwargs.setdefault("expire_on_commit", False)
    return async_sessionmaker(bind, **kwargs)
