"""문의 접수 동시성 행동 시험 하나(T9b 결정 vi): 같은 이메일 + 같은 내용 동시 둘 → 행 1 · 같은 영수증. 라이브 PG, 커밋한다.
이름 접두는 test_inquiry_race_(E-11 의 test_concurrent_ 와 다르다).

틀은 T5 tests/integration/test_db_assign_race.py 를 복사했다(그 파일은 고치지 않는다): 커밋하는 NullPool 엔진
committing(끝에 SEED_TABLES 밖의 ORM 표를 TRUNCATE) · factory · pg_stat_activity 로 "B 가 기다렸다" 를 재는 _waits_on_lock ·
_commit_after · _lock_timeout · _race(A 가 함수를 끝내고 커밋 전에 선다) · _ok · _count. 이 파일에서 바꾼 것:
- _advisory_waiting(engine, pid): B 가 기다리는 것이 advisory 잠금인지(pg_locks 의 advisory 미승인 1행). T5 _blocked_on 은
  tuple 잠금만 보므로 쓰지 않는다. Raced 는 blocked 대신 advisory 칸을 갖는다.
순서는 시간이 아니라 _waits_on_lock 폴링이 정한다(sleep 없음). A·B 둘 다 lock_timeout 10초.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from classfit.database.session import make_engine, make_session_factory
from classfit.models import Base, Inquiry, MailOutbox
from classfit.service.inquiries import receive
from tests.fixtures.inquiry import NOTIFY_TO, fields

WAIT_SECONDS = 5.0
POLL_SECONDS = 0.02
GATHER_SECONDS = 15.0

Factory = async_sessionmaker[AsyncSession]
Work = Callable[[AsyncSession], Awaitable[Any]]
# 마이그레이션이 넣는 시드 표는 비우지 않는다(0005 document_type · 0009 survey_template, T8 판)
SEED_TABLES = frozenset({"document_type", "survey_template"})


@pytest_asyncio.fixture
async def committing(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    """커밋하는 엔진. 끝에 ORM 표를 비운다(sorted_tables, CASCADE). 시드 표 SEED_TABLES 는 남긴다."""
    engine = make_engine(migrated_db_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        try:
            async with engine.begin() as conn:
                quote = conn.dialect.identifier_preparer.format_table
                names = ", ".join(
                    quote(t)
                    for t in Base.metadata.sorted_tables
                    if t.name not in SEED_TABLES
                )
                await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def factory(committing: AsyncEngine) -> Factory:
    return make_session_factory(committing)


async def _waits_on_lock(
    engine: AsyncEngine, pid: int, task: asyncio.Task[Any]
) -> bool:
    """B(pid)가 잠금을 기다리는 것을 보면 True, 못 보고 B 가 끝났거나 5초가 지나면 False.

    pg_stat_activity 는 트랜잭션 안에서 처음 읽은 값을 붙들므로 AUTOCOMMIT 으로 매번 새로 읽는다.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        while loop.time() < deadline and not task.done():
            wait = await conn.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            )
            if wait == "Lock":
                return True
            await asyncio.sleep(POLL_SECONDS)
    return False


async def _advisory_waiting(engine: AsyncEngine, pid: int) -> bool:
    """B(pid)가 승인되지 않은 advisory 잠금 하나를 기다리는가(문의 이메일 잠금 crud.inquiry.lock_email)."""
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        waiting = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_locks"
                " WHERE locktype = 'advisory' AND NOT granted AND pid = :pid"
            ),
            {"pid": pid},
        )
        return waiting == 1


async def _commit_after[T](
    session: AsyncSession, work: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    result = await work(session)
    await session.commit()
    return result


async def _lock_timeout(session: AsyncSession) -> int:
    """lock_timeout 10초를 걸고 백엔드 pid 를 돌려준다(교착·잠금 누수 때 멈추지 않고 빨개지게)."""
    await session.execute(text("SET LOCAL lock_timeout = '10s'"))
    pid = await session.scalar(text("SELECT pg_backend_pid()"))
    assert pid is not None
    return int(pid)


@dataclass
class Raced:
    first: Any  # A 결과(예외면 예외 객체)
    second: Any  # B 결과(예외면 예외 객체)
    waited: bool  # B 가 잠금을 기다렸는지
    advisory: bool  # B 가 기다린 것이 advisory 잠금인지


async def _race(
    factory: Factory, engine: AsyncEngine, hold: Work, contend: Work
) -> Raced:
    """A 는 hold 뒤 커밋 전에 멈추고, B 를 띄워 기다림·대기 관계를 잰 뒤 A 를 커밋한다."""
    async with factory() as a, factory() as b:
        await _lock_timeout(a)
        first = await hold(a)
        pid = await _lock_timeout(b)
        task = asyncio.create_task(_commit_after(b, contend))
        try:
            waited = await _waits_on_lock(engine, pid, task)
            advisory = await _advisory_waiting(engine, pid) if waited else False
            await a.commit()
            (second,) = await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True), GATHER_SECONDS
            )
        finally:
            if not task.done():
                await a.rollback()  # A 의 잠금을 풀어 B 가 끝나게 한다
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    return Raced(first, second, waited, advisory)


def _ok(raced: Raced) -> None:
    """A·B 둘 다 예외 없음(40P01 교착 · 55P03 lock_timeout · 23505 · 500 없음)."""
    for value in (raced.first, raced.second):
        assert not isinstance(value, BaseException), repr(value)


async def _count(factory: Factory, model: type, *where: Any) -> int:
    async with factory() as s:
        return (
            await s.scalar(select(func.count()).select_from(model).where(*where)) or 0
        )


async def _submit(s: AsyncSession) -> receive.Receipt:
    return await receive.receive_inquiry(
        s, fields=fields(), honeypot=False, notify_to=NOTIFY_TO, daily_max=20
    )


async def test_inquiry_race_duplicate_one_row_same_receipt(
    factory: Factory, committing: AsyncEngine
) -> None:
    raced = await _race(factory, committing, _submit, _submit)
    assert raced.waited, "B 가 A 의 이메일 잠금을 기다리지 않았다"
    assert raced.advisory, "B 가 기다린 것이 advisory 잠금이 아니다"
    _ok(raced)
    first, second = raced.first, raced.second
    # B 는 A 의 커밋을 보고 같은 영수증을 받는다 — 행 1 · outbox 2(r3 171)
    assert first.receipt_no == second.receipt_no
    assert first.created and not second.created
    assert await _count(factory, Inquiry) == 1
    assert await _count(factory, MailOutbox) == 2
