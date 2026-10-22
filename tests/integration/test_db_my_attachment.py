"""강사 첨부의 crud 판정·범위(T6 결정 vi·vii·xv·xxi·xxii): 파일 열람 판정표 · 강사 첨부 목록 범위 · 관리자 목록의 강사
거절 · 교체 종류 비교(service) · 잠금 호출 자리. 라이브 PG.

행은 crud·service 로 직접 만든다(HTTP 없음). 배정은 운영 경로 sections.patch_session 이다(tests/fixtures/my_attachments.py).
시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(T4 대조 실험 13).
잠금 호출 자리 시험은 src 를 ast 로 읽는다(T5 tests/integration/test_db_assign.py 의 _function·_calls 를 복사하고 호출마다
키워드 이름·값도 담게 바꿨다). 잠금이 실제로 줄 세우는지는 tests/integration/test_db_attachment_race.py 의 행동 시험이 잰다.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import attachment as crud_attachment
from classfit.crud import attachment_edit as crud_attachment_edit
from classfit.crud import course as crud_course
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import schedule as crud_schedule
from classfit.crud import scope as crud_scope
from classfit.crud import stored_file as crud_stored_file
from classfit.crud.learner import get_or_create_learner
from classfit.crud.page import keyset_page
from classfit.crud.scope import OWNER_KINDS
from classfit.crud.stored_file import insert_stored_file
from classfit.models import AuditLog, SessionAttachment, StoredFile
from classfit.schemas.course import SessionPatchIn
from classfit.service.auth.sessions import Principal
from classfit.service.courses import my_views, sections
from classfit.service.files import my_attachment_edit, my_attachments
from classfit.service.files.store import path_for
from classfit.service.rules.attachment import UPLOAD_KINDS, FileRejected
from tests.fixtures.assign import course_with_section
from tests.fixtures.instructors import make_instructor
from tests.fixtures.my_attachments import SAMPLES, assigned_session

ADMIN = Principal("admin", 1)
MAX = {kind: 1024 * 1024 for kind in UPLOAD_KINDS}
SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"
# 강사 첨부 쓰기 다섯(T6 결정 xv). 두 파일의 공개 async def 중 쓰기를 부르는 것은 이 다섯뿐이어야 한다
WRITERS = {
    "service/files/my_attachments.py": (
        "add_my_file",
        "add_my_link",
        "delete_my_attachment",
    ),
    "service/files/my_attachment_edit.py": ("patch_my_attachment", "replace_my_file"),
}
ADDS = {"add_my_file", "add_my_link"}
WITH_BYTES = {"add_my_file", "replace_my_file"}
WRITE_CALLS = {
    "insert_attachment",
    "insert_stored_file",
    "set_file_id",
    "swap_file",
    "apply_changes",
    "set_sorts",
    "delete_attachment",
    "audit_attachment",
}
CRUD_MODULES: tuple[ModuleType, ...] = (
    crud_attachment,
    crud_attachment_edit,
    crud_course,
    crud_schedule,
    crud_scope,
    crud_stored_file,
)


async def _approved(session: AsyncSession, email: str) -> int:
    return await make_instructor(
        session, Settings(_env_file=None), email=email, status="approved"
    )


async def _link(session: AsyncSession, session_id: int) -> SessionAttachment:
    return await crud_attachment.insert_attachment(
        session,
        session_id=session_id,
        kind="link",
        title="링크",
        description=None,
        url="https://example.com/a",
    )


async def _pdf(
    session: AsyncSession, session_id: int, data: bytes
) -> SessionAttachment:
    """첨부 행 → stored_file → file_id 순서(T2b 결정 ix). 바이트는 쓰지 않는다(판정·목록만 잰다)."""
    row = await crud_attachment.insert_attachment(
        session, session_id=session_id, kind="pdf", title="강의안", description=None
    )
    stored = await insert_stored_file(
        session,
        sha256=hashlib.sha256(data).hexdigest(),
        owner_kind=crud_attachment.OWNER_KIND,
        owner_id=row.id,
        content_type="application/pdf",
        size=len(data),
    )
    return await crud_attachment.set_file_id(session, row, stored.id)


async def test_attachment_owner_kind_judgment_matrix(db_session: AsyncSession) -> None:
    judge = OWNER_KINDS["session_attachment"]
    x = await _approved(db_session, "matrix-x@example.com")
    y = await _approved(db_session, "matrix-y@example.com")
    z = await _approved(db_session, "matrix-z@example.com")
    course, section = await course_with_section(db_session, title="A 강의")
    other, other_section = await course_with_section(db_session, title="B 강의")
    sessions = {
        "x_closed": await assigned_session(
            db_session, section.id, instructor_id=x, is_open=False
        ),
        "y_open": await assigned_session(
            db_session, section.id, instructor_id=y, is_open=True
        ),
        "y_closed": await assigned_session(
            db_session, section.id, instructor_id=y, is_open=False
        ),
        "b_open": await assigned_session(
            db_session, other_section.id, instructor_id=y, is_open=True
        ),
    }
    att = {name: (await _link(db_session, sid)).id for name, sid in sessions.items()}

    learner = Principal("learner", 1, course.id)
    stranger = Principal("learner", 1, other.id)
    mine = Principal("instructor", x)
    cases = [
        (ADMIN, "x_closed", True),
        (ADMIN, "y_closed", True),
        (learner, "y_open", True),
        (learner, "x_closed", False),  # 같은 강의 닫힌 세션
        (stranger, "y_open", False),  # 남의 강의 수강생
        (stranger, "b_open", True),
        (mine, "x_closed", True),  # 내 닫힌 세션
        (mine, "y_open", True),  # 같은 강의 남의 열린 세션
        (mine, "y_closed", False),  # 같은 강의 남의 닫힌 세션
        (mine, "b_open", False),  # 내 세션이 없는 강의
        (Principal("instructor", z), "y_open", False),  # 배정 없는 강사
        (Principal("learner", x, course.id), "x_closed", False),  # 같은 id 의 다른 종류
        (Principal("system", x), "x_closed", False),
    ]
    for subject, name, expected in cases:
        assert await judge(db_session, subject, att[name]) is expected, (subject, name)
    assert await judge(db_session, mine, 999_999_999) is False  # 없는 첨부

    # X 의 유일한 세션을 Y 에게 다시 배정하면 X 는 그 강의 범위를 잃는다
    await sections.patch_session(
        db_session,
        sessions["x_closed"],
        SessionPatchIn(instructor_id=y),
        actor="admin:1",
    )
    assert await judge(db_session, mine, att["x_closed"]) is False
    assert await judge(db_session, mine, att["y_open"]) is False
    assert await judge(db_session, Principal("instructor", y), att["x_closed"]) is True


async def test_attachment_my_list_scope(db_session: AsyncSession) -> None:
    x = await _approved(db_session, "list-x@example.com")
    y = await _approved(db_session, "list-y@example.com")
    z = await _approved(db_session, "list-z@example.com")
    course, section = await course_with_section(db_session)
    xs = await assigned_session(db_session, section.id, instructor_id=x)
    ys = await assigned_session(db_session, section.id, instructor_id=y, is_open=True)
    data = b"%PDF-1.4\n%t6-list\n"
    pdf = await _pdf(db_session, xs, data)
    link = await _link(db_session, xs)  # 관리자가 넣었든 강사가 넣었든 같은 표다
    y_link = await _link(db_session, ys)

    def shape(
        rows: list[crud_attachment.AttachmentRow],
    ) -> list[tuple[int, bool, int | None]]:
        return [(a.id, key is not None, size) for a, key, size in rows]

    expected = [(pdf.id, True, len(data)), (link.id, False, None)]
    listed = crud_attachment_edit.list_for_my_session
    assert shape(await listed(db_session, ADMIN, xs)) == expected
    assert shape(await listed(db_session, Principal("instructor", x), xs)) == expected
    # 403 미리 판정 없이 범위만으로 0행이다
    assert await listed(db_session, Principal("instructor", y), xs) == []
    assert await listed(db_session, Principal("learner", 1, course.id), xs) == []
    assert await listed(db_session, Principal("instructor", z), xs) == []
    assert [
        a.id for a, _, _ in await listed(db_session, Principal("instructor", y), ys)
    ] == [y_link.id]


async def test_instructor_view_admin_lists_refuse_instructor(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    x = await _approved(db_session, "refuse-x@example.com")
    y = await _approved(db_session, "refuse-y@example.com")
    course, section = await course_with_section(db_session)
    xs = await assigned_session(db_session, section.id, instructor_id=x, is_open=True)
    link = await _link(db_session, xs)
    people = [
        ("r1@example.com", "가명1", "A팀"),
        ("r2@example.com", "가명2", None),
    ]
    for email, name, dept in people:
        learner = await get_or_create_learner(db_session, email)
        await crud_enrollment.insert_enrollment(
            db_session, course_id=course.id, learner_id=learner.id, name=name, dept=dept
        )
    mine = Principal("instructor", x)

    with pytest.raises(ValueError, match="강사 주체로 부르지 않는다"):
        await crud_attachment.list_for_session(db_session, mine, xs)
    with pytest.raises(ValueError, match="강사 주체로 부르지 않는다"):
        await crud_attachment.list_for_course(db_session, mine, course.id)
    with pytest.raises(ValueError, match="강사 주체로 부르지 않는다"):
        crud_enrollment.list_stmt(mine, course.id)

    # 강사 명단(roster_stmt)은 관리자 명단(joinedload 로 learner 를 채운다)을 읽기 전에 잰다 — identity map 이 채운
    # learner 를 돌려주면 lazy="raise" 오류가 나지 않아 거짓 녹색이 된다
    roster, _, more = await keyset_page(
        db_session, crud_enrollment.roster_stmt(mine, course.id), None, 10
    )
    assert more is False
    assert sorted((r.name, r.dept or "") for r in roster) == [
        ("가명1", "A팀"),
        ("가명2", ""),
    ]
    with pytest.raises(InvalidRequestError):
        roster[0].learner  # noqa: B018 — 이메일을 읽을 길이 없다
    stranger, _, _ = await keyset_page(
        db_session,
        crud_enrollment.roster_stmt(Principal("instructor", y), course.id),
        None,
        10,
    )
    assert stranger == []

    # service 명단: 깨진 커서만 InvalidCursor 다. 가드 ValueError 는 커서 오류로 바뀌지 않고 그대로 올라간다
    names, _, _ = await my_views.my_roster(
        db_session, mine, course_id=course.id, cursor=None, limit=10
    )
    assert sorted(r.name for r in names) == ["가명1", "가명2"]
    with pytest.raises(my_views.InvalidCursor):
        await my_views.my_roster(
            db_session, mine, course_id=course.id, cursor="broken!!", limit=10
        )
    assert issubclass(my_views.InvalidCursor, ValueError)
    with monkeypatch.context() as patched:
        patched.setattr(crud_enrollment, "roster_stmt", crud_enrollment.list_stmt)
        with pytest.raises(ValueError, match="강사 주체로 부르지 않는다") as guard:
            await my_views.my_roster(
                db_session, mine, course_id=course.id, cursor="broken!!", limit=10
            )
        assert not isinstance(guard.value, my_views.InvalidCursor)

    # 관리자·수강생 주체는 그대로다
    learner = Principal("learner", 1, course.id)
    for subject in (ADMIN, learner):
        rows = await crud_attachment.list_for_session(db_session, subject, xs)
        assert [a.id for a, _, _ in rows] == [link.id], subject
        by_course = await crud_attachment.list_for_course(
            db_session, subject, course.id
        )
        assert [a.id for a, _, _ in by_course] == [link.id], subject
    page, _, _ = await keyset_page(
        db_session, crud_enrollment.list_stmt(ADMIN, course.id), None, 10
    )
    assert {r.learner.email for r in page} == {email for email, _, _ in people}


async def test_attachment_replace_kind_changed_service(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """교체의 종류 비교를 service 에서 직접 잰다(끝점의 미리 판정과 따로, 대조 실험 22). 바이트를 쓰기 전에 거절한다."""
    x = await _approved(db_session, "kind-x@example.com")
    _, section = await course_with_section(db_session)
    sid = await assigned_session(db_session, section.id, instructor_id=x)
    actor = f"instructor:{x}"
    row, stored = await my_attachments.add_my_file(
        db_session,
        root=tmp_path,
        max_bytes=MAX,
        instructor_id=x,
        session_id=sid,
        title="강의안",
        description=None,
        filename="a.pdf",
        data=SAMPLES[".pdf"],
        actor=actor,
    )
    pid, f0, k0 = row.id, stored.id, stored.key
    png = SAMPLES[".png"]
    with pytest.raises(FileRejected) as caught:
        await my_attachment_edit.replace_my_file(
            db_session,
            root=tmp_path,
            max_bytes=MAX,
            instructor_id=x,
            attachment_id=pid,
            filename="b.png",
            data=png,
            actor=actor,
        )
    assert (caught.value.reason, caught.value.kind) == ("kind_changed", "image")
    found = await crud_attachment_edit.get_with_session(db_session, pid, fresh=True)
    assert found is not None
    assert (found[0].kind, found[0].file_id, found[0].title) == ("pdf", f0, "강의안")
    owned = await db_session.scalars(
        select(StoredFile.key).where(
            StoredFile.owner_kind == crud_attachment.OWNER_KIND,
            StoredFile.owner_id == pid,
        )
    )
    assert owned.all() == [k0]
    updates = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "session_attachment.update")
    )
    assert updates == 0
    assert not path_for(tmp_path, hashlib.sha256(png).hexdigest()).exists()


@dataclass(frozen=True)
class _Call:
    owner: str | None  # 받는 이름(crud_attachment.insert_attachment 면 crud_attachment)
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


def test_attachment_lock_call_sites() -> None:
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
            if fn in WITH_BYTES:
                assert _first(calls, "to_thread", where) < lock, where
            # ③ 잠근 뒤 fresh=True 다시 읽기
            reread = "get_session_and_course" if fn in ADDS else "get_with_session"
            assert any(
                c.name == reread and c.at > lock and c.keywords.get("fresh") == "True"
                for c in calls
            ), f"{where}: 잠근 뒤 {reread}(fresh=True) 가 없다"
            # ④ 넣기 둘은 잠근 뒤 상한을 다시 센다
            if fn in ADDS:
                assert any(
                    c.name == "count_for_session" and c.at > lock for c in calls
                ), where
            # ⑤ PATCH 는 잠근 뒤 목록을 다시 읽고 나서 다시 매긴다
            if fn == "patch_my_attachment":
                rows = _first(calls, "rows_for_session", where)
                assert lock < rows < _first(calls, "set_sorts", where), where
            # ⑥ session.get 판 getter 를 쓰지 않는다
            assert all(c.name != "get_attachment" for c in calls), where
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
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "classfit.crud"
            ):
                assert node.module == "classfit.crud", (relpath, node.module)
                assert all(a.asname == f"crud_{a.name}" for a in node.names), relpath
        # ⑧ 쓰기를 부르는 공개 async def 는 위 다섯뿐(규약 밖 새 쓰기 함수를 막는다)
        writers = {
            node.name
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and not node.name.startswith("_")
            and any(c.name in WRITE_CALLS for c in _calls(node))
        }
        assert writers == set(functions), (relpath, writers)
