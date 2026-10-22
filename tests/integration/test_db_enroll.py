"""입장·첨부 표(0004, Design 부록 A T2b): 이메일 유일(lower) · 강의당 등록 1 · FK NO ACTION · 첨부 대상 CHECK · 단일 진입. 라이브 PG.

alembic check 는 CHECK 를 비교하지 않으므로 CHECK 는 여기서 잰다. 단일 진입 시험은 src 에서 부르는 곳을 센다(정의 줄 제외).
crud 의 범위·삭제 도우미(scope 판정 · 첨부 일괄 삭제 · 강의 세션 삭제 · 명단 범위)도 여기서 잰다.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import attachment as crud_attachment
from classfit.crud.auth import delete_course_sessions
from classfit.crud.course import delete_course
from classfit.crud.enrollment import insert_enrollment, list_stmt
from classfit.crud.learner import find_learner, get_or_create_learner
from classfit.crud.page import keyset_page
from classfit.crud.schedule import insert_section, insert_session
from classfit.crud.scope import OWNER_KINDS
from classfit.crud.stored_file import insert_stored_file
from classfit.models import (
    AuthSession,
    CourseSession,
    Learner,
    SessionAttachment,
    StoredFile,
)
from classfit.service.auth.sessions import Principal
from tests.fixtures.courses import learner_headers, open_test_course

SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"
UNIQUE_VIOLATION = "23505"
FK_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
_DEFINITION = re.compile(r"^\s*(async\s+def|def|class)\s")


def _callers(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    found = []
    for path in sorted(SRC.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if any(rx.search(line) for line in lines if not _DEFINITION.match(line)):
            found.append(path.relative_to(SRC).as_posix())
    return found


async def _violation(session: AsyncSession, *rows: object) -> str:
    """rows 를 SAVEPOINT 안에서 넣고 위반 sqlstate 를 돌려준다. 바깥 시험 트랜잭션은 산다."""
    with pytest.raises(IntegrityError) as caught:
        async with session.begin_nested():
            session.add_all(rows)
            await session.flush()
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


async def _course_session(
    session: AsyncSession, course_id: int, *, is_open: bool = True
) -> CourseSession:
    section = await insert_section(session, course_id, title="공통")
    return await insert_session(session, section.id, title="1교시", is_open=is_open)


async def _pdf(session: AsyncSession, session_id: int) -> SessionAttachment:
    """첨부 행 → stored_file → file_id 순서(T2b 결정 ix)."""
    row = await crud_attachment.insert_attachment(
        session, session_id=session_id, kind="pdf", title="강의안", description=None
    )
    stored = await insert_stored_file(
        session,
        sha256="0" * 64,
        owner_kind=crud_attachment.OWNER_KIND,
        owner_id=row.id,
        content_type="application/pdf",
        size=5,
    )
    return await crud_attachment.set_file_id(session, row, stored.id)


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    stmt = select(func.count()).select_from(model).where(*where)  # type: ignore[arg-type]
    return await session.scalar(stmt) or 0


# ── Design 부록 A T2b 표 시험


async def test_learner_email_unique_lower(db_session: AsyncSession) -> None:
    db_session.add(Learner(email="kim@example.com"))
    await db_session.flush()
    assert (
        await _violation(db_session, Learner(email="Kim@Example.COM"))
        == UNIQUE_VIOLATION
    )


async def test_enrollment_unique_per_course(db_session: AsyncSession) -> None:
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="B 강의")
    learner = await get_or_create_learner(db_session, "kim@example.com")
    await insert_enrollment(
        db_session, course_id=course.id, learner_id=learner.id, name="김가명", dept=None
    )
    # 다른 강의에는 같은 사람이 따로 등록된다(이름도 따로)
    await insert_enrollment(
        db_session, course_id=other.id, learner_id=learner.id, name="이가명", dept="B팀"
    )
    with pytest.raises(IntegrityError) as caught:
        async with db_session.begin_nested():
            await insert_enrollment(
                db_session,
                course_id=course.id,
                learner_id=learner.id,
                name="박가명",
                dept=None,
            )
    assert caught.value.orig.sqlstate == UNIQUE_VIOLATION  # type: ignore[union-attr]


async def test_enrollment_course_fk_blocks_delete(db_session: AsyncSession) -> None:
    course, _ = await open_test_course(db_session)
    learner = await get_or_create_learner(db_session, "kim@example.com")
    await insert_enrollment(
        db_session, course_id=course.id, learner_id=learner.id, name="김가명", dept=None
    )
    with pytest.raises(IntegrityError) as caught:
        async with db_session.begin_nested():
            await delete_course(db_session, course.id)
    assert caught.value.orig.sqlstate == FK_VIOLATION  # type: ignore[union-attr]


async def test_session_attachment_link_requires_url(db_session: AsyncSession) -> None:
    course, _ = await open_test_course(db_session)
    sid = (await _course_session(db_session, course.id)).id
    file_id = (await _pdf(db_session, sid)).file_id

    def row(kind: str, **over: object) -> SessionAttachment:
        return SessionAttachment(session_id=sid, kind=kind, title="자료", **over)

    assert await _violation(db_session, row("link")) == CHECK_VIOLATION  # url 없음
    assert (
        await _violation(db_session, row("pdf", url="https://example.com/a"))
        == CHECK_VIOLATION
    )  # link 가 아닌데 url
    assert (
        await _violation(
            db_session, row("link", url="https://example.com/a", file_id=file_id)
        )
        == CHECK_VIOLATION
    )  # link 인데 file_id
    assert (
        await _violation(db_session, row("video", url="https://example.com/a"))
        == CHECK_VIOLATION
    )  # 5종 밖
    # 대조: 맞는 link 는 들어간다
    db_session.add(row("link", url="https://example.com/a"))
    await db_session.flush()
    assert (
        await _count(db_session, SessionAttachment, SessionAttachment.session_id == sid)
        == 2
    )


def test_enrollment_created_only_in_enter() -> None:
    # 넣기를 부르는 곳은 service/enroll/enter.py 밖에 없다. 생성자는 crud/enrollment.py 하나다
    assert set(_callers(r"\binsert_enrollment\(")) <= {"service/enroll/enter.py"}
    assert _callers(r"\bEnrollment\(") == ["crud/enrollment.py"]


# ── crud 도우미


async def test_learner_get_or_create_reuses_row(db_session: AsyncSession) -> None:
    first = await get_or_create_learner(db_session, "kim@example.com")
    again = await get_or_create_learner(db_session, "KIM@example.com")
    assert again.id == first.id
    found = await find_learner(db_session, "Kim@Example.com")
    assert found is not None and found.id == first.id
    assert await _count(db_session, Learner) == 1
    assert await find_learner(db_session, "lee@example.com") is None


async def test_session_attachment_owner_check_scope(db_session: AsyncSession) -> None:
    judge = OWNER_KINDS["session_attachment"]
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="B 강의")
    opened = await _pdf(db_session, (await _course_session(db_session, course.id)).id)
    closed_session = await _course_session(db_session, course.id, is_open=False)
    closed = await _pdf(db_session, closed_session.id)

    mine = Principal("learner", 1, course.id)
    assert await judge(db_session, Principal("admin", 1), closed.id) is True
    assert await judge(db_session, mine, opened.id) is True
    assert await judge(db_session, mine, closed.id) is False  # 잠긴 세션
    assert (
        await judge(db_session, Principal("learner", 1, other.id), opened.id) is False
    )
    assert await judge(db_session, Principal("instructor", 1), opened.id) is False
    assert await judge(db_session, mine, 999_999) is False  # 없는 첨부


async def test_session_attachment_lists_scope(db_session: AsyncSession) -> None:
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="B 강의")
    sid = (await _course_session(db_session, course.id)).id
    pdf = await _pdf(db_session, sid)
    link = await crud_attachment.insert_attachment(
        db_session,
        session_id=sid,
        kind="link",
        title="참고",
        description="설명",
        url="https://example.com/a",
    )
    assert (pdf.sort, link.sort) == (0, 1)  # 끝에 붙는다

    admin = Principal("admin", 1)
    rows = await crud_attachment.list_for_session(db_session, admin, sid)
    assert [(a.id, key is not None, size) for a, key, size in rows] == [
        (pdf.id, True, 5),
        (link.id, False, None),
    ]
    by_course = await crud_attachment.list_for_course(db_session, admin, course.id)
    assert [a.id for a, _, _ in by_course] == [pdf.id, link.id]
    mine = Principal("learner", 1, course.id)
    assert len(await crud_attachment.list_for_session(db_session, mine, sid)) == 2
    stranger = Principal("learner", 1, other.id)
    assert await crud_attachment.list_for_session(db_session, stranger, sid) == []
    assert await crud_attachment.list_for_course(db_session, stranger, course.id) == []


async def test_session_attachment_delete_under_scopes(db_session: AsyncSession) -> None:
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="B 강의")
    sec1 = await insert_section(db_session, course.id, title="1부")
    sec2 = await insert_section(db_session, course.id, title="2부")
    s1 = await insert_session(db_session, sec1.id, title="1교시")
    s2 = await insert_session(db_session, sec1.id, title="2교시")
    s3 = await insert_session(db_session, sec2.id, title="3교시")
    for s in (s1, s2, s3):
        await _pdf(db_session, s.id)
    kept = await _pdf(db_session, (await _course_session(db_session, other.id)).id)
    owned = StoredFile.owner_kind == crud_attachment.OWNER_KIND

    with pytest.raises(ValueError):
        await crud_attachment.delete_attachments_under(db_session)
    with pytest.raises(ValueError):
        await crud_attachment.delete_attachments_under(
            db_session, course_id=course.id, session_id=s1.id
        )
    assert (
        await crud_attachment.delete_attachments_under(db_session, session_id=s1.id)
        == 1
    )
    assert (
        await crud_attachment.delete_attachments_under(db_session, section_id=sec1.id)
        == 1
    )
    assert (
        await crud_attachment.delete_attachments_under(db_session, course_id=course.id)
        == 1
    )
    assert (
        await crud_attachment.delete_attachments_under(db_session, course_id=course.id)
        == 0
    )
    # 남은 것은 다른 강의의 첨부와 그 파일 행 하나
    assert await _count(db_session, SessionAttachment) == 1
    assert await _count(db_session, StoredFile, owned) == 1
    assert await crud_attachment.delete_attachment(db_session, kept.id) is True
    assert await crud_attachment.delete_attachment(db_session, kept.id) is False
    assert await _count(db_session, StoredFile, owned) == 0
    # 첨부가 비면 강의는 FK 없이 지워진다
    assert await delete_course(db_session, course.id) is True


async def test_course_sessions_delete_only_that_course(
    db_session: AsyncSession,
) -> None:
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="B 강의")
    await learner_headers(db_session, course.id)
    await learner_headers(db_session, other.id)
    in_course = AuthSession.course_id == course.id
    assert await _count(db_session, AuthSession, in_course) == 1
    assert await delete_course_sessions(db_session, course.id) == 1
    assert await _count(db_session, AuthSession, in_course) == 0
    assert await _count(db_session, AuthSession, AuthSession.course_id == other.id) == 1
    assert await delete_course(db_session, course.id) is True


async def test_enrollment_list_scope_and_email(db_session: AsyncSession) -> None:
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="B 강의")
    for i, email in enumerate(("a@example.com", "b@example.com", "c@example.com")):
        learner = await get_or_create_learner(db_session, email)
        await insert_enrollment(
            db_session,
            course_id=course.id,
            learner_id=learner.id,
            name=f"가명{i}",
            dept=None,
        )
    admin = Principal("admin", 1)
    items, cursor, more = await keyset_page(
        db_session, list_stmt(admin, course.id), None, 2
    )
    assert more is True and cursor is not None
    rest, _, more2 = await keyset_page(
        db_session, list_stmt(admin, course.id), cursor, 2
    )
    assert more2 is False
    emails = {row.learner.email for row in [*items, *rest]}
    assert emails == {"a@example.com", "b@example.com", "c@example.com"}
    stranger = Principal("learner", 1, other.id)
    none, _, _ = await keyset_page(db_session, list_stmt(stranger, course.id), None, 10)
    assert none == []
