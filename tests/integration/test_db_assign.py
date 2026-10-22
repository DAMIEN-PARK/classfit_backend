"""강의 배정(0007, Design 부록 A T5): 새 칸·FK·CHECK origin · 강사 강의 범위 · 기본 강의안 원본 순서 · 행 복제 한
트랜잭션 · 배정 상태 판정 · 잠금 호출 자리 · 배정 알림 미리 보기. 라이브 PG.

alembic check 는 CHECK 를 비교하지 않으므로 여기서 잰다(23514). 행은 crud·service 로 직접 만든다(HTTP 픽스처 없음).
시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(nextval 은 롤백돼도 돌아오지 않는다 — T4 대조 실험 13).
잠금 호출 자리 시험은 src 를 ast 로 읽는다(T3 tests/integration/test_db_instructor.py 의 _calls_in 을 순서까지 보게 바꿨다).
잠금이 실제로 줄 세우는지는 tests/integration/test_db_assign_race.py 의 행동 시험이 잰다.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from classfit.core.config import Settings
from classfit.core.errors import Conflict, NotFound
from classfit.crud import course as crud_course
from classfit.crud import schedule as crud_schedule
from classfit.crud.attachment import insert_attachment
from classfit.crud.instructor import lock_instructor, set_status, update_instructor
from classfit.crud.materials import curriculum_sources, pool_sources
from classfit.crud.outbox import enqueue
from classfit.crud.pool_file import FILE_OWNER_KINDS, insert_file_row
from classfit.crud.scope import OWNER_KINDS, course_scope
from classfit.database.session import make_session_factory
from classfit.models import (
    AuditLog,
    CapabilityFile,
    Course,
    MailOutbox,
    SessionAttachment,
    StoredFile,
)
from classfit.models.attachment import ATTACHMENT_ORIGINS
from classfit.schemas.course import SessionIn, SessionPatchIn
from classfit.service.courses import assign, sections
from classfit.service.courses.mine import MY_SESSION_FIELDS
from classfit.service.courses.remove import remove_course
from scripts import outbox_preview
from tests.fixtures.assign import (
    PDF,
    capability_files,
    course_with_section,
    curriculum_with_slots,
    own_course_files,
    pool_session,
)
from tests.fixtures.instructors import make_instructor
from tests.fixtures.pool import make_pool_course

SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"
FK_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
PDF_SHA = hashlib.sha256(PDF).hexdigest()
NEW_COLUMNS = {
    ("session", "pool_course_id"),
    ("session", "curriculum_id"),
    ("session", "instructor_id"),
    ("course", "curriculum_src_id"),
    ("session_attachment", "origin"),
}


@dataclass(frozen=True)
class _Subject:
    type: str
    id: int
    course_id: int | None = None


async def _instructor(
    session: AsyncSession, email: str, status: str = "approved"
) -> int:
    return await make_instructor(
        session, Settings(_env_file=None), email=email, status=status
    )


async def _sqlstate(session: AsyncSession, stmt: str, **params: object) -> str:
    """stmt 를 SAVEPOINT 안에서 돌리고 위반 sqlstate 를 돌려준다. 바깥 시험 트랜잭션은 산다."""
    with pytest.raises(IntegrityError) as caught:
        async with session.begin_nested():
            await session.execute(text(stmt), params)
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


async def test_assign_migration_columns_and_fk(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT table_name, column_name, is_nullable, column_default"
                " FROM information_schema.columns"
                " WHERE table_schema = 'public'"
                " AND (table_name, column_name) IN ("
                "('session', 'pool_course_id'), ('session', 'curriculum_id'),"
                " ('session', 'instructor_id'), ('course', 'curriculum_src_id'),"
                " ('session_attachment', 'origin'))"
            )
        )
    ).all()
    assert {(t, c) for t, c, _, _ in rows} == NEW_COLUMNS
    assert all(
        nullable == "YES" and default is None for _, _, nullable, default in rows
    ), rows

    course, section = await course_with_section(db_session)
    row = await crud_schedule.insert_session(
        db_session, section.id, title="세션", keywords=[], is_open=False
    )
    for column, value in (
        ("instructor_id", 999_999_999),
        ("pool_course_id", "ax-none"),
        ("curriculum_id", "cur-none"),
    ):
        assert (
            await _sqlstate(
                db_session,
                f"UPDATE session SET {column} = :v WHERE id = :id",
                v=value,
                id=row.id,
            )
            == FK_VIOLATION
        ), column
    assert (
        await _sqlstate(
            db_session,
            "UPDATE course SET curriculum_src_id = 'cur-none' WHERE id = :id",
            id=course.id,
        )
        == FK_VIOLATION
    )

    attachment = await insert_attachment(
        db_session,
        session_id=row.id,
        kind="link",
        title="링크",
        description=None,
        url="https://example.com/a",
    )
    assert attachment.origin is None  # 보통 첨부
    for origin in ATTACHMENT_ORIGINS:  # 값 집합 안은 된다
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE session_attachment SET origin = :o WHERE id = :id"),
                {"o": origin, "id": attachment.id},
            )
    assert (
        await _sqlstate(
            db_session,
            "UPDATE session_attachment SET origin = 'session_attachment' WHERE id = :id",
            id=attachment.id,
        )
        == CHECK_VIOLATION
    )
    assert set(ATTACHMENT_ORIGINS) == set(FILE_OWNER_KINDS)

    indexes = set(
        (
            await db_session.scalars(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'session'")
            )
        ).all()
    )
    assert "ix_session_instructor_id" in indexes


async def test_assign_course_scope_instructor_branch(db_session: AsyncSession) -> None:
    x = await _instructor(db_session, "scope-x@example.com")
    y = await _instructor(db_session, "scope-y@example.com")
    z = await _instructor(db_session, "scope-z@example.com")
    mine, mine_section = await course_with_section(db_session, title="X 강의")
    other, other_section = await course_with_section(db_session, title="Y 강의")
    empty, _ = await course_with_section(db_session, title="배정 없음")
    ids = {mine.id, other.id, empty.id}

    x_session = await crud_schedule.insert_session(
        db_session, mine_section.id, title="X 세션", keywords=[], is_open=True
    )
    await crud_schedule.insert_session(
        db_session, mine_section.id, title="미배정", keywords=[], is_open=True
    )
    y_session = await crud_schedule.insert_session(
        db_session, other_section.id, title="Y 세션", keywords=[], is_open=True
    )
    await crud_schedule.set_instructor(db_session, [x_session], x)
    await crud_schedule.set_instructor(db_session, [y_session], y)

    async def visible(subject: _Subject) -> set[int]:
        stmt = select(Course.id).where(course_scope(subject)).where(Course.id.in_(ids))
        return set((await db_session.scalars(stmt)).all())

    assert await visible(_Subject("admin", 1)) == ids
    assert await visible(_Subject("learner", 1, other.id)) == {other.id}
    assert await visible(_Subject("instructor", x)) == {mine.id}
    assert await visible(_Subject("instructor", y)) == {other.id}
    assert await visible(_Subject("instructor", z)) == set()
    assert await visible(_Subject("learner", 1, None)) == set()
    assert await visible(_Subject("system", x)) == set()
    assert await crud_course.in_scope(db_session, _Subject("instructor", x), mine.id)
    assert not await crud_course.in_scope(
        db_session, _Subject("instructor", x), other.id
    )

    # 강의 범위 안이어도 강사의 첨부 판정은 거짓이다(T6 몫, 결정 xii)
    attachment = await insert_attachment(
        db_session,
        session_id=x_session.id,
        kind="link",
        title="링크",
        description=None,
        url="https://example.com/a",
    )
    check = OWNER_KINDS["session_attachment"]
    assert not await check(db_session, _Subject("instructor", x), attachment.id)
    assert await check(db_session, _Subject("admin", 1), attachment.id)

    # 배정을 바꾸면 범위가 따라간다
    await crud_schedule.set_instructor(db_session, [x_session], None)
    assert await visible(_Subject("instructor", x)) == set()


async def test_default_material_sources_order(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await _instructor(db_session, "src-owner@example.com")
    other = await _instructor(db_session, "src-other@example.com")
    course = await make_pool_course(db_session, source="own", owner_instructor_id=owner)
    await own_course_files(
        db_session, tmp_path, pool_id=course.id, kinds=("pdf", "link")
    )
    # file_id 없는 pdf 행(넣다 만 행)은 원본이 아니다
    await insert_file_row(
        db_session, "pool_course_file", course.id, kind="pdf", title="빈 행"
    )
    await capability_files(
        db_session, tmp_path, instructor_id=owner, pool_id=course.id, kinds=("pdf",)
    )
    await capability_files(
        db_session,
        tmp_path,
        instructor_id=other,
        pool_id=course.id,
        kinds=("link", "pdf"),
    )

    def shape(sources: list) -> list[tuple[str, str, str, str | None, str | None]]:
        return [(s.origin, s.kind, s.title, s.url, s.sha256) for s in sources]

    url = "https://example.com/guide"
    got = await pool_sources(db_session, pool_course_id=course.id, instructor_id=owner)
    assert got.skipped_missing == 0
    assert shape(got.sources) == [
        ("pool_course_file", "pdf", "강의안 1", None, PDF_SHA),
        ("pool_course_file", "link", "참고 자료 2", url, None),
        ("capability_file", "pdf", "강의안 1", None, PDF_SHA),
    ]
    pdf = got.sources[0]
    assert (pdf.content_type, pdf.size) == ("application/pdf", len(PDF))
    assert (got.sources[1].content_type, got.sources[1].size) == (None, None)

    # 소유자가 아니면 남의 고유 과정 파일을 주지 않는다(T4 결정 ix)
    got = await pool_sources(db_session, pool_course_id=course.id, instructor_id=other)
    assert got.skipped_missing == 0
    assert shape(got.sources) == [
        ("capability_file", "link", "참고 자료 1", url, None),
        ("capability_file", "pdf", "강의안 2", None, PDF_SHA),
    ]

    # 역량도 소유도 없으면 비어 있다
    third = await _instructor(db_session, "src-third@example.com")
    got = await pool_sources(db_session, pool_course_id=course.id, instructor_id=third)
    assert (got.sources, got.skipped_missing) == ([], 0)

    curriculum_id = await curriculum_with_slots(
        db_session,
        tmp_path,
        instructor_id=owner,
        slots=[{"day": 1, "slot": 1, "title": "차시"}],
        kinds=("link", "pdf", "link"),
    )
    got = await curriculum_sources(db_session, curriculum_id)
    assert got.skipped_missing == 0
    assert shape(got.sources) == [
        ("curriculum_file", "link", "참고 자료 1", url, None),
        ("curriculum_file", "pdf", "강의안 2", None, PDF_SHA),
        ("curriculum_file", "link", "참고 자료 3", url, None),
    ]

    # 풀 세션 픽스처는 과정을 가리키는 미배정 세션을 만든다
    _, section = await course_with_section(db_session)
    row = await pool_session(db_session, section_id=section.id, pool_id=course.id)
    assert (row.pool_course_id, row.instructor_id, row.title) == (
        course.id,
        None,
        course.title,
    )


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    stmt = select(func.count()).select_from(model).where(*where)
    return await session.scalar(stmt) or 0


async def _assigned_pool_session(
    session: AsyncSession, root: Path, email: str
) -> tuple[int, Course, int]:
    """(승인 강사 X, 강의, X 의 역량 파일(pdf·link)이 있는 AX 과정을 가리키는 미배정 세션 id)."""
    x = await _instructor(session, email)
    pool = await make_pool_course(session, source="ax")
    await capability_files(session, root, instructor_id=x, pool_id=pool.id)
    course, section = await course_with_section(session)
    row = await pool_session(session, section_id=section.id, pool_id=pool.id)
    return x, course, row.id


async def test_default_material_copy_same_tx_rollback(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    x, course, sid = await _assigned_pool_session(
        db_session, tmp_path, "tx-x@example.com"
    )
    copies = (StoredFile.owner_kind == "session_attachment",)
    sources = await _count(
        db_session, StoredFile, StoredFile.owner_kind == "capability_file"
    )
    nested = await db_session.begin_nested()
    found = await crud_schedule.get_session_and_course(db_session, sid)
    assert found is not None
    result = await assign.assign_rows(
        db_session,
        course_id=course.id,
        rows=[found[0]],
        instructor_id=x,
        actor="admin:1",
    )
    assert (result.changed, result.materials, result.skipped_missing) == ([sid], 2, 0)
    assert (
        await _count(db_session, SessionAttachment, SessionAttachment.session_id == sid)
        == 2
    )
    assert await _count(db_session, StoredFile, *copies) == 1
    await nested.rollback()
    assert (
        await _count(db_session, SessionAttachment, SessionAttachment.session_id == sid)
        == 0
    )
    assert await _count(db_session, StoredFile, *copies) == 0
    assert await _count(db_session, CapabilityFile) == 2
    assert (
        await _count(db_session, StoredFile, StoredFile.owner_kind == "capability_file")
        == sources
        == 1
    )


async def test_assign_service_status_matrix(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    x, course, sid = await _assigned_pool_session(
        db_session, tmp_path, "mx-x@example.com"
    )
    found = await crud_schedule.get_session_and_course(db_session, sid)
    assert found is not None
    row = found[0]

    async def assign_to(instructor_id: int | None) -> assign.AssignResult:
        return await assign.assign_rows(
            db_session,
            course_id=course.id,
            rows=[row],
            instructor_id=instructor_id,
            actor="admin:1",
        )

    for status in ("pending", "rejected", "suspended"):
        other = await _instructor(db_session, f"mx-{status}@example.com", status)
        with pytest.raises(Conflict) as caught:
            await assign_to(other)
        assert caught.value.extra == {"instructor_status": status}
        with pytest.raises(Conflict):
            await assign.lock_assignable(db_session, other)
    assert row.instructor_id is None
    assert await _count(db_session, AuditLog, AuditLog.action == "session.assign") == 0

    with pytest.raises(NotFound):
        await assign_to(999_999_999)

    result = await assign_to(x)
    assert result.changed == [sid] and row.instructor_id == x
    assert (await assign_to(x)).changed == []  # 같은 값은 기록 없음
    assert await _count(db_session, AuditLog, AuditLog.action == "session.assign") == 1
    assert (
        await _count(db_session, MailOutbox, MailOutbox.kind == "session_assigned") == 1
    )

    # 배정 뒤 정지되면 같은 값으로 다시 줘도 409(상태 판정이 먼저다), 해제는 상태를 보지 않는다
    locked = await lock_instructor(db_session, x)
    assert locked is not None
    await set_status(db_session, locked, "suspended", reject_reason=None)
    with pytest.raises(Conflict):
        await assign_to(x)
    assert (await assign_to(None)).changed == [sid]
    assert row.instructor_id is None
    audits = (
        await db_session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "session.assign")
            .order_by(AuditLog.id)
        )
    ).all()
    assert [a.detail["instructor_id"] for a in audits] == [x, None]
    assert audits[1].detail["sessions"] == [{"id": sid, "title": row.title, "from": x}]
    assert (
        await _count(db_session, MailOutbox, MailOutbox.kind == "session_assigned") == 1
    )


# ── 잠금 호출 자리(결정 xvii·xviii). (받는 이름, 호출 이름, 줄) — `x.f(…)` 면 ("x", "f"), `f(…)` 면 (None, "f")
Call = tuple[str | None, str, int, int]
LOCK_SITES = {
    "service/courses/assign.py": ("assign_rows", "lock_assignable", "assign_section"),
    "service/courses/mine.py": ("patch_my_session",),
    "service/courses/starts.py": ("load_curriculum", "load_clone"),
    "service/courses/pool_sessions.py": ("add_from_pool",),
    "service/courses/sections.py": (
        "add_section",
        "patch_section",
        "remove_section",
        "add_session",
        "patch_session",
        "remove_session",
    ),
    "service/courses/days.py": ("patch_course", "put_days", "patch_day", "delete_day"),
    "service/files/attachments.py": (
        "add_pdf_attachment",
        "add_link_attachment",
        "delete_attachment",
    ),
    "crud/materials.py": (
        "key_share_refs",
        "share_sources",
        "pool_sources",
        "curriculum_sources",
    ),
    "crud/course.py": ("lock_course",),
}
# days.py·sections.py 의 쓰기 함수(규약은 파일 단위다 — 새 쓰기 함수는 이 열거 단언이 막는다, codex 2차 #1)
SCHEDULE_WRITERS = {
    "patch_course",
    "put_days",
    "patch_day",
    "delete_day",
    "add_section",
    "patch_section",
    "remove_section",
    "add_session",
    "patch_session",
    "remove_session",
}
# crud.schedule·course·attachment 의 쓰기 함수 이름(T5 가 더한 set_instructor 포함)
CRUD_WRITES = {
    "insert_section",
    "insert_session",
    "insert_days",
    "replace_days",
    "apply_fields",
    "update_course",
    "delete_day",
    "delete_section",
    "delete_session",
    "delete_attachments_under",
    "unset_session_days",
    "set_instructor",
}
# crud 를 감싼 같은 파일 도우미(첫 crud 호출을 셀 때 crud 호출로 본다)
CRUD_HELPERS = {"section_in_course", "_require_day", "_follow_period", "_session"}


def _function(relpath: str, function: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse((SRC / relpath).read_text(encoding="utf-8"))
    (body,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name == function
    ]
    return body


def _calls(node: ast.AST) -> list[Call]:
    """node 안의 호출을 소스 순서(줄, 칸)로. ast.walk 는 소스 순서를 보장하지 않는다."""
    found: list[Call] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Attribute):
            owner = func.value.id if isinstance(func.value, ast.Name) else None
            found.append((owner, func.attr, sub.lineno, sub.col_offset))
        elif isinstance(func, ast.Name):
            found.append((None, func.id, sub.lineno, sub.col_offset))
    return sorted(found, key=lambda c: (c[2], c[3]))


def _calls_in(relpath: str, function: str) -> list[Call]:
    return _calls(_function(relpath, function))


def _first(calls: list[Call], name: str, where: str) -> tuple[int, int]:
    hits = [(line, col) for _, n, line, col in calls if n == name]
    assert hits, f"{where}: {name}( 호출이 없다"
    return hits[0]


def _ordered(calls: list[Call], where: str, *names: str) -> None:
    """names 의 첫 호출이 이 순서로 나온다."""
    at = [_first(calls, n, where) for n in names]
    assert at == sorted(at), f"{where}: 순서가 {names} 가 아니다 — {at}"


def _after_lock(calls: list[Call], name: str, where: str) -> bool:
    lock = _first(calls, "lock_course", where)
    return any(n == name and (line, col) > lock for _, n, line, col in calls)


def _first_crud(calls: list[Call]) -> list[str]:
    """lock_course 앞까지의 crud 호출(받는 이름 crud_*)과 crud 를 감싼 도우미 이름."""
    out = []
    for owner, name, _, _ in calls:
        if name == "lock_course":
            return out
        if (owner or "").startswith("crud_") or name in CRUD_HELPERS:
            out.append(name)
    raise AssertionError("lock_course( 호출이 없다")


def test_assign_lock_call_sites() -> None:
    calls = {
        (relpath, fn): _calls_in(relpath, fn)
        for relpath, functions in LOCK_SITES.items()
        for fn in functions
    }
    assert len(calls) == 25

    def c(relpath: str, fn: str) -> list[Call]:
        return calls[(relpath, fn)]

    a, sec, days = (
        "service/courses/assign.py",
        "service/courses/sections.py",
        "service/courses/days.py",
    )
    att, mat = "service/files/attachments.py", "crud/materials.py"
    # ① 잠금끼리의 순서
    _ordered(
        c(a, "assign_rows"),
        "assign_rows",
        "lock_course",
        "lock_assignable",
        "assign_locked",
    )
    _first(c(a, "lock_assignable"), "lock_instructor", "lock_assignable")
    starts = "service/courses/starts.py"
    _ordered(
        c(starts, "load_curriculum"),
        "load_curriculum",
        "lock_curriculum",
        "lock_assignable",
    )
    _ordered(c(starts, "load_clone"), "load_clone", "key_share_refs", "lock_assignable")
    for fn in ("pool_sources", "curriculum_sources"):
        _first(c(mat, fn), "share_sources", fn)
    for relpath, fn in (
        (mat, "key_share_refs"),
        (mat, "share_sources"),
        ("crud/course.py", "lock_course"),
    ):
        _first(c(relpath, fn), "with_for_update", fn)

    # ② lock_course 가 첫 쓰기보다 앞
    _ordered(c(a, "assign_section"), "assign_section", "lock_course", "lock_assignable")
    _ordered(
        c(a, "assign_section"),
        "assign_section",
        "lock_course",
        "list_section_sessions",
        "assign_locked",
    )
    _ordered(
        c("service/courses/mine.py", "patch_my_session"),
        "patch_my_session",
        "lock_course",
        "apply_fields",
    )
    _ordered(
        c("service/courses/pool_sessions.py", "add_from_pool"),
        "add_from_pool",
        "section_in_course",
        "key_share_refs",
        "lock_course",
        "used_slots",
        "insert_session",
    )
    for relpath, fn in [(sec, f) for f in LOCK_SITES[sec]] + [
        (days, f) for f in LOCK_SITES[days]
    ]:
        before = _first_crud(c(relpath, fn))
        allowed = ["_session"] if fn in {"patch_session", "remove_session"} else []
        assert before == allowed, (fn, before)
    _ordered(c(sec, "add_section"), "add_section", "lock_course", "insert_section")
    _ordered(
        c(sec, "patch_section"),
        "patch_section",
        "lock_course",
        "section_in_course",
        "apply_fields",
    )
    _ordered(
        c(sec, "remove_section"),
        "remove_section",
        "lock_course",
        "section_in_course",
        "delete_attachments_under",
    )
    _ordered(
        c(sec, "add_session"),
        "add_session",
        "lock_course",
        "section_in_course",
        "_require_day",
        "insert_session",
    )
    _ordered(c(sec, "patch_session"), "patch_session", "lock_course", "lock_assignable")
    _ordered(
        c(sec, "patch_session"),
        "patch_session",
        "lock_course",
        "apply_fields",
        "assign_locked",
    )
    _ordered(
        c(sec, "remove_session"),
        "remove_session",
        "lock_course",
        "delete_attachments_under",
    )
    _ordered(c(days, "patch_course"), "patch_course", "lock_course", "update_course")
    _ordered(
        c(days, "put_days"),
        "put_days",
        "lock_course",
        "replace_days",
        "unset_session_days",
    )
    _ordered(
        c(days, "patch_day"),
        "patch_day",
        "lock_course",
        "get_day",
        "apply_fields",
        "_follow_period",
    )
    _ordered(c(days, "delete_day"), "delete_day", "lock_course", "delete_day")
    _ordered(
        c(att, "add_pdf_attachment"),
        "add_pdf_attachment",
        "to_thread",
        "lock_course",
        "insert_attachment",
    )
    _ordered(
        c(att, "add_link_attachment"),
        "add_link_attachment",
        "lock_course",
        "insert_attachment",
    )
    delete = c(att, "delete_attachment")
    crud_delete = [
        (line, col)
        for o, n, line, col in delete
        if (o, n) == ("crud_attachment", "delete_attachment")
    ]
    assert crud_delete and crud_delete[0] > _first(
        delete, "lock_course", "delete_attachment"
    )

    # ③ 잠근 뒤 다시 읽기
    for relpath, fn in (
        (a, "assign_section"),
        ("service/courses/pool_sessions.py", "add_from_pool"),
    ):
        assert _after_lock(c(relpath, fn), "section_in_course", fn), fn
    for relpath, fn in (
        (sec, "patch_session"),
        (sec, "remove_session"),
        ("service/courses/mine.py", "patch_my_session"),
        (att, "add_pdf_attachment"),
        (att, "add_link_attachment"),
    ):
        assert _after_lock(c(relpath, fn), "get_session_and_course", fn), fn
    assert not _after_lock(delete, "get_attachment", "delete_attachment")

    # ④ days.py·sections.py 의 쓰기 함수 열거 == 열 개, 쓰기 crud 를 부르는 밑줄 도우미는 그 안에서만 불린다
    writers: set[str] = set()
    helpers: dict[str, set[str]] = {}
    for relpath in (sec, days):
        tree = ast.parse((SRC / relpath).read_text(encoding="utf-8"))
        top = [
            n
            for n in tree.body
            if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef)
        ]
        writing = {
            n.name
            for n in top
            if any(
                ((o or "").startswith("crud_") and name in CRUD_WRITES)
                or name == "assign_locked"
                for o, name, _, _ in _calls(n)
            )
        }
        writers |= {n for n in writing if not n.startswith("_")}
        for n in top:
            for _, name, _, _ in _calls(n):
                if name in writing and name.startswith("_"):
                    helpers.setdefault(name, set()).add(n.name)
    assert writers == SCHEDULE_WRITERS
    assert set(helpers) == {"_follow_period"}, helpers
    assert helpers["_follow_period"] <= SCHEDULE_WRITERS, helpers


# ── 담당 강사는 set_instructor 로만(crud/schedule.py 독스트링 · T5 리뷰 Nit 5)
SESSION_SINKS = {
    "insert_session",
    "apply_fields",
}  # 세션 칸을 쓰는 crud.schedule 함수(정의는 crud/schedule.py)


def _schedule_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """(crud.schedule 모듈을 가리키는 이름, crud.schedule 에서 직접 들인 SESSION_SINKS 함수 이름)."""
    modules: set[str] = set()
    funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "classfit.crud":
            modules |= {a.asname or a.name for a in node.names if a.name == "schedule"}
        elif (
            isinstance(node, ast.ImportFrom) and node.module == "classfit.crud.schedule"
        ):
            funcs |= {a.asname or a.name for a in node.names if a.name in SESSION_SINKS}
        elif isinstance(node, ast.Import):
            modules |= {
                a.asname
                for a in node.names
                if a.name == "classfit.crud.schedule" and a.asname
            }
    return modules, funcs


def _dict_keys(node: ast.AST) -> set[str]:
    """dict 리터럴·dict(…) 호출이 넣는 글자 키."""
    if isinstance(node, ast.Dict):
        return {
            k.value
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
    ):
        return {kw.arg for kw in node.keywords if kw.arg} | {
            key for arg in node.args for key in _dict_keys(arg)
        }
    return set()


def _puts_instructor(scope: ast.AST, name: str) -> bool:
    """scope 안에서 name 이라는 dict 에 instructor_id 키를 넣는 꼴(대입 · 첨자 대입 · update · setdefault)."""
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if (
                    isinstance(t, ast.Name)
                    and t.id == name
                    and node.value is not None
                    and "instructor_id" in _dict_keys(node.value)
                ):
                    return True
                if (
                    isinstance(t, ast.Subscript)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == name
                    and isinstance(t.slice, ast.Constant)
                    and t.slice.value == "instructor_id"
                ):
                    return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
            and node.func.attr in {"update", "setdefault", "__setitem__"}
        ):
            keys = {kw.arg for kw in node.keywords if kw.arg}
            for arg in node.args:
                keys |= _dict_keys(arg)
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.add(arg.value)
            if "instructor_id" in keys:
                return True
    return False


def _returns_instructor(tree: ast.Module, function: str) -> bool:
    """같은 모듈 함수 function 이 instructor_id 키가 든 dict 를 돌려주는가(**_place(…) 꼴)."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == function
        ):
            for ret in ast.walk(node):
                if (
                    isinstance(ret, ast.Return)
                    and ret.value is not None
                    and "instructor_id" in _dict_keys(ret.value)
                ):
                    return True
    return False


