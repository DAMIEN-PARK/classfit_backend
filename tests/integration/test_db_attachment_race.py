"""T6 동시성 행동 시험 일곱(T6 결정 xv·xvi): 재배정·세션 삭제와 겹친 넣기 · 상한 경합 · 교체끼리 · 재배정과 겹친 PATCH·교체·
지우기. 라이브 PG, 커밋한다. 이름 접두는 test_attachment_race_(E-11 의 test_concurrent_ 와 다르다).

도우미는 T5 tests/integration/test_db_assign_race.py :77-286 을 그대로 복사했다(그 파일은 고치지 않는다): 커밋하는 NullPool
엔진 committing(끝에 SEED_TABLES 밖의 ORM 표를 TRUNCATE) · factory · pg_stat_activity 로 "B 가 기다렸다" 를 재는
_waits_on_lock · B 가 기다린 행의 표를 재는 _blocked_on · _commit_after · _lock_timeout · _race(A 가 함수를 끝내고 커밋
전에 선다) · _ok · _count · _seed. 장벽 도우미(_pause_after·_race_paused)는 복사하지 않았다 — 일곱 다 _race 꼴로 갈린다.
일곱 다 B 가 기다렸는지와 무엇을 기다렸는지(blocked == {"course"})를 함께 단언한다. 순서는 sleep 이 아니라 Event 와
_waits_on_lock 폴링이 정한다. A 는 운영 경로(sections.patch_session · remove_session · 강사 첨부 service)로 부른다.
재배정 대 쓰기 셋(⑤~⑦)은 B 가 잠그기 전 읽기에서 아직 X 의 세션을 보고 강의 행에서 기다린 뒤, 잠근 뒤 다시 읽어
담당이 Y 로 바뀐 것을 보고 Forbidden 인지를 쓰기마다 따로 잰다(결과 단언 — 제목·file_id·행 수·audit).
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from classfit.core.config import Settings
from classfit.core.errors import Conflict, Forbidden, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import stored_file as crud_stored_file
from classfit.database.session import make_engine, make_session_factory
from classfit.models import AuditLog, Base, SessionAttachment, StoredFile
from classfit.models.attachment import ATTACHMENTS_MAX
from classfit.schemas.course import SessionPatchIn
from classfit.service.courses import sections
from classfit.service.files import my_attachment_edit, my_attachments
from classfit.service.files.store import path_for
from classfit.service.rules.attachment import UPLOAD_KINDS
from tests.fixtures.assign import PDF, course_with_section
from tests.fixtures.instructors import make_instructor
from tests.fixtures.my_attachments import SAMPLES, assigned_session

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


MAX = {kind: 1024 * 1024 for kind in UPLOAD_KINDS}
URL = "https://example.com/race"
OWNER = "session_attachment"


async def _approved(s: AsyncSession, email: str) -> int:
    return await make_instructor(
        s, Settings(_env_file=None), email=email, status="approved"
    )


def _actor(instructor_id: int) -> str:
    return f"instructor:{instructor_id}"


async def _my_session(s: AsyncSession, tag: str) -> tuple[int, int, int]:
    """(X, Y, X 에게 배정된 닫힌 세션 id) — 승인 강사 둘과 강의 하나."""
    x = await _approved(s, f"{tag}-x@example.com")
    y = await _approved(s, f"{tag}-y@example.com")
    _, section = await course_with_section(s)
    return x, y, await assigned_session(s, section.id, instructor_id=x)


def _reassign(session_id: int, instructor_id: int) -> Work:
    """관리자 재배정(운영 문 sections.patch_session). 커밋 전에 서서 강의 행을 쥔다."""

    async def hold(s: AsyncSession) -> Any:
        body = SessionPatchIn(instructor_id=instructor_id)
        return await sections.patch_session(s, session_id, body, actor="admin:1")

    return hold


async def _add_pdf(
    s: AsyncSession, root: Path, x: int, sid: int, data: bytes, title: str = "강의안"
) -> tuple[SessionAttachment, StoredFile]:
    return await my_attachments.add_my_file(
        s,
        root=root,
        max_bytes=MAX,
        instructor_id=x,
        session_id=sid,
        title=title,
        description=None,
        filename="a.pdf",
        data=data,
        actor=_actor(x),
    )


def _link(x: int, sid: int) -> Work:
    async def work(s: AsyncSession) -> SessionAttachment:
        return await my_attachments.add_my_link(
            s,
            instructor_id=x,
            session_id=sid,
            title="링크",
            description=None,
            url=URL,
            actor=_actor(x),
        )

    return work


def _replace(root: Path, x: int, attachment_id: int, data: bytes) -> Work:
    async def work(s: AsyncSession) -> crud_attachment.AttachmentRow:
        return await my_attachment_edit.replace_my_file(
            s,
            root=root,
            max_bytes=MAX,
            instructor_id=x,
            attachment_id=attachment_id,
            filename="v.pdf",
            data=data,
            actor=_actor(x),
        )

    return work


async def _audits(factory: Factory, action: str, actor: str) -> int:
    return await _count(
        factory, AuditLog, AuditLog.action == action, AuditLog.actor == actor
    )


async def _owned_files(factory: Factory, attachment_id: int) -> list[tuple[int, str]]:
    """그 첨부가 소유한 stored_file 행 (id, key), id 순."""
    async with factory() as s:
        stmt = (
            select(StoredFile.id, StoredFile.key)
            .where(StoredFile.owner_kind == OWNER, StoredFile.owner_id == attachment_id)
            .order_by(StoredFile.id)
        )
        return [(i, k) for i, k in (await s.execute(stmt)).all()]


async def _attachment(
    factory: Factory, attachment_id: int
) -> tuple[str, int, int | None] | None:
    """(title, sort, file_id). 없으면 None."""
    async with factory() as s:
        stmt = select(
            SessionAttachment.title, SessionAttachment.sort, SessionAttachment.file_id
        ).where(SessionAttachment.id == attachment_id)
        found = (await s.execute(stmt)).first()
        return None if found is None else (found[0], found[1], found[2])


async def test_attachment_race_reassign_then_write_403(
    factory: Factory, committing: AsyncEngine
) -> None:
    """① 관리자 재배정(A)이 커밋 전인 사이 X 의 링크 넣기(B) → B 는 강의 행에서 기다렸다 잠근 뒤 다시 읽어 403."""
    x, y, sid = await _seed(factory, lambda s: _my_session(s, "arace1"))
    raced = await _race(factory, committing, _reassign(sid, y), _link(x, sid))
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Forbidden), repr(raced.second)
    assert (
        await _count(factory, SessionAttachment, SessionAttachment.session_id == sid)
        == 0
    )
    assert await _audits(factory, "session_attachment.create", _actor(x)) == 0


async def test_attachment_race_session_removed_then_write_404(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """② 세션 삭제(A)가 커밋 전인 사이 X 의 pdf 넣기(B) → 바이트를 쓰고 강의 행에서 기다렸다 404(23503·500 아님)."""
    x, _, sid = await _seed(factory, lambda s: _my_session(s, "arace2"))
    data = SAMPLES[".pdf"]

    async def remove(s: AsyncSession) -> None:
        await sections.remove_session(s, sid)

    async def write(s: AsyncSession) -> Any:
        return await _add_pdf(s, tmp_path, x, sid, data)

    raced = await _race(factory, committing, remove, write)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, NotFound), repr(raced.second)
    assert (
        await _count(factory, SessionAttachment, SessionAttachment.session_id == sid)
        == 0
    )
    assert await _count(factory, StoredFile, StoredFile.owner_kind == OWNER) == 0
    # 바이트는 잠금 앞에서 썼다 — 참조 0 이라 유예 뒤 gc 몫이다
    assert path_for(tmp_path, hashlib.sha256(data).hexdigest()).is_file()


async def test_attachment_race_cap_two_adds_one_409(
    factory: Factory, committing: AsyncEngine
) -> None:
    """③ 첨부 19개인 세션에 X 의 넣기 둘이 겹친다 → 뒤(B)는 강의 행에서 기다렸다 잠근 뒤 다시 세어 409(limit 20)."""

    async def seed(s: AsyncSession) -> tuple[int, int, int]:
        ids = await _my_session(s, "arace3")
        for n in range(ATTACHMENTS_MAX - 1):
            await crud_attachment.insert_attachment(
                s,
                session_id=ids[2],
                kind="link",
                title=f"링크 {n}",
                description=None,
                url=URL,
            )
        return ids

    x, _, sid = await _seed(factory, seed)
    raced = await _race(factory, committing, _link(x, sid), _link(x, sid))
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert raced.second.extra == {"limit": ATTACHMENTS_MAX}
    assert (
        await _count(factory, SessionAttachment, SessionAttachment.session_id == sid)
        == ATTACHMENTS_MAX
    )


async def test_attachment_race_replace_vs_replace_one_file_row(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """④ 같은 pdf 첨부의 교체 둘이 겹친다 → 뒤(B)는 잠근 뒤 다시 읽은 file_id(A 의 F1)를 옛 행으로 지워 파일 행은 하나(F2)."""
    v0, v1, v2 = SAMPLES[".pdf"], PDF + b"%arace4-v1\n", PDF + b"%arace4-v2\n"

    async def seed(s: AsyncSession) -> tuple[int, int, str]:
        x, _, sid = await _my_session(s, "arace4")
        row, stored = await _add_pdf(s, tmp_path, x, sid, v0)
        return x, row.id, stored.key

    x, pid, k0 = await _seed(factory, seed)
    raced = await _race(
        factory,
        committing,
        _replace(tmp_path, x, pid, v1),
        _replace(tmp_path, x, pid, v2),
    )
    assert raced.waited is True
    assert raced.blocked == {"course"}
    _ok(raced)
    k1, k2 = raced.first[1], raced.second[1]
    owned = await _owned_files(factory, pid)
    assert [key for _, key in owned] == [k2]
    found = await _attachment(factory, pid)
    assert found is not None and found[2] == owned[0][0]
    async with factory() as s:
        assert await crud_stored_file.get_by_key(s, k0) is None
        assert (
            await crud_stored_file.get_by_key(s, k1) is None
        )  # 옛 href 404 의 crud 근거


async def _seed_pdf(
    factory: Factory, root: Path, tag: str
) -> tuple[int, int, int, int, int, str]:
    """(X, Y, 세션, pdf 첨부 P, P 의 파일 행 F0, F0 key). P 앞에 링크 하나를 둬 P 는 두 번째(sort 1)다."""

    async def seed(s: AsyncSession) -> tuple[int, int, int, int, int, str]:
        x, y, sid = await _my_session(s, tag)
        await _link(x, sid)(s)
        row, stored = await _add_pdf(s, root, x, sid, SAMPLES[".pdf"], "원래 제목")
        return x, y, sid, row.id, stored.id, stored.key

    return await _seed(factory, seed)


async def test_attachment_race_reassign_then_patch_403(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑤ 재배정(A) 대 X 의 PATCH(B) → B 는 강의 행에서 기다렸다 잠근 뒤 다시 읽어 403. 제목·자리·파일 행·audit 그대로."""
    x, y, sid, pid, f0, k0 = await _seed_pdf(factory, tmp_path, "arace5")
    before = await _attachment(factory, pid)
    assert before is not None and before[:2] == ("원래 제목", 1)

    async def patch(s: AsyncSession) -> Any:
        return await my_attachment_edit.patch_my_attachment(
            s,
            instructor_id=x,
            attachment_id=pid,
            changes={"title": "새 제목", "position": 0},
            actor=_actor(x),
        )

    raced = await _race(factory, committing, _reassign(sid, y), patch)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Forbidden), repr(raced.second)
    assert await _attachment(factory, pid) == before
    assert await _owned_files(factory, pid) == [(f0, k0)]
    assert await _audits(factory, "session_attachment.update", _actor(x)) == 0


