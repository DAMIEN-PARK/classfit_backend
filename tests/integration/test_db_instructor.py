"""강사 표(0005, Design 부록 A T3): 이메일 유일(lower) · 반려 ⇔ 사유 CHECK · 태그 유일 · 서류 종류당 1 · 서류 시드 ·
인증 요청 이메일당 열린 1행 · 발송 시각 issued_at. 라이브 PG.

alembic check 는 CHECK·시드를 비교하지 않으므로 여기서 잰다. 행은 crud·service 로 직접 만든다(HTTP 픽스처 없음).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict
from classfit.crud.auth import consume_verification, insert_verification
from classfit.crud.instructor import insert_instructor
from classfit.crud.instructor_document import upsert_document
from classfit.crud.stored_file import insert_stored_file
from classfit.crud.tag import insert_tag
from classfit.models import (
    DocumentType,
    EmailVerification,
    Instructor,
    InstructorDocument,
)
from classfit.service.auth.email_code import issue_email_code

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"


def _fields(email: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "email": email,
        "password_hash": "x",
        "name": "강사",
        "phone": "010-0000-0000",
        "status": "pending",
        "terms_version": "2026-10-22",
    }
    return {**base, **over}


def _conflict_sqlstate(exc: Conflict) -> str | None:
    """flush_or_conflict 는 IntegrityError 를 원인으로 달아 Conflict 로 바꾼다."""
    return getattr(getattr(exc.__cause__, "orig", None), "sqlstate", None)


async def _check_violation(session: AsyncSession, **fields: Any) -> str:
    with pytest.raises(IntegrityError) as caught:
        await insert_instructor(session, **fields)
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


async def _violation(session: AsyncSession, *rows: object) -> str:
    """rows 를 SAVEPOINT 안에서 넣고 위반 sqlstate 를 돌려준다. 바깥 시험 트랜잭션은 산다."""
    with pytest.raises(IntegrityError) as caught:
        async with session.begin_nested():
            session.add_all(rows)
            await session.flush()
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


async def _pdf_file(session: AsyncSession, instructor_id: int, digit: str) -> int:
    stored = await insert_stored_file(
        session,
        sha256=digit * 64,
        owner_kind="instructor_document",
        owner_id=instructor_id,
        content_type="application/pdf",
        size=5,
    )
    return stored.id


async def test_instructor_email_unique_lower(db_session: AsyncSession) -> None:
    first = await insert_instructor(db_session, **_fields("a@example.com"))
    with pytest.raises(Conflict) as caught:
        await insert_instructor(db_session, **_fields("A@Example.com"))

    assert _conflict_sqlstate(caught.value) == UNIQUE_VIOLATION
    assert first.status == "pending" and first.career == []
    assert first.terms_agreed_at is not None
    count = await db_session.scalar(select(func.count()).select_from(Instructor))
    assert count == 1


async def test_instructor_rejected_requires_reason_check(
    db_session: AsyncSession,
) -> None:
    no_reason = _fields("a@example.com", status="rejected", reject_reason=None)
    stray_reason = _fields("b@example.com", status="pending", reject_reason="사유")

    assert await _check_violation(db_session, **no_reason) == CHECK_VIOLATION
    assert await _check_violation(db_session, **stray_reason) == CHECK_VIOLATION
    ok = await insert_instructor(
        db_session, **_fields("c@example.com", status="rejected", reject_reason="사유")
    )
    assert ok.reject_reason == "사유"


async def test_tag_unique_kind_name(db_session: AsyncSession) -> None:
    await insert_tag(
        db_session, kind="field", name="프롬프트", group_name="기타", source="admin"
    )
    with pytest.raises(Conflict) as caught:
        await insert_tag(
            db_session,
            kind="field",
            name="프롬프트",
            group_name="기타",
            source="instructor",
        )
    other_kind = await insert_tag(
        db_session, kind="session", name="프롬프트", group_name=None, source="admin"
    )

    assert _conflict_sqlstate(caught.value) == UNIQUE_VIOLATION
    assert other_kind.group_name is None and other_kind.active is True


async def test_instructor_document_unique_per_type(db_session: AsyncSession) -> None:
    instructor = await insert_instructor(db_session, **_fields("a@example.com"))
    first_file = await _pdf_file(db_session, instructor.id, "1")
    second_file = await _pdf_file(db_session, instructor.id, "2")
    row, created, old = await upsert_document(
        db_session, instructor.id, "resume", first_file
    )
    duplicate = InstructorDocument(
        instructor_id=instructor.id, type_id="resume", file_id=second_file
    )

    assert (created, old) == (True, None) and row.submitted_at is not None
    assert await _violation(db_session, duplicate) == UNIQUE_VIOLATION


async def test_document_type_seed_three_rows(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            select(
                DocumentType.id,
                DocumentType.name,
                DocumentType.required,
                DocumentType.sort,
            ).order_by(DocumentType.sort)
        )
    ).all()

    assert [tuple(r) for r in rows] == [
        ("resume", "이력서", True, 1),
        ("cert", "자격증/경력증명", True, 2),
        ("pledge", "강사 서약서", True, 3),
    ]


async def test_email_verification_one_open_per_email(db_session: AsyncSession) -> None:
    first = await insert_verification(db_session, "a@example.com")
    again = await insert_verification(db_session, "a@example.com")
    clash = EmailVerification(email="A@example.com")

    assert again.id == first.id
    assert await _violation(db_session, clash) == UNIQUE_VIOLATION

    instructor = await insert_instructor(db_session, **_fields("a@example.com"))
    await consume_verification(db_session, first.id, instructor.id)
    reopened = await insert_verification(db_session, "a@example.com")
    open_rows = await db_session.scalar(
        select(func.count())
        .select_from(EmailVerification)
        .where(
            func.lower(EmailVerification.email) == "a@example.com",
            EmailVerification.consumed_at.is_(None),
        )
    )

    assert reopened.id != first.id
    assert open_rows == 1


async def test_instructor_email_code_issue_sets_issued_at(
    db_session: AsyncSession,
) -> None:
    row = await insert_verification(db_session, "a@example.com")
    issued = select(EmailVerification.issued_at).where(EmailVerification.id == row.id)
    assert row.issued_at is None

    await issue_email_code(db_session, row.id)
    filled = await db_session.scalar(issued)
    assert filled is not None

    # now() 는 트랜잭션 시작 시각이라 같은 시험 안에서 다시 불러도 같은 값이다. 1시간 전으로 돌려 갱신을 잰다
    await db_session.execute(
        update(EmailVerification)
        .where(EmailVerification.id == row.id)
        .values(issued_at=func.now() - text("interval '1 hour'"))
    )
    past = await db_session.scalar(issued)
    await issue_email_code(db_session, row.id)
    renewed = await db_session.scalar(issued)

    assert past is not None and renewed is not None
    assert renewed > past
    assert renewed == filled
