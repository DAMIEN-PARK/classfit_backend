"""동시성(Design 5절 6·18, r3 부록 D): 정원 · 재발급 · 재발급 뒤 옛 코드 입장 · 로그인 잠금. 라이브 PG, 커밋한다.

단일 연결 + 바깥 롤백(db_session)으로는 행 잠금을 못 잰다. 그래서 이 파일은 커밋하는 엔진(NullPool)을 따로 쓰고,
끝에 ORM 표를 전부 TRUNCATE … RESTART IDENTITY CASCADE 한다. 정리가 실패해도 다음 세션의 downgrade base 가 복구한다.

순서는 시간이 아니라 기계로 고정한다(_race):
  A 가 판정을 끝내고 커밋 전에 멈춘다 → B 를 태스크로 띄운다 → 제3 연결이 pg_stat_activity 에서 B 의
  wait_event_type = 'Lock' 을 보거나 B 가 끝날 때까지(최대 5초) 기다린다 → A 커밋 → B 결과를 단언한다.
잠금이 없으면 B 는 A 의 커밋 전에 끝나 A 의 미커밋 쓰기를 못 본 채 판정하므로, 기다리지 않고 빨개진다.
B 의 lock_timeout 10초는 교착·잠금 누수 때 시험이 멈추지 않고 실패하게 하는 안전판이다.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date
from typing import Any

import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from classfit.core.config import Settings
from classfit.core.passwords import hash_password
from classfit.crud import auth as crud_auth
from classfit.crud.admin import insert_admin
from classfit.crud.invite_code import update_code
from classfit.database.session import make_engine, make_session_factory
from classfit.models import AuthAttempt, Base, Enrollment, InviteCode
from classfit.service.auth.login import ATTEMPT_KIND, admin_login, subject_hash
from classfit.service.courses.codes import reissue_invite_code
from classfit.service.enroll.enter import enter_course
from tests.fixtures.courses import open_test_course

TODAY = date(2026, 11, 3)  # 시험 강의(2026-11-02~05) 진행 중, 코드 만료 전
WAIT_SECONDS = 5.0
POLL_SECONDS = 0.02

Factory = async_sessionmaker[AsyncSession]
# 마이그레이션이 넣는 시드 표는 비우지 않는다(0005 document_type, 뒤에 도는 시드 시험이 잰다).
# CASCADE 는 참조하는 쪽으로만 번지므로 이 표를 빼도 TRUNCATE 는 성립한다(T3 계획 착수 조건 ⑩)
SEED_TABLES = frozenset({"document_type"})


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


async def _commit_after[T](
    session: AsyncSession, work: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    result = await work(session)
    await session.commit()
    return result


async def _race[T, U](
    factory: Factory,
    engine: AsyncEngine,
    hold: Callable[[AsyncSession], Awaitable[T]],
    contend: Callable[[AsyncSession], Awaitable[U]],
) -> tuple[T, U, bool]:
    """(A 결과, B 결과, B 가 잠금을 기다렸는지). A 는 hold 뒤 커밋 전에 멈추고, B 를 지켜본 뒤 커밋한다."""
    async with factory() as a, factory() as b:
        first = await hold(a)
        pid = await b.scalar(text("SELECT pg_backend_pid()"))
        await b.execute(text("SET LOCAL lock_timeout = '10s'"))
        task = asyncio.create_task(_commit_after(b, contend))
        try:
            waited = await _waits_on_lock(engine, pid, task)
            await a.commit()
            second = await asyncio.wait_for(task, timeout=15)
        finally:
            if not task.done():
                await a.rollback()  # A 의 잠금을 풀어 B 가 끝나게 한다
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    return first, second, waited


async def _seed_course(
    factory: Factory, *, max_seats: int | None = None
) -> tuple[int, str]:
    """커밋한 시험 강의의 (id, 산 코드)."""
    async with factory() as s, s.begin():
        course, code = await open_test_course(s)
        if max_seats is not None:
            await update_code(s, code, max_seats=max_seats)
        return course.id, code.code


async def _count(factory: Factory, model: type, *where: Any) -> int:
    async with factory() as s:
        stmt = select(func.count()).select_from(model).where(*where)
        return await s.scalar(stmt) or 0


def _enter(
    code: str, email: str, name: str
) -> Callable[[AsyncSession], Awaitable[Any]]:
    async def run(s: AsyncSession) -> Any:
        return await enter_course(
            s, raw_code=code, email=email, name=name, dept=None, today=TODAY
        )

    return run


def _reissue(course_id: int) -> Callable[[AsyncSession], Awaitable[InviteCode]]:
    async def run(s: AsyncSession) -> InviteCode:
        return await reissue_invite_code(s, course_id)

    return run


async def test_concurrent_enroll_capacity(
    factory: Factory, committing: AsyncEngine
) -> None:
    """정원 1. A 가 첫 자리를 잡고 커밋 전에 멈춘 사이 B 가 들어오면, B 는 강의 행 잠금을 기다렸다 full."""
    course_id, code = await _seed_course(factory, max_seats=1)
    first, second, waited = await _race(
        factory,
        committing,
        _enter(code, "a@example.com", "김가명"),
        _enter(code, "b@example.com", "이가명"),
    )
    assert first.outcome == "created"
    assert (second.outcome, waited) == ("full", True)
    assert await _count(factory, Enrollment, Enrollment.course_id == course_id) == 1


async def test_concurrent_reissue_one_live(
    factory: Factory, committing: AsyncEngine
) -> None:
    """재발급 둘이 겹치면 둘째는 첫째의 커밋을 기다렸다 그 새 코드를 다시 바꾼다. 둘 다 성공, 산 행 1 · replaced 2."""
    course_id, old = await _seed_course(factory)
    first, second, waited = await _race(
        factory, committing, _reissue(course_id), _reissue(course_id)
    )
    assert waited is True
    assert len({old, first.code, second.code}) == 3
    async with factory() as s:
        rows = (
            await s.execute(
                select(InviteCode.code, InviteCode.status)
                .where(InviteCode.course_id == course_id)
                .order_by(InviteCode.id)
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        (old, "replaced"),
        (first.code, "replaced"),
        (second.code, "active"),
    ]


async def test_concurrent_reissue_then_enter_old_code_404(
    factory: Factory, committing: AsyncEngine
) -> None:
    """A 재발급이 강의 행 잠금을 쥔 사이 B 가 옛 코드로 새 등록 → A 커밋 뒤 B 는 not_found(끝점 404
    /problems/invite-code-not-found). B 가 잠금 전에 코드 ORM 행을 올리거나 잠금 뒤 populate_existing 없이
    다시 읽으면 replaced 를 못 보고 created 가 된다(T2b 결정 ii)."""
    course_id, old = await _seed_course(factory)
    first, second, waited = await _race(
        factory,
        committing,
        _reissue(course_id),
        _enter(old, "b@example.com", "이가명"),
    )
    assert first.code != old
    assert (second.outcome, waited) == ("not_found", True)
    assert await _count(factory, Enrollment, Enrollment.course_id == course_id) == 0


async def test_concurrent_login_failures_serialized(
    factory: Factory, committing: AsyncEngine
) -> None:
    """실패 9 를 커밋해 둔다. A 의 10번째 실패가 커밋 전인 사이 B 가 오면, B 는 advisory 잠금을 기다렸다
    실패 10 을 세고 locked(T1 리뷰 nit 2 이관, lock_attempt_key)."""
    login_id, client = "admin-race", "192.0.2.10"
    settings = Settings(_env_file=None, login_lock_failures=10, login_lock_minutes=15)
    subject = subject_hash(login_id)
    async with factory() as s, s.begin():
        await insert_admin(
            s, login_id=login_id, password_hash=hash_password("맞는-비밀번호")
        )
        for _ in range(9):
            await crud_auth.insert_attempt(
                s, kind=ATTEMPT_KIND, subject_hash=subject, client=client, ok=False
            )

    def attempt(s: AsyncSession) -> Awaitable[Any]:
        return admin_login(
            s, settings, login_id=login_id, password="틀린-비밀번호", client=client
        )

    first, second, waited = await _race(factory, committing, attempt, attempt)
    assert first.outcome == "failed"
    assert (second.outcome, waited) == ("locked", True)
    failures = (
        AuthAttempt.kind == ATTEMPT_KIND,
        AuthAttempt.subject_hash == subject,
        AuthAttempt.ok.is_(False),
    )
    assert await _count(factory, AuthAttempt, *failures) == 11
