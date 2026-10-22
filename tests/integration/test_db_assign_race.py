"""T5 동시성 행동 시험 여덟(T5 결정 xvii·xviii): 잠금 순서 · 원본 삭제와 사본 · 풀 배치 · T2a 일정 쓰기 · 섹션 일괄 배정 ·
배정 사본과 관리자 링크. 라이브 PG, 커밋한다. 이름 접두는 test_assign_race_(E-11 의 test_concurrent_ 와 다르다).

틀은 T2b tests/integration/test_db_concurrency.py 를 복사했다(그 파일은 고치지 않는다): 커밋하는 NullPool 엔진
committing(끝에 SEED_TABLES 밖의 ORM 표를 TRUNCATE) · factory · pg_stat_activity 로 "B 가 기다렸다" 를 재는
_waits_on_lock · _commit_after · _race(A 가 함수를 끝내고 커밋 전에 선다). 이 파일에서 더한 것:
- _blocked_on(engine, pid): B 가 무엇을 기다리는지(pg_locks 의 tuple 잠금이 걸린 표 이름 집합). 행 잠금을 기다리는 백엔드는
  그 튜플의 tuple 잠금을 쥔 채 상대의 transactionid 를 기다린다. 기다렸다는 것만으로는 "옳은 행에서" 인지 모른다.
- _pause_after(monkeypatch, module, name): crud 모듈 속성을 감싸 첫 호출만 진짜 함수를 끝낸 뒤 장벽에 세운다.
  service 는 crud 를 모듈 별칭으로 들여 부를 때마다 속성을 찾으므로(crud_schedule.get_day(…)) 감싸개가 먹는다.
- _race_paused: A 를 장벽까지 보내고(못 닿으면 "장벽에 닿지 않음") B 를 띄워 기다림·대기 관계를 잰 뒤 장벽을 푼다.
- _race 는 B 의 대기 관계와 예외를 함께 돌려주고, B 가 기다리는 동안 부를 during 을 받는다.
순서는 시간이 아니라 Event 와 _waits_on_lock 폴링이 정한다(sleep 없음). A·B 둘 다 lock_timeout 10초.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

import classfit.crud.instructor
import classfit.crud.schedule
from classfit.core.config import Settings
from classfit.core.errors import Conflict, NotFound
from classfit.crud import schedule as crud_schedule
from classfit.database.session import make_engine, make_session_factory
from classfit.models import (
    AuditLog,
    Base,
    Course,
    CourseDay,
    CourseSession,
    MailOutbox,
    Section,
    SessionAttachment,
    StoredFile,
)
from classfit.schemas.course import CourseOpenIn, DayPatchIn, DaysPutIn, SessionIn
from classfit.service.courses import assign, days, pool_sessions, sections
from classfit.service.courses.open import open_course
from classfit.service.files.attachments import add_link_attachment
from classfit.service.files.pool_files import remove_file
from classfit.service.files.store import path_for
from classfit.service.pool.capabilities import remove_capability
from scripts import file_gc
from tests.fixtures.assign import (
    PDF,
    capability_files,
    course_with_section,
    curriculum_with_slots,
    own_course_files,
    pool_session,
)
from tests.fixtures.courses import DEFAULTS
from tests.fixtures.instructors import make_instructor
from tests.fixtures.pool import make_pool_course

WAIT_SECONDS = 5.0
POLL_SECONDS = 0.02
GATHER_SECONDS = 15.0

Factory = async_sessionmaker[AsyncSession]
Work = Callable[[AsyncSession], Awaitable[Any]]
# 마이그레이션이 넣는 시드 표는 비우지 않는다(0005 document_type, T2b test_db_concurrency.py 와 같다)
SEED_TABLES = frozenset({"document_type"})


@dataclass(frozen=True)
class _Admin:
    type: str = "admin"
    id: int = 1
    course_id: int | None = None


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


async def _blocked_on(engine: AsyncEngine, pid: int) -> set[str]:
    """B(pid)가 쥔 tuple 잠금의 표 이름 — 행 잠금·UPDATE·DELETE 가 기다리는 행의 표다."""
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        rows = await conn.scalars(
            text(
                "SELECT c.relname FROM pg_locks l JOIN pg_class c ON c.oid = l.relation"
                " WHERE l.pid = :pid AND l.locktype = 'tuple'"
            ),
            {"pid": pid},
        )
        return set(rows.all())


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
    blocked: set[str]  # B 가 기다린 행의 표


async def _race(
    factory: Factory,
    engine: AsyncEngine,
    hold: Work,
    contend: Work,
    during: Callable[[], Awaitable[None]] | None = None,
) -> Raced:
    """A 는 hold 뒤 커밋 전에 멈추고, B 를 띄워 기다림·대기 관계를 잰 뒤(그동안 during) A 를 커밋한다."""
    async with factory() as a, factory() as b:
        await _lock_timeout(a)
        first = await hold(a)
        pid = await _lock_timeout(b)
        task = asyncio.create_task(_commit_after(b, contend))
        try:
            waited = await _waits_on_lock(engine, pid, task)
            blocked = await _blocked_on(engine, pid) if waited else set()
            if during is not None:
                await during()
            await a.commit()
            (second,) = await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True), GATHER_SECONDS
            )
        finally:
            if not task.done():
                await a.rollback()  # A 의 잠금을 풀어 B 가 끝나게 한다
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    return Raced(first, second, waited, blocked)


def _pause_after(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, name: str
) -> tuple[asyncio.Event, asyncio.Event]:
    """(held, release). module.name 의 첫 호출만 진짜 함수를 끝낸 뒤 held 를 켜고 release 를 기다린다."""
    real = getattr(module, name)
    held, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        result = await real(*args, **kwargs)
        if calls == 1:
            held.set()
            await release.wait()
        return result

    monkeypatch.setattr(module, name, wrapper)
    return held, release


async def _race_paused(
    factory: Factory,
    engine: AsyncEngine,
    held: asyncio.Event,
    release: asyncio.Event,
    hold: Work,
    contend: Work,
) -> Raced:
    """A 를 장벽까지 보내고 B 를 띄워 기다림·대기 관계를 잰 뒤 장벽을 푼다. 둘 다 끝나면 결과를 모은다."""
    async with factory() as a, factory() as b:
        await _lock_timeout(a)
        a_task = asyncio.create_task(_commit_after(a, hold))
        b_task: asyncio.Task[Any] | None = None
        try:
            barrier = asyncio.create_task(held.wait())
            await asyncio.wait(
                {a_task, barrier},
                timeout=WAIT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            barrier.cancel()
            if not held.is_set():
                detail = a_task.exception() if a_task.done() else "5초 초과"
                raise AssertionError(f"장벽에 닿지 않음: {detail!r}")
            pid = await _lock_timeout(b)
            b_task = asyncio.create_task(_commit_after(b, contend))
            waited = await _waits_on_lock(engine, pid, b_task)
            blocked = await _blocked_on(engine, pid) if waited else set()
            release.set()
            first, second = await asyncio.wait_for(
                asyncio.gather(a_task, b_task, return_exceptions=True), GATHER_SECONDS
            )
        finally:
            release.set()
            pending = [t for t in (a_task, b_task) if t is not None and not t.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
    return Raced(first, second, waited, blocked)


def _ok(raced: Raced) -> None:
    """A·B 둘 다 예외 없음(40P01 교착 · 55P03 lock_timeout · 23503 · 500 없음)."""
    for value in (raced.first, raced.second):
        assert not isinstance(value, BaseException), repr(value)


async def _count(factory: Factory, model: type, *where: Any) -> int:
    async with factory() as s:
        return (
            await s.scalar(select(func.count()).select_from(model).where(*where)) or 0
        )


async def _seed[T](factory: Factory, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async with factory() as s, s.begin():
        return await work(s)


async def _approved(s: AsyncSession, email: str) -> int:
    return await make_instructor(
        s, Settings(_env_file=None), email=email, status="approved"
    )


def _open_body(**over: Any) -> CourseOpenIn:
    return CourseOpenIn.model_validate({**DEFAULTS, "day_count": 2, **over})


async def _row(s: AsyncSession, session_id: int) -> CourseSession:
    found = await crud_schedule.get_session_and_course(s, session_id)
    assert found is not None
    return found[0]


async def test_assign_race_clone_vs_curriculum_start_no_deadlock(
    factory: Factory, committing: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """① 복제(A)가 강사 잠금 직후 선 사이 같은 커리큘럼으로 시작점(B) → B 는 커리큘럼 행에서 기다리고 둘 다 커밋."""

    async def seed(s: AsyncSession) -> tuple[int, str, int]:
        iid = await _approved(s, "race1-i@example.com")
        slots = [
            {"day": 1, "slot": 1, "title": "차시 1"},
            {"day": 1, "slot": 2, "title": "차시 2"},
        ]
        cid = await curriculum_with_slots(s, None, instructor_id=iid, slots=slots)
        course, section = await course_with_section(s)
        await crud_schedule.insert_session(
            s,
            section.id,
            title="원본 세션",
            keywords=[],
            is_open=False,
            curriculum_id=cid,
            instructor_id=iid,
        )
        return iid, cid, course.id

    iid, cid, source = await _seed(factory, seed)
    held, release = _pause_after(
        monkeypatch, classfit.crud.instructor, "lock_instructor"
    )

    async def clone(s: AsyncSession) -> int:
        course, _ = await open_course(
            s,
            _open_body(start="clone", source_course_id=source, title="복제 강의"),
            actor="admin:1",
            invite_expiry_days=30,
        )
        return course.id

    async def start(s: AsyncSession) -> int:
        course, _ = await open_course(
            s,
            _open_body(start="curriculum", curriculum_id=cid, title="커리큘럼 강의"),
            actor="admin:1",
            invite_expiry_days=30,
        )
        return course.id

    raced = await _race_paused(factory, committing, held, release, clone, start)
    assert raced.waited is True
    assert raced.blocked == {"curriculum"}
    _ok(raced)
    in_course = Section.course_id == raced.first
    async with factory() as s:
        cloned = (
            await s.scalars(select(CourseSession).join(Section).where(in_course))
        ).all()
        started = await s.get(Course, raced.second)
    assert [(r.curriculum_id, r.instructor_id) for r in cloned] == [(cid, iid)]
    assert started is not None and started.curriculum_src_id == cid
    assert (
        await _count(
            factory,
            CourseSession,
            CourseSession.section_id.in_(
                select(Section.id).where(Section.course_id == raced.second)
            ),
        )
        == 2
    )


async def test_assign_race_delete_waits_for_copy_then_gc_keeps_bytes(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """② 배정 복사(A)가 커밋 전인 사이 역량 삭제(B) → B 는 역량 행에서 기다리고, 그동안·둘 다 커밋한 뒤의 gc 가 바이트를 남긴다."""
    settings = Settings(
        _env_file=None, file_store_root=tmp_path, file_gc_grace_hours=24
    )

    async def seed(s: AsyncSession) -> tuple[int, str, int, int]:
        x = await _approved(s, "race2-x@example.com")
        pool = await make_pool_course(s, source="ax")
        await capability_files(
            s, tmp_path, instructor_id=x, pool_id=pool.id, kinds=("pdf",)
        )
        course, section = await course_with_section(s)
        row = await pool_session(s, section_id=section.id, pool_id=pool.id)
        return x, pool.id, course.id, row.id

    x, pool_id, course_id, sid = await _seed(factory, seed)
    async with factory() as s:
        sha = await s.scalar(
            select(StoredFile.sha256).where(StoredFile.owner_kind == "capability_file")
        )
    assert sha is not None
    stored = path_for(tmp_path, sha)
    then = time.time() - 48 * 3600
    os.utime(stored, (then, then))

    async def copy(s: AsyncSession) -> assign.AssignResult:
        return await assign.assign_rows(
            s,
            course_id=course_id,
            rows=[await _row(s, sid)],
            instructor_id=x,
            actor="admin:1",
        )

    async def delete(s: AsyncSession) -> None:
        await remove_capability(s, instructor_id=x, pool_id=pool_id)

    async def gc_while_waiting() -> None:
        assert await file_gc.run(["--apply"], factory, settings) == 0
        assert stored.is_file()  # 원본 행이 아직 커밋돼 있다

    raced = await _race(factory, committing, copy, delete, during=gc_while_waiting)
    assert raced.waited is True
    assert raced.blocked == {"capability"}
    _ok(raced)
    assert raced.first.materials == 1
    assert (
        await _count(factory, StoredFile, StoredFile.owner_kind == "capability_file")
        == 0
    )
    assert await file_gc.run(["--apply"], factory, settings) == 0
    async with factory() as s:
        copy_sha = await s.scalar(
            select(StoredFile.sha256)
            .join(SessionAttachment, SessionAttachment.file_id == StoredFile.id)
            .where(SessionAttachment.session_id == sid)
        )
    assert copy_sha == sha
    assert path_for(tmp_path, copy_sha).read_bytes() == PDF


async def test_assign_race_source_deleted_mid_copy_skipped(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """③ 원본 PDF 삭제(A)가 커밋 전인 사이 소유자 배정(B) → B 는 원본 stored_file 에서 기다렸다 그 파일을 건너뛴다."""

    async def seed(s: AsyncSession) -> tuple[int, int, int, int]:
        owner = await _approved(s, "race3-o@example.com")
        pool = await make_pool_course(s, source="own", owner_instructor_id=owner)
        pdf_id, _ = await own_course_files(
            s, tmp_path, pool_id=pool.id, kinds=("pdf", "link")
        )
        course, section = await course_with_section(s)
        row = await pool_session(s, section_id=section.id, pool_id=pool.id)
        return owner, pdf_id, course.id, row.id

    owner, pdf_id, course_id, sid = await _seed(factory, seed)

    async def delete(s: AsyncSession) -> None:
        await remove_file(
            s,
            owner_kind="pool_course_file",
            file_row_id=pdf_id,
            subject=_Admin(),
            actor="admin:1",
        )

    async def copy(s: AsyncSession) -> assign.AssignResult:
        return await assign.assign_rows(
            s,
            course_id=course_id,
            rows=[await _row(s, sid)],
            instructor_id=owner,
            actor="admin:1",
        )

    raced = await _race(factory, committing, delete, copy)
    assert raced.waited is True
    assert raced.blocked == {"stored_file"}
    _ok(raced)
    assert (raced.second.materials, raced.second.skipped_missing) == (1, 1)
    async with factory() as s:
        rows = (
            await s.execute(
                select(SessionAttachment.kind, SessionAttachment.origin).where(
                    SessionAttachment.session_id == sid
                )
            )
        ).all()
        audit = await s.scalar(
            select(AuditLog).where(AuditLog.action == "session.assign")
        )
    assert [tuple(r) for r in rows] == [("link", "pool_course_file")]
    assert audit is not None and audit.detail["skipped_missing"] == 1


async def test_assign_race_two_pool_placements_no_duplicate_slot(
    factory: Factory, committing: AsyncEngine
) -> None:
    """④ 같은 섹션에 풀 배치 둘이 겹치면 뒤 요청은 강의 행에서 기다렸다 남은 교시를 받는다."""

    async def seed(s: AsyncSession) -> tuple[int, int, list[str]]:
        course, section = await course_with_section(s, day_count=1)
        pools = [
            await make_pool_course(s, source="ax", title=f"과정 {n}") for n in range(4)
        ]
        return course.id, section.id, [p.id for p in pools]

    course_id, section_id, pool_ids = await _seed(factory, seed)

    def place(ids: list[str]) -> Work:
        async def run(s: AsyncSession) -> pool_sessions.FromPoolResult:
            return await pool_sessions.add_from_pool(
                s, course_id=course_id, section_id=section_id, pool_ids=ids, day=1
            )

        return run

    raced = await _race(factory, committing, place(pool_ids[:2]), place(pool_ids[2:]))
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    async with factory() as s:
        placed = (
            await s.execute(
                select(CourseSession.day_no, CourseSession.slot).where(
                    CourseSession.section_id == section_id
                )
            )
        ).all()
    assert sorted(tuple(p) for p in placed) == [(1, 1), (1, 2), (1, 3), (1, 4)]


async def test_assign_race_patch_day_vs_put_days_no_deadlock(
    factory: Factory, committing: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⑤ 일차 PATCH(A)가 일차 UPDATE 직후 선 사이 일차 PUT(B) → B 는 강의 행에서 기다리고 둘 다 커밋, 기간은 B 를 따른다."""

    async def seed(s: AsyncSession) -> int:
        course, _ = await course_with_section(s, day_count=2)
        return course.id

    course_id = await _seed(factory, seed)
    held, release = _pause_after(monkeypatch, classfit.crud.schedule, "apply_fields")
    new_days = [dt.date(2026, 11, 9), dt.date(2026, 11, 10), dt.date(2026, 11, 11)]

    async def patch(s: AsyncSession) -> None:
        course = await s.get(Course, course_id)
        assert course is not None
        await days.patch_day(s, course, 1, DayPatchIn(date=dt.date(2026, 11, 1)))

    async def put(s: AsyncSession) -> None:
        course = await s.get(Course, course_id)
        assert course is not None
        body = DaysPutIn.model_validate(
            {
                "days": [
                    {"date": d, "start_time": "13:00", "end_time": "17:00"}
                    for d in new_days
                ]
            }
        )
        await days.put_days(s, course, body)

    raced = await _race_paused(factory, committing, held, release, patch, put)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    assert await _count(factory, CourseDay, CourseDay.course_id == course_id) == 3
    async with factory() as s:
        course = await s.get(Course, course_id)
    assert course is not None and (course.start_on, course.end_on) == (
        new_days[0],
        new_days[-1],
    )


