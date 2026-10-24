"""T7 동시성 행동 시험 일곱(T7 결정 xiii·xiv): 재배정과 기록 저장 · 두 저장 · 저장과 계획대로 · 고침과 일괄 확인 ·
세션 삭제와 사진 올리기 · 재배정과 사진 지우기 · 확인 표시와 세션 삭제의 사진 행 잠금 순서. 라이브 PG, 커밋한다.
이름 접두는 test_record_race_·test_photo_race_(E-11 의 test_concurrent_ 와 다르다).

도우미는 T5 tests/integration/test_db_assign_race.py 의 :77-206(WAIT_SECONDS … _race)과 :271-286(_ok · _count · _seed)을
그대로 복사했다(그 파일과 T2b test_db_concurrency.py · T6 test_db_attachment_race.py 는 고치지 않는다). 장벽 도우미
_pause_after·_race_paused 는 복사하지 않았다 — ①~⑥ 은 A 가 함수를 끝내고 커밋 전에 서는 _race 꼴이고, ⑦ 은 같은
도우미(_lock_timeout · _commit_after · _waits_on_lock · _blocked_on)를 시험 안에서 세 트랜잭션 차례로 조합한다.
A 는 운영 경로로 부른다(배정은 sections.patch_session). 날짜는 service 의 today= 로 준다(시드 강의 일차보다 뒤).
기다렸는지와 무엇을 기다렸는지(①~⑥ course · ⑦ photo)를 함께 단언하고, 결과 단언(행 수·칸 값·audit 수)을 따로 둔다.
순서는 시간이 아니라 _waits_on_lock 폴링과 PG 의 잠금 줄(먼저 기다린 쪽이 먼저)이 정한다(sleep 없음).
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from classfit.core.config import Settings
from classfit.core.errors import Forbidden, NotFound
from classfit.crud import schedule as crud_schedule
from classfit.database.session import make_engine, make_session_factory
from classfit.models import (
    AuditLog,
    Base,
    CourseSession,
    Photo,
    SessionRecord,
    StoredFile,
)
from classfit.schemas.course import SessionPatchIn
from classfit.service.auth.sessions import Principal
from classfit.service.courses import record_days, records, sections
from classfit.service.files import photo_views, photos
from classfit.service.rules.record import RecordFields
from tests.fixtures.assign import approved
from tests.fixtures.records import IMAGES, PAST, Assigned, assigned

WAIT_SECONDS = 5.0
POLL_SECONDS = 0.02
GATHER_SECONDS = 15.0

Factory = async_sessionmaker[AsyncSession]
Work = Callable[[AsyncSession], Awaitable[Any]]
# 마이그레이션이 넣는 시드 표는 비우지 않는다(0005 document_type, T2b test_db_concurrency.py 와 같다)
SEED_TABLES = frozenset({"document_type", "survey_template"})


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


MIB = 1024 * 1024
FIELDS = RecordFields(
    held_on=dt.date(2026, 11, 2),
    start_time=dt.time(13),
    end_time=dt.time(13, 50),
    attendees=3,
    content="진행",
    note=None,
)


def _settings() -> Settings:
    return Settings(_env_file=None)


async def _assigned_x(factory: Factory, tag: str) -> Assigned:
    """승인 강사 X 에게 배정한 지난 1일차 세션 S 하나(커밋)."""

    async def seed(s: AsyncSession) -> Assigned:
        return await assigned(s, _settings(), email=f"{tag}-x@example.com")

    return await _seed(factory, seed)


async def _instructor(factory: Factory, tag: str) -> int:
    async def seed(s: AsyncSession) -> int:
        iid, _ = await approved(s, _settings(), email=f"{tag}@example.com")
        return iid

    return await _seed(factory, seed)


async def _photo(
    factory: Factory, root: Path, x: Assigned, data: bytes
) -> tuple[int, int]:
    """X 가 S 에 올린 사진(커밋) — (사진 id, 파일 행 id)."""

    async def seed(s: AsyncSession) -> tuple[int, int]:
        photo, stored = await photos.add_my_photo(
            s,
            root=root,
            max_bytes=MIB,
            instructor_id=x.instructor_id,
            session_id=x.session_id,
            caption=None,
            filename="race.png",
            data=data,
            today=PAST,
            actor=f"instructor:{x.instructor_id}",
        )
        return photo.id, stored.id

    return await _seed(factory, seed)


async def _record(factory: Factory, session_id: int) -> SessionRecord:
    async with factory() as s:
        row = await s.scalar(
            select(SessionRecord).where(SessionRecord.session_id == session_id)
        )
        assert row is not None
        return row


def _reassign(session_id: int, to: int) -> Work:
    async def work(s: AsyncSession) -> Any:
        return await sections.patch_session(
            s, session_id, SessionPatchIn(instructor_id=to), actor="admin:1"
        )

    return work


def _save_mine(x: Assigned, session_id: int, fields: RecordFields) -> Work:
    async def work(s: AsyncSession) -> Any:
        return await records.save_my_record(
            s,
            instructor_id=x.instructor_id,
            session_id=session_id,
            fields=fields,
            actor=f"instructor:{x.instructor_id}",
        )

    return work


async def test_record_race_reassign_then_put_403(
    factory: Factory, committing: AsyncEngine
) -> None:
    """① 재배정(A)이 커밋 전인 사이 옛 담당 X 의 저장(B) → B 는 강의 행에서 기다리고, 잠근 뒤 새 담당 Y 를 보고 403."""
    x = await _assigned_x(factory, "race-r1")
    y = await _instructor(factory, "race-r1-y")
    raced = await _race(
        factory,
        committing,
        _reassign(x.session_id, y),
        _save_mine(x, x.session_id, FIELDS),
    )
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Forbidden), repr(raced.second)
    assert (
        await _count(factory, SessionRecord, SessionRecord.session_id == x.session_id)
        == 0
    )
    assert (
        await _count(factory, AuditLog, AuditLog.action == "session_record.save") == 0
    )


async def test_record_race_two_puts_one_row(
    factory: Factory, committing: AsyncEngine
) -> None:
    """② 강사 저장(A, none → done)이 커밋 전인 사이 관리자 저장(B) → B 는 기다린 뒤 A 의 행을 고친다(23505 없음)."""
    x = await _assigned_x(factory, "race-r2")

    async def admin_save(s: AsyncSession) -> Any:
        return await records.save_admin_record(
            s,
            admin_id=1,
            session_id=x.session_id,
            fields=replace(FIELDS, content="관리자"),
            actor="admin:1",
        )

    raced = await _race(
        factory,
        committing,
        _save_mine(x, x.session_id, replace(FIELDS, content="강사")),
        admin_save,
    )
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    assert (
        await _count(factory, SessionRecord, SessionRecord.session_id == x.session_id)
        == 1
    )
    row = await _record(factory, x.session_id)
    assert (row.status, row.content, row.recorded_by_kind, row.recorded_by_id) == (
        "ok",
        "관리자",
        "admin",
        1,
    )
    assert row.confirmed_at is not None and row.confirmed_by_id == 1
    assert (
        await _count(factory, AuditLog, AuditLog.action == "session_record.save") == 2
    )


async def test_record_race_put_then_as_planned_keeps_written(
    factory: Factory, committing: AsyncEngine
) -> None:
    """③ X 의 S1 저장(A)이 커밋 전인 사이 X 의 계획대로(B) → B 는 잠근 뒤 S1 의 기록을 보고 건너뛴다(REC-003)."""
    x = await _assigned_x(factory, "race-r3")

    async def second_session(s: AsyncSession) -> int:
        row = await crud_schedule.insert_session(
            s, x.section_id, title="둘째 교육", day_no=1, slot=2, keywords=[]
        )
        await sections.patch_session(
            s, row.id, SessionPatchIn(instructor_id=x.instructor_id), actor="admin:1"
        )
        return row.id

    s2 = await _seed(factory, second_session)

    async def as_planned(s: AsyncSession) -> Any:
        return await record_days.record_day_as_planned(
            s,
            Principal("instructor", x.instructor_id),
            course_id=x.course_id,
            day_no=1,
            today=PAST,
            actor=f"instructor:{x.instructor_id}",
        )

    raced = await _race(
        factory,
        committing,
        _save_mine(x, x.session_id, replace(FIELDS, content="실제 진행")),
        as_planned,
    )
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    assert raced.second.session_ids == [s2]
    assert (await _record(factory, x.session_id)).content == "실제 진행"
    assert (await _record(factory, s2)).status == "done"
    assert (
        await _count(
            factory,
            SessionRecord,
            SessionRecord.session_id.in_([x.session_id, s2]),
        )
        == 2
    )


async def test_record_race_edit_then_confirm_all_sees_fresh(
    factory: Factory, committing: AsyncEngine
) -> None:
    """④ 확인된(ok) 기록을 X 가 고치는(A, ok → done) 사이 관리자 일괄 확인(B) → B 는 잠근 뒤 done 을 보고 ok 로."""
    x = await _assigned_x(factory, "race-r4")

    async def confirmed(s: AsyncSession) -> None:
        await _save_mine(x, x.session_id, FIELDS)(s)
        await records.confirm_record(
            s, admin_id=1, session_id=x.session_id, actor="admin:1"
        )

    await _seed(factory, confirmed)
    assert (await _record(factory, x.session_id)).status == "ok"

    async def confirm_all(s: AsyncSession) -> Any:
        return await record_days.confirm_day(
            s, admin_id=1, course_id=x.course_id, day_no=1, actor="admin:1"
        )

    raced = await _race(
        factory,
        committing,
        _save_mine(x, x.session_id, replace(FIELDS, content="고친 내용")),
        confirm_all,
    )
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    assert raced.first.status == "done"
    assert raced.second.session_ids == [x.session_id]
    row = await _record(factory, x.session_id)
    assert (row.status, row.content, row.recorded_by_kind, row.recorded_by_id) == (
        "ok",
        "고친 내용",
        "instructor",
        x.instructor_id,
    )
    assert row.confirmed_at is not None


async def test_photo_race_session_removed_then_upload_404(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑤ 세션 삭제(A)가 커밋 전인 사이 X 의 사진 올리기(B) → 바이트를 쓴 뒤 강의 행에서 기다리고, 잠근 뒤 404."""
    x = await _assigned_x(factory, "race-p5")

    async def remove(s: AsyncSession) -> Any:
        return await sections.remove_session(s, x.session_id)

    async def upload(s: AsyncSession) -> Any:
        return await photos.add_my_photo(
            s,
            root=tmp_path,
            max_bytes=MIB,
            instructor_id=x.instructor_id,
            session_id=x.session_id,
            caption=None,
            filename="race.png",
            data=IMAGES[".png"] + b"-race5",
            today=PAST,
            actor=f"instructor:{x.instructor_id}",
        )

    raced = await _race(factory, committing, remove, upload)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, NotFound), repr(raced.second)
    assert await _count(factory, Photo) == 0
    assert await _count(factory, StoredFile, StoredFile.owner_kind == "photo") == 0
    assert await _count(factory, AuditLog, AuditLog.action == "photo.create") == 0


