"""교육 기록·사진 표와 crud(T7 결정 iv·vii·ix·xiii·xvi): 사진 열람 판정표 · 소유자 삭제가 사진·파일 행·기록을 지움 · 표 제약 ·
잠금 호출 자리. 라이브 PG.

행은 crud·service 로 직접 만든다(HTTP 없음). 배정은 운영 경로 sections.patch_session 이다(tests/fixtures/records.py).
시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(T4 대조 실험 13). 표본 sha 는 시험마다 다르다.
잠금 호출 자리 시험은 src 를 ast 로 읽는다(T6 tests/integration/test_db_my_attachment.py 의 _Call·_function·_calls 를
복사했다 — 호출마다 키워드 이름·값도 담는다). 잠금이 실제로 줄 세우는지는 tests/integration/test_db_record_race.py 가 잰다.
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import attachment as crud_attachment
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import instructor as crud_instructor
from classfit.crud import photo as crud_photo
from classfit.crud import photo_list as crud_photo_list
from classfit.crud import record as crud_record
from classfit.crud import schedule as crud_schedule
from classfit.crud import scope as crud_scope
from classfit.crud import stored_file as crud_stored_file
from classfit.crud.scope import OWNER_KINDS
from classfit.crud.stored_file import insert_stored_file
from classfit.models import (
    CourseSession,
    Photo,
    Section,
    SessionAttachment,
    SessionRecord,
    StoredFile,
)
from classfit.schemas.course import SessionPatchIn
from classfit.service.auth.sessions import Principal
from classfit.service.courses import remove, sections
from tests.fixtures.assign import approved
from tests.fixtures.instructors import count
from tests.fixtures.records import assigned

DAY = dt.date(2026, 11, 2)
SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"
# 기록·사진 쓰기 아홉(T7 결정 xiii). 세 파일의 공개 async def 중 쓰기를 부르는 것은 이 아홉뿐이어야 한다
WRITERS = {
    "service/courses/records.py": (
        "save_my_record",
        "save_admin_record",
        "confirm_record",
    ),
    "service/courses/record_days.py": ("record_day_as_planned", "confirm_day"),
    "service/files/photos.py": (
        "add_my_photo",
        "patch_my_photo",
        "delete_my_photo",
        "delete_photo_as_admin",
    ),
}
WRITE_CALLS = {
    "insert_record",
    "apply_record",
    "confirm_row",
    "insert_photo",
    "insert_stored_file",
    "set_photo_file",
    "set_caption",
    "delete_photo",
    "insert_audit",
}
# 잠근 뒤 fresh=True 로 다시 읽는 getter(③)
REREAD = {
    "save_my_record": "session_context",
    "save_admin_record": "session_context",
    "confirm_record": "session_context",
    "add_my_photo": "session_context",
    "patch_my_photo": "get_with_context",
    "delete_my_photo": "get_with_context",
    "delete_photo_as_admin": "get_with_context",
    "record_day_as_planned": "course_day",
    "confirm_day": "course_day",
}
SAVES = {"save_my_record", "save_admin_record", "confirm_record"}
DAYS = {"record_day_as_planned", "confirm_day"}
# 소유자 삭제 셋: 사진 지우기는 잠금 뒤 · 소유자 행 지우기 앞(⑤)
OWNER_DELETES = (
    ("service/courses/sections.py", "remove_section", "delete_section"),
    ("service/courses/sections.py", "remove_session", "delete_session"),
    ("service/courses/remove.py", "remove_course", "delete_course"),
)
CRUD_MODULES: tuple[ModuleType, ...] = (
    crud_audit,
    crud_course,
    crud_enrollment,
    crud_instructor,
    crud_photo,
    crud_photo_list,
    crud_record,
    crud_schedule,
    crud_scope,
    crud_stored_file,
)


def _settings() -> Settings:
    return Settings(_env_file=None)


def _sha(tag: str) -> str:
    return hashlib.sha256(f"t7-record-{tag}".encode()).hexdigest()


async def _photo(
    db: AsyncSession, *, course_id: int, session_id: int, by_id: int, tag: str
) -> tuple[int, int]:
    """(사진 id, 그 파일 행 id). 넣기 순서는 사진 → stored_file → file_id(service 와 같다)."""
    row = await crud_photo.insert_photo(
        db,
        course_id=course_id,
        session_id=session_id,
        by_kind="instructor",
        by_id=by_id,
        caption=None,
        taken_on=DAY,
    )
    stored = await insert_stored_file(
        db,
        sha256=_sha(tag),
        owner_kind=crud_photo.OWNER_KIND,
        owner_id=row.id,
        content_type="image/png",
        size=16,
    )
    await crud_photo.set_photo_file(db, row, stored.id)
    return row.id, stored.id


async def _record(db: AsyncSession, session_id: int, by_id: int) -> None:
    await crud_record.insert_record(
        db,
        session_id=session_id,
        status="done",
        values={"held_on": DAY, "content": "진행"},
        by_kind="instructor",
        by_id=by_id,
        confirmed_by_id=None,
    )


async def _pdf_attachment(db: AsyncSession, session_id: int, tag: str) -> None:
    row = await crud_attachment.insert_attachment(
        db, session_id=session_id, kind="pdf", title="자료", description=None
    )
    stored = await insert_stored_file(
        db,
        sha256=_sha(f"pdf-{tag}"),
        owner_kind="session_attachment",
        owner_id=row.id,
        content_type="application/pdf",
        size=8,
    )
    await crud_attachment.set_file_id(db, row, stored.id)


async def test_photo_owner_kind_judgment_matrix(db_session: AsyncSession) -> None:
    db = db_session
    judge = OWNER_KINDS["photo"]
    x = await assigned(db, _settings(), email="photo-matrix-x@example.com")
    y, _ = await approved(db, _settings(), email="photo-matrix-y@example.com")
    z, _ = await approved(db, _settings(), email="photo-matrix-z@example.com")
    # Y 는 같은 강의의 다른 세션 담당이다
    other = await crud_schedule.insert_session(
        db, x.section_id, title="다른 교육", day_no=1, slot=2, keywords=[]
    )
    await sections.patch_session(
        db, other.id, SessionPatchIn(instructor_id=y), actor="admin:1"
    )
    pid, _ = await _photo(
        db,
        course_id=x.course_id,
        session_id=x.session_id,
        by_id=x.instructor_id,
        tag="matrix",
    )
    mine = Principal("instructor", x.instructor_id)
    cases = [
        (Principal("admin", 1), True),
        (mine, True),  # 그 세션의 지금 담당
        (Principal("instructor", y), False),  # 같은 강의 다른 세션 담당
        (Principal("instructor", z), False),  # 배정 없는 강사
        (
            Principal("learner", 1, x.course_id),
            False,
        ),  # 같은 강의 수강생(공개 표시 없음)
        (
            Principal("learner", x.instructor_id, x.course_id),
            False,
        ),  # 같은 id 다른 종류
        (Principal("admin", x.instructor_id), True),  # 관리자는 id 와 무관
        (Principal("system", x.instructor_id), False),
    ]
    for subject, expected in cases:
        assert await judge(db, subject, pid) is expected, subject
    assert await judge(db, mine, 999_999_999) is False  # 없는 사진

    # 그 세션을 Y 에게 다시 배정하면 올린 X 는 거짓, 새 담당 Y 는 참
    await sections.patch_session(
        db, x.session_id, SessionPatchIn(instructor_id=y), actor="admin:1"
    )
    assert await judge(db, mine, pid) is False
    assert await judge(db, Principal("instructor", y), pid) is True


async def _left(
    db: AsyncSession, session_id: int, photo_ids: list[int]
) -> dict[str, int]:
    """그 세션의 사진 행 · 그 사진들의 파일 행(owner_kind photo) · 기록 · 첨부 수."""
    return {
        "photos": await count(db, Photo, Photo.session_id == session_id),
        "photo_files": await count(
            db,
            StoredFile,
            StoredFile.owner_kind == "photo",
            StoredFile.owner_id.in_(photo_ids),
        ),
        "records": await count(
            db, SessionRecord, SessionRecord.session_id == session_id
        ),
        "attachments": await count(
            db, SessionAttachment, SessionAttachment.session_id == session_id
        ),
    }


async def test_photo_removed_with_session_section_course(
    db_session: AsyncSession,
) -> None:
    db = db_session
    x = await assigned(db, _settings(), email="photo-remove-x@example.com")
    second_section = await crud_schedule.insert_section(
        db, x.course_id, title="다른 트랙"
    )
    second = await crud_schedule.insert_session(
        db, second_section.id, title="다른 교육", day_no=1, slot=1, keywords=[]
    )
    s1, s2 = x.session_id, second.id
    photos: dict[int, list[int]] = {s1: [], s2: []}
    for sid, n in ((s1, 2), (s2, 1)):  # 여러 행 지우기(id 순 잠금)도 거친다
        for i in range(n):
            pid, _ = await _photo(
                db,
                course_id=x.course_id,
                session_id=sid,
                by_id=x.instructor_id,
                tag=f"remove-{sid}-{i}",
            )
            photos[sid].append(pid)
        await _record(db, sid, x.instructor_id)
        await _pdf_attachment(db, sid, f"remove-{sid}")
    full = {"photos": 2, "photo_files": 2, "records": 1, "attachments": 1}
    gone = dict.fromkeys(full, 0)
    second_full = {"photos": 1, "photo_files": 1, "records": 1, "attachments": 1}
    assert await _left(db, s1, photos[s1]) == full
    assert await _left(db, s2, photos[s2]) == second_full

    for name, deletion, second_after in (
        ("session", lambda: sections.remove_session(db, s1), second_full),
        (
            "section",
            lambda: sections.remove_section(db, x.course_id, x.section_id),
            second_full,
        ),
        ("course", lambda: remove.remove_course(db, x.course_id), gone),
    ):
        tx = await db.begin_nested()
        await deletion()
        assert await _left(db, s1, photos[s1]) == gone, name
        assert await _left(db, s2, photos[s2]) == second_after, name
        assert await count(db, CourseSession, CourseSession.id == s1) == 0, name
        if name == "course":
            assert await count(db, Photo, Photo.course_id == x.course_id) == 0
            assert await count(db, Section, Section.course_id == x.course_id) == 0
        await tx.rollback()
        assert await _left(db, s1, photos[s1]) == full, name
        assert await _left(db, s2, photos[s2]) == second_full, name


async def _violates(
    db: AsyncSession, stmt: Any, sqlstate: str, constraint: str | None = None
) -> None:
    """SAVEPOINT 안에서 stmt 가 sqlstate(그리고 그 제약 이름)로 실패하는지."""
    tx = await db.begin_nested()
    with pytest.raises(IntegrityError) as caught:
        await db.execute(stmt)
    await tx.rollback()
    assert caught.value.orig.sqlstate == sqlstate, caught.value
    if constraint is not None:
        assert caught.value.orig.diag.constraint_name == constraint, caught.value


async def test_record_table_checks(db_session: AsyncSession) -> None:
    db = db_session
    x = await assigned(db, _settings(), email="record-checks-x@example.com")
    records = SessionRecord.__table__
    base = {
        "session_id": x.session_id,
        "status": "done",
        "held_on": DAY,
        "content": "진행",
        "recorded_by_kind": "instructor",
        "recorded_by_id": x.instructor_id,
    }
    confirmed = dt.datetime(2026, 11, 2, 13, tzinfo=dt.UTC)
    bad = [
        ({"status": "none"}, "status"),
        ({"start_time": dt.time(13)}, "time_pair"),
        ({"start_time": dt.time(14), "end_time": dt.time(13)}, "time_order"),
        ({"start_time": dt.time(13), "end_time": dt.time(13)}, "time_order"),
        ({"attendees": -1}, "attendees"),
        ({"attendees": 10_001}, "attendees"),
        ({"content": "   "}, "content"),
        ({"status": "ok"}, "confirmed_status"),  # ok 인데 확인 시각 없음
        ({"status": "ok", "confirmed_at": confirmed}, "confirmed_pair"),  # 확인자 없음
        ({"recorded_by_kind": "learner"}, "recorded_by_kind"),
    ]
    for change, name in bad:
        await _violates(
            db,
            insert(records).values(**(base | change)),
            "23514",
            f"ck_session_record_{name}",
        )
    await _violates(
        db,
        insert(Photo.__table__).values(
            course_id=x.course_id,
            session_id=x.session_id,
            uploaded_by_kind="learner",
            uploaded_by_id=1,
            taken_on=DAY,
        ),
        "23514",
        "ck_photo_uploaded_by_kind",
    )

    # 세션당 1행
    await db.execute(insert(records).values(**base))
    await _violates(
        db, insert(records).values(**base), "23505", "uq_session_record_session_id"
    )
    # 사진 둘이 한 파일 행을 가리킬 수 없다
    pid, file_id = await _photo(
        db,
        course_id=x.course_id,
        session_id=x.session_id,
        by_id=x.instructor_id,
        tag="checks",
    )
    await _violates(
        db,
        insert(Photo.__table__).values(
            course_id=x.course_id,
            session_id=x.session_id,
            file_id=file_id,
            uploaded_by_kind="admin",
            uploaded_by_id=1,
            taken_on=DAY,
        ),
        "23505",
        "uq_photo_file_id",
    )
    # 사진이 남은 세션을 직접 지우면 23503(NO ACTION) — 삭제 경로는 delete_photos_under 를 먼저 부른다
    tx = await db.begin_nested()
    with pytest.raises(IntegrityError) as caught:
        await crud_schedule.delete_session(db, x.session_id)
    await tx.rollback()
    assert caught.value.orig.sqlstate == "23503"
    assert caught.value.orig.diag.constraint_name == "fk_photo_session_id_session"
    # 사진을 지우면 세션 삭제가 기록을 CASCADE 로 같이 지운다
    assert await crud_photo.delete_photo(db, pid) is True
    assert await count(db, StoredFile, StoredFile.id == file_id) == 0
    await crud_schedule.delete_session(db, x.session_id)
    assert await count(db, SessionRecord, SessionRecord.session_id == x.session_id) == 0


@dataclass(frozen=True)
class _Call:
    owner: str | None  # 받는 이름(crud_record.insert_record 면 crud_record)
    name: str
    at: tuple[int, int]  # (줄, 칸)
    keywords: dict[str, str] = field(
        default_factory=dict
    )  # 키워드 이름 → 값 글자(ast.unparse)


def _tree(relpath: str) -> ast.Module:
    return ast.parse((SRC / relpath).read_text(encoding="utf-8"))


def _function(relpath: str, function: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    (body,) = [
        node
        for node in ast.walk(_tree(relpath))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name == function
    ]
    return body


def _calls(node: ast.AST) -> list[_Call]:
    """node 안의 호출을 소스 순서(줄, 칸)로. ast.walk 는 소스 순서를 보장하지 않는다."""
    found: list[_Call] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        keywords = {k.arg: ast.unparse(k.value) for k in sub.keywords if k.arg}
        func = sub.func
        if isinstance(func, ast.Attribute):
            owner = func.value.id if isinstance(func.value, ast.Name) else None
            found.append(
                _Call(owner, func.attr, (sub.lineno, sub.col_offset), keywords)
            )
        elif isinstance(func, ast.Name):
            found.append(_Call(None, func.id, (sub.lineno, sub.col_offset), keywords))
    return sorted(found, key=lambda c: c.at)


def _awaited(node: ast.AST) -> list[str]:
    """node 안에서 await 하는 호출의 이름(소스 순서) — DB 를 치는 호출이다."""
    hits = [
        (sub.lineno, sub.col_offset, _calls(sub.value)[0].name)
        for sub in ast.walk(node)
        if isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call)
    ]
    return [name for *_, name in sorted(hits)]


def _first(calls: list[_Call], name: str, where: str) -> tuple[int, int]:
    hits = [c.at for c in calls if c.name == name]
    assert hits, f"{where}: {name}( 호출이 없다"
    return hits[0]


def _crud_names() -> set[str]:
    return {
        name
        for module in CRUD_MODULES
        for name, value in vars(module).items()
        if inspect.isfunction(value) and value.__module__ == module.__name__
    }


def test_record_lock_call_sites() -> None:
    crud_names = _crud_names()
    for relpath, functions in WRITERS.items():
        for fn in functions:
            where = f"{relpath}::{fn}"
            calls = _calls(_function(relpath, fn))
            lock = _first(calls, "lock_course", where)
            # ① 잠금이 첫 쓰기 앞
            writes = [c.at for c in calls if c.name in WRITE_CALLS]
            assert writes and lock < min(writes), f"{where}: 쓰기가 잠금 앞이다"
            # ② 바이트 쓰기는 잠금 앞
            if fn == "add_my_photo":
                assert _first(calls, "to_thread", where) < lock, where
            # ③ 잠근 뒤 fresh=True 다시 읽기(저장·확인은 기록도)
            reread = REREAD[fn]
            assert any(
                c.name == reread and c.at > lock and c.keywords.get("fresh") == "True"
                for c in calls
            ), f"{where}: 잠근 뒤 {reread}(fresh=True) 가 없다"
            if fn in SAVES:
                assert any(
                    c.name == "get_record"
                    and lock < c.at < min(writes)
                    and c.keywords.get("fresh") == "True"
                    for c in calls
                ), f"{where}: 잠근 뒤 get_record(fresh=True) 가 없다"
            # ④ 일차 둘은 잠근 뒤 그 일차 세션·기록을 다시 읽고 나서 쓴다
            if fn in DAYS:
                rows = _first(calls, "day_sessions", where)
                assert lock < rows < min(writes), where
            # ⑥ 잠근 뒤 session.get 판 getter 로 판정하지 않는다
            assert not any(c.name == "get_course" and c.at > lock for c in calls), where
            assert not any(c.owner == "session" and c.name == "get" for c in calls)
            # ⑦ crud 는 모듈 별칭 속성으로 부른다(감싸개가 먹는 꼴)
            bare = [
                c.name
                for c in calls
                if c.name in crud_names and not (c.owner or "").startswith("crud_")
            ]
            assert bare == [], f"{where}: crud 를 별칭 밖에서 부른다 — {bare}"

    for relpath, functions in WRITERS.items():
        tree = _tree(relpath)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module == "classfit.crud":
                assert all(a.asname == f"crud_{a.name}" for a in node.names), relpath
            elif module.startswith("classfit.crud."):
                # 형(SessionContext·Subject 등)만 들인다 — 함수는 별칭 속성으로
                loaded = importlib.import_module(module)
                for alias in node.names:
                    assert not inspect.isfunction(getattr(loaded, alias.name)), (
                        relpath,
                        alias.name,
                    )
        # ⑧ 쓰기를 부르는 공개 async def 는 위 아홉뿐(규약 밖 새 쓰기 함수를 막는다)
        writers = {
            node.name
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and not node.name.startswith("_")
            and any(c.name in WRITE_CALLS for c in _calls(node))
        }
        assert writers == set(functions), (relpath, writers)

    # ⑤ 소유자 삭제 셋: 잠금 → 첨부 → 사진 → 소유자 행
    for relpath, fn, owner_delete in OWNER_DELETES:
        where = f"{relpath}::{fn}"
        calls = _calls(_function(relpath, fn))
        lock = _first(calls, "lock_course", where)
        attachments = _first(calls, "delete_attachments_under", where)
        photos = _first(calls, "delete_photos_under", where)
        assert lock < attachments < photos < _first(calls, owner_delete, where), where
        assert [c.owner for c in calls if c.name == "delete_photos_under"] == [
            "crud_photo"
        ], where

    # ⑨ 확인 표시는 강의를 잠그지 않고, 사진 여러 행을 잡는 crud 둘은 같은 id 순 잠금을 먼저 부른다
    marks = _calls(_function("service/files/photo_views.py", "mark_seen"))
    assert all(c.name != "lock_course" for c in marks)
    assert any(c.owner == "crud_photo" and c.name == "mark_seen" for c in marks)
    for fn in ("mark_seen", "delete_photos_under"):
        awaited = _awaited(_function("crud/photo.py", fn))
        assert awaited and awaited[0] == "_lock_in_id_order", (fn, awaited)
    lock_source = inspect.getsource(crud_photo._lock_in_id_order)
    assert "with_for_update(" in lock_source and "order_by(Photo.id" in lock_source
    # 오름차순이다 — 확인 표시와 사진 여러 행 지우기가 같은 차례로 잡는다
    assert "desc(" not in lock_source
    for_update = [
        c for c in _calls(_tree("crud/photo.py")) if c.name == "with_for_update"
    ]
    assert len(for_update) == 1
    assert for_update[0].at[0] in range(
        crud_photo._lock_in_id_order.__code__.co_firstlineno,
        crud_photo._lock_in_id_order.__code__.co_firstlineno
        + len(lock_source.splitlines()),
    )