def test_assign_instructor_set_only_via_set_instructor() -> None:
    """src 의 insert_session(·apply_fields( 호출(crud.schedule 것)이 instructor_id 를 넘기지 않는다 — 키워드로도,
    ** 로 넘기는 dict·같은 파일 도우미의 반환 dict 에 그 키를 넣어서도. 담당 강사는 set_instructor 하나로만 바뀌어
    배정 audit·outbox·기본 강의안을 건너뛰지 못한다. 정의 쪽 crud/schedule.py 는 뺀다."""
    found: list[str] = []
    bad: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel == "crud/schedule.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules, funcs = _schedule_names(tree)
        scopes = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        for scope in scopes:
            for node in ast.walk(scope):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                sink = (
                    isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and f.value.id in modules
                    and f.attr in SESSION_SINKS
                ) or (isinstance(f, ast.Name) and f.id in funcs)
                if not sink:
                    continue
                where = f"{rel}:{node.lineno}"
                found.append(where)
                for kw in node.keywords:
                    if kw.arg == "instructor_id":
                        bad.append(f"{where} 키워드")
                    elif kw.arg is None and (
                        "instructor_id" in _dict_keys(kw.value)
                        or (
                            isinstance(kw.value, ast.Name)
                            and _puts_instructor(scope, kw.value.id)
                        )
                        or (
                            isinstance(kw.value, ast.Call)
                            and isinstance(kw.value.func, ast.Name)
                            and _returns_instructor(tree, kw.value.func.id)
                        )
                    ):
                        bad.append(f"{where} ** dict")
                for arg in node.args[
                    2:
                ]:  # apply_fields(session, row, fields) 의 fields
                    if "instructor_id" in _dict_keys(arg) or (
                        isinstance(arg, ast.Name) and _puts_instructor(scope, arg.id)
                    ):
                        bad.append(f"{where} 칸 dict")
    assert len(found) >= 8, (
        found
    )  # 지금 sections 3 · days 1 · mine 1 · pool_sessions 1 · starts 2
    assert bad == [], bad

    # 본문 모델이 그 키를 실어 오는 꼴: SessionIn·강사 PATCH 칸에는 없고, 관리자 SessionPatchIn 에는 있어
    # sections.patch_session 이 apply_fields 앞에서 pop 한다(그 뒤 assign_locked 가 기록한다)
    assert "instructor_id" not in SessionIn.model_fields
    assert "instructor_id" not in MY_SESSION_FIELDS
    assert "instructor_id" in SessionPatchIn.model_fields
    patch = _function("service/courses/sections.py", "patch_session")
    pops = [
        n.lineno
        for n in ast.walk(patch)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "pop"
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == "instructor_id"
    ]
    applies = [line for _, name, line, _ in _calls(patch) if name == "apply_fields"]
    assert pops and applies and min(pops) < min(applies), (pops, applies)