async def test_attachment_race_reassign_then_replace_403(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑥ 재배정(A) 대 X 의 교체(B) → B 는 바이트를 쓰고 기다렸다 403. 제목·자리·file_id(F0) 그대로, 새 파일 행 0, audit 0."""
    x, y, sid, pid, f0, k0 = await _seed_pdf(factory, tmp_path, "arace6")
    before = await _attachment(factory, pid)
    assert before == ("원래 제목", 1, f0)
    replace = _replace(tmp_path, x, pid, PDF + b"%arace6-new\n")
    raced = await _race(factory, committing, _reassign(sid, y), replace)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Forbidden), repr(raced.second)
    assert await _attachment(factory, pid) == before
    assert await _owned_files(factory, pid) == [(f0, k0)]
    assert await _audits(factory, "session_attachment.update", _actor(x)) == 0


async def test_attachment_race_reassign_then_delete_403(
    factory: Factory, committing: AsyncEngine, tmp_path: Path
) -> None:
    """⑦ 재배정(A) 대 X 의 지우기(B) → B 는 강의 행에서 기다렸다 403. P(제목·자리·file_id)·F0 행 그대로, audit 0."""
    x, y, sid, pid, f0, k0 = await _seed_pdf(factory, tmp_path, "arace7")
    before = await _attachment(factory, pid)
    assert before == ("원래 제목", 1, f0)

    async def delete(s: AsyncSession) -> None:
        await my_attachments.delete_my_attachment(
            s, instructor_id=x, attachment_id=pid, actor=_actor(x)
        )

    raced = await _race(factory, committing, _reassign(sid, y), delete)
    assert raced.waited is True
    assert raced.blocked == {"course"}
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Forbidden), repr(raced.second)
    assert await _attachment(factory, pid) == before
    assert await _owned_files(factory, pid) == [(f0, k0)]
    assert await _audits(factory, "session_attachment.delete", _actor(x)) == 0
