"""강사 첨부의 crud 판정·범위(T6 결정 vi·xxi·xxii): 파일 열람 판정표 · 강사 첨부 목록 범위 · 관리자 목록의 강사 거절. 라이브 PG.

행은 crud·service 로 직접 만든다(HTTP 없음). 배정은 운영 경로 sections.patch_session 이다(tests/fixtures/my_attachments.py).
시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(T4 대조 실험 13).
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import attachment as crud_attachment
from classfit.crud import attachment_edit as crud_attachment_edit
from classfit.crud import enrollment as crud_enrollment
from classfit.crud.learner import get_or_create_learner
from classfit.crud.page import keyset_page
from classfit.crud.scope import OWNER_KINDS
from classfit.crud.stored_file import insert_stored_file
from classfit.models import SessionAttachment
from classfit.schemas.course import SessionPatchIn
from classfit.service.auth.sessions import Principal
from classfit.service.courses import sections
from tests.fixtures.assign import course_with_section
from tests.fixtures.instructors import make_instructor
from tests.fixtures.my_attachments import assigned_session

ADMIN = Principal("admin", 1)


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
    db_session: AsyncSession,
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