async def test_assign_outbox_preview_session_assigned(
    db_connection: AsyncConnection,
    db_session: AsyncSession,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    x, course, sid = await _assigned_pool_session(
        db_session, tmp_path, "ob-x@example.com"
    )
    locked = await lock_instructor(db_session, x)
    assert locked is not None
    await update_instructor(db_session, locked, name="가명 엑스")
    found = await crud_schedule.get_session_and_course(db_session, sid)
    assert found is not None
    await crud_schedule.apply_fields(db_session, found[0], {"title": "옛 제목"})
    body = SessionPatchIn.model_validate({"title": "새 제목", "instructor_id": x})
    await sections.patch_session(db_session, sid, body, actor="admin:1")
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "session.assign")
    )
    assert audit is not None and audit.detail["sessions"][0]["title"] == "새 제목"
    factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )

    async def preview() -> str:
        assert await outbox_preview.run([], factory) == 0
        messages = json.loads(capsys.readouterr().out)["messages"]
        (message,) = [m for m in messages if m["kind"] == "session_assigned"]
        assert message["to"] == "ob-x@example.com"
        return str(message["body"])

    text_ = await preview()
    assert "가명 엑스" in text_ and course.title in text_ and "새 제목" in text_
    assert "옛 제목" not in text_ and "ob-x@example.com" not in text_
    await remove_course(db_session, course.id)
    assert await db_session.get(Course, course.id) is None
    assert await preview() == text_