DANGLING = text(
    "SELECT count(*) FROM session s JOIN section x ON x.id = s.section_id"
    " WHERE x.course_id = :c AND s.day_no IS NOT NULL AND NOT EXISTS"
    " (SELECT 1 FROM course_day d WHERE d.course_id = :c AND d.day_no = s.day_no)"
)


async def test_assign_race_add_session_vs_delete_day_no_dangling_day(
    factory: Factory, committing: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⑥ 세션 넣기(A)가 일차 확인 직후 선 사이 그 일차 지우기(B) → B 는 강의 행에서 기다리고, 없는 일차를 가리키는 세션이 없다.
    반대 순서(일차 지우기가 먼저 끝남)면 세션 넣기는 기다렸다 409."""

    async def seed(s: AsyncSession) -> tuple[int, int]:
        course, section = await course_with_section(s, day_count=2)
        return course.id, section.id

    course_id, section_id = await _seed(factory, seed)
    held, release = _pause_after(monkeypatch, classfit.crud.schedule, "get_day")

    def add(day_no: int) -> Work:
        async def run(s: AsyncSession) -> CourseSession:
            body = SessionIn(title=f"{day_no}일차 세션", day_no=day_no)
            return await sections.add_session(s, course_id, section_id, body)

        return run

    def delete(day_no: int) -> Work:
        async def run(s: AsyncSession) -> None:
            course = await s.get(Course, course_id)
            assert course is not None
            await days.delete_day(s, course, day_no)

        return run

    async def dangling() -> int:
        async with factory() as s:
            return int(await s.scalar(DANGLING, {"c": course_id}) or 0)

    raced = await _race_paused(factory, committing, held, release, add(2), delete(2))
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    assert await dangling() == 0
    sessions = await _count(
        factory, CourseSession, CourseSession.section_id == section_id
    )
    assert sessions == 1

    raced = await _race(factory, committing, delete(1), add(1))
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert (
        await _count(factory, CourseSession, CourseSession.section_id == section_id)
        == sessions
    )
    assert await dangling() == 0


async def test_assign_race_section_assign_vs_remove_section(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑦ 섹션 일괄 배정(A)이 커밋 전인 사이 섹션 지우기(B) → B 는 강의 행에서 기다렸다 사본까지 지운다(23503 없음).
    반대 순서면 일괄 배정은 기다렸다 404(빈 섹션처럼 changed [] 가 아니다)."""

    async def seed(s: AsyncSession) -> tuple[int, int, int, int]:
        x = await _approved(s, "race7-x@example.com")
        pool = await make_pool_course(s, source="ax")
        await capability_files(
            s, tmp_path, instructor_id=x, pool_id=pool.id, kinds=("pdf",)
        )
        course, g = await course_with_section(s)
        h = await crud_schedule.insert_section(s, course.id, title="H")
        for section in (g, g, h):
            await pool_session(s, section_id=section.id, pool_id=pool.id)
        return x, course.id, g.id, h.id

    x, course_id, g, h = await _seed(factory, seed)

    def bulk(section_id: int) -> Work:
        async def run(s: AsyncSession) -> assign.AssignResult:
            return await assign.assign_section(
                s,
                course_id=course_id,
                section_id=section_id,
                instructor_id=x,
                actor="admin:1",
            )

        return run

    def remove(section_id: int) -> Work:
        async def run(s: AsyncSession) -> None:
            await sections.remove_section(s, course_id, section_id)

        return run

    raced = await _race(factory, committing, bulk(g), remove(g))
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    assert (len(raced.first.changed), raced.first.materials) == (2, 2)
    assert await _count(factory, Section, Section.id == g) == 0
    assert await _count(factory, CourseSession, CourseSession.section_id == g) == 0
    assert await _count(factory, SessionAttachment) == 0
    assert (
        await _count(factory, StoredFile, StoredFile.owner_kind == "session_attachment")
        == 0
    )
    audits = await _count(factory, AuditLog, AuditLog.action == "session.assign")
    mails = await _count(factory, MailOutbox, MailOutbox.kind == "session_assigned")
    assert (audits, mails) == (1, 1)

    raced = await _race(factory, committing, remove(h), bulk(h))
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, NotFound), repr(raced.second)
    assert (
        await _count(factory, AuditLog, AuditLog.action == "session.assign") == audits
    )
    assert (
        await _count(factory, MailOutbox, MailOutbox.kind == "session_assigned")
        == mails
    )