async def test_photo_race_reassign_then_delete_403(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑥ 재배정(A)이 커밋 전인 사이 X 가 자기 사진 지우기(B) → B 는 기다린 뒤 새 담당 Y 를 보고 403, 사진은 남는다."""
    x = await _assigned_x(factory, "race-p6")
    y = await _instructor(factory, "race-p6-y")
    pid, fid = await _photo(factory, tmp_path, x, IMAGES[".png"] + b"-race6")

    async def delete(s: AsyncSession) -> Any:
        return await photos.delete_my_photo(
            s,
            instructor_id=x.instructor_id,
            photo_id=pid,
            actor=f"instructor:{x.instructor_id}",
        )

    raced = await _race(factory, committing, _reassign(x.session_id, y), delete)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Forbidden), repr(raced.second)
    assert await _count(factory, Photo, Photo.id == pid) == 1
    assert await _count(factory, StoredFile, StoredFile.id == fid) == 1
    assert await _count(factory, AuditLog, AuditLog.action == "photo.delete") == 0


async def test_photo_race_mark_seen_vs_session_removed_no_deadlock(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑦ H 가 P1 만 쥔 사이 확인 표시 M(P1·P2) → P1 에서 기다림, 세션 삭제 D → 강의를 잡은 뒤 P1 에서 M 뒤에 줄 섬.
    H 커밋 → M 이 P1·P2 를 잡아 커밋, D 가 이어서 지운다. 둘 다 id 오름차순으로 잡아 40P01 이 없다(결정 xiii)."""
    x = await _assigned_x(factory, "race-p7")
    p1, f1 = await _photo(factory, tmp_path, x, IMAGES[".png"] + b"-race7-1")
    p2, f2 = await _photo(factory, tmp_path, x, IMAGES[".png"] + b"-race7-2")
    assert p1 < p2

    async def mark(s: AsyncSession) -> int:
        return await photo_views.mark_seen(s, ids=[p1, p2])

    async def remove(s: AsyncSession) -> Any:
        return await sections.remove_session(s, x.session_id)

    async with factory() as h, factory() as m, factory() as d:
        await _lock_timeout(h)
        await h.execute(
            text("SELECT id FROM photo WHERE id = :p1 FOR UPDATE"), {"p1": p1}
        )
        tasks: list[asyncio.Task[Any]] = []
        try:
            m_pid = await _lock_timeout(m)
            tasks.append(asyncio.create_task(_commit_after(m, mark)))
            assert await _waits_on_lock(committing, m_pid, tasks[0]) is True
            assert await _blocked_on(committing, m_pid) == {"photo"}
            d_pid = await _lock_timeout(d)
            tasks.append(asyncio.create_task(_commit_after(d, remove)))
            assert await _waits_on_lock(committing, d_pid, tasks[1]) is True
            assert await _blocked_on(committing, d_pid) == {"photo"}
            await h.commit()
            marked, removed = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), GATHER_SECONDS
            )
        finally:
            pending = [t for t in tasks if not t.done()]
            if pending:
                await h.rollback()  # H 의 잠금을 풀어 M·D 가 끝나게 한다
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
    for value in (marked, removed):
        assert not isinstance(value, BaseException), repr(value)
    assert marked == 2
    assert await _count(factory, Photo, Photo.session_id == x.session_id) == 0
    assert (
        await _count(
            factory,
            StoredFile,
            StoredFile.owner_kind == "photo",
            StoredFile.id.in_([f1, f2]),
        )
        == 0
    )
    assert await _count(factory, CourseSession, CourseSession.id == x.session_id) == 0
