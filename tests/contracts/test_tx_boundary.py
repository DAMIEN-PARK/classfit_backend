"""요청 1개 = 트랜잭션 1개. 응답 전에 커밋, 예외(도메인·미처리)면 롤백. scope="function" 이나 session.begin() 을 지우면 빨개진다."""

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import AuditLog


async def _rows(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(AuditLog)) or 0


async def test_commit_happens_before_response_and_row_persists(
    client: httpx.AsyncClient, db_session: AsyncSession, nested_at_response_start: list[bool]
) -> None:
    r = await client.post("/v1/_probe/audit")
    assert r.status_code == 200 and r.json()["id"] > 0
    assert nested_at_response_start == [False]  # 응답 시작 시점에 요청 SAVEPOINT 는 이미 해제
    assert await _rows(db_session) == 1


async def test_domain_error_rolls_back_the_request(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    r = await client.post("/v1/_probe/audit", params={"fail": "conflict"})
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "/problems/conflict"
    assert await _rows(db_session) == 0


async def test_unhandled_error_rolls_back_and_returns_problem_500(
    client_noraise: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    r = await client_noraise.post("/v1/_probe/audit", params={"fail": "crash"})
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "일부러" not in r.text  # 내부 메시지를 손님에게 흘리지 않는다
    assert await _rows(db_session) == 0