async def test_assign_race_assign_copy_vs_admin_link(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑧ 배정(A)이 "첨부 0개" 를 보고 사본을 붙인 뒤 커밋 전인 사이 관리자 링크(B) → B 는 강의 행에서 기다렸다 뒤에 붙는다
    (직렬 순서 "배정 → 링크" 와 같다)."""

    async def seed(s: AsyncSession) -> tuple[int, int, int]:
        x = await _approved(s, "race8-x@example.com")
        pool = await make_pool_course(s, source="ax")
        await capability_files(
            s, tmp_path, instructor_id=x, pool_id=pool.id, kinds=("pdf",)
        )
        course, section = await course_with_section(s)
        row = await pool_session(s, section_id=section.id, pool_id=pool.id)
        return x, course.id, row.id

    x, course_id, sid = await _seed(factory, seed)

    async def copy(s: AsyncSession) -> assign.AssignResult:
        return await assign.assign_rows(
            s,
            course_id=course_id,
            rows=[await _row(s, sid)],
            instructor_id=x,
            actor="admin:1",
        )

    async def link(s: AsyncSession) -> SessionAttachment:
        return await add_link_attachment(
            s,
            session_id=sid,
            title="관리자 링크",
            description=None,
            url="https://example.com/admin",
            actor="admin:1",
        )

    raced = await _race(factory, committing, copy, link)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    async with factory() as s:
        rows = (
            await s.execute(
                select(
                    SessionAttachment.id,
                    SessionAttachment.kind,
                    SessionAttachment.origin,
                )
                .where(SessionAttachment.session_id == sid)
                .order_by(SessionAttachment.sort, SessionAttachment.id)
            )
        ).all()
        audit = await s.scalar(
            select(AuditLog).where(AuditLog.action == "session.assign")
        )
    assert [(kind, origin) for _, kind, origin in rows] == [
        ("pdf", "capability_file"),
        ("link", None),
    ]
    assert rows[0][0] < rows[1][0]
    assert audit is not None and audit.detail["materials"] == 1