async def test_assign_outbox_preview_mismatched_audit_3(
    db_connection: AsyncConnection,
    db_session: AsyncSession,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    x, course, sid = await _assigned_pool_session(
        db_session, tmp_path, "mm-x@example.com"
    )
    y = await _instructor(db_session, "mm-y@example.com")
    found = await crud_schedule.get_session_and_course(db_session, sid)
    assert found is not None
    await assign.assign_rows(
        db_session,
        course_id=course.id,
        rows=[found[0]],
        instructor_id=y,
        actor="admin:1",
    )
    y_audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "session.assign")
    )
    open_audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "course.open")
    )
    assert y_audit is not None and open_audit is not None
    factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )
    assert await outbox_preview.run([], factory) == 0  # y 의 배정 알림은 맞다
    capsys.readouterr()
    for audit_id in (y_audit.id, open_audit.id):  # 다른 강사의 배정 · 다른 action
        bad = await enqueue(
            db_session,
            kind="session_assigned",
            params={"instructor_id": x, "audit_id": audit_id},
            to="mm-x@example.com",
        )
        assert await outbox_preview.run(["--apply"], factory) == 3
        assert "전제 거절" in capsys.readouterr().err
        assert (
            await _count(db_session, MailOutbox, MailOutbox.sent_at.is_not(None)) == 0
        )
        await db_session.delete(bad)
        await db_session.flush()
