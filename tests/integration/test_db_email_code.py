"""인증 코드(Design 5절 8·13): issue_email_code() 한 곳에서만 만들고, 미리 보기는 해시를 남기지 않는다. 라이브 PG.

미리 보기·apply 는 scripts.outbox_preview.run 을 거친다(시험 연결에 묶은 session_factory 를 넘긴다).
재발급은 같은 함수를 직접 두 번 부른다.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from classfit.core.passwords import verify_password
from classfit.database.session import make_session_factory
from classfit.models import EmailVerification, MailOutbox
from classfit.service.auth.email_code import issue_email_code

SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"


async def _queued(session: AsyncSession) -> tuple[int, int]:
    """인증 요청 1건 + outbox 1행(kind email_code, params 에 id 만)."""
    verification = EmailVerification(email="a@example.com")
    session.add(verification)
    await session.flush()
    row = MailOutbox(
        kind="email_code",
        params={"verification_id": verification.id},
        to="a@example.com",
    )
    session.add(row)
    await session.flush()
    return verification.id, row.id


async def _state(session: AsyncSession, verification_id: int, outbox_id: int) -> tuple:
    code_hash = await session.scalar(
        select(EmailVerification.code_hash).where(
            EmailVerification.id == verification_id
        )
    )
    sent_at = await session.scalar(
        select(MailOutbox.sent_at).where(MailOutbox.id == outbox_id)
    )
    return code_hash, sent_at


def test_email_code_generated_only_in_issue_email_code() -> None:
    callers = sorted(
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if re.search(r"\b_new_code\(", p.read_text(encoding="utf-8"))
    )
    assert callers == ["service/auth/email_code.py"]


async def test_email_code_preview_stores_no_hash(
    db_connection: AsyncConnection,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.outbox_preview import run

    verification_id, outbox_id = await _queued(db_session)
    factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )
    assert await run([], factory) == 0
    assert "무효 코드(미리 보기)" in capsys.readouterr().out
    assert await _state(db_session, verification_id, outbox_id) == (None, None)


async def test_email_code_apply_stores_hash_and_sent_at(
    db_connection: AsyncConnection, db_session: AsyncSession
) -> None:
    from scripts.outbox_preview import run

    verification_id, outbox_id = await _queued(db_session)
    factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )
    assert await run(["--apply"], factory) == 0
    code_hash, sent_at = await _state(db_session, verification_id, outbox_id)
    assert code_hash is not None and code_hash.startswith("$argon2id$")
    assert sent_at is not None


async def test_email_code_reissue_overwrites_hash(db_session: AsyncSession) -> None:
    verification = EmailVerification(email="a@example.com", tries=3)
    db_session.add(verification)
    await db_session.flush()

    first = await issue_email_code(db_session, verification.id)
    first_hash = await db_session.scalar(
        select(EmailVerification.code_hash).where(
            EmailVerification.id == verification.id
        )
    )
    second = await issue_email_code(db_session, verification.id)
    row = (
        await db_session.execute(
            select(EmailVerification.code_hash, EmailVerification.tries).where(
                EmailVerification.id == verification.id
            )
        )
    ).one()

    assert re.fullmatch(r"\d{6}", first) and re.fullmatch(r"\d{6}", second)
    assert row.code_hash != first_hash
    assert row.tries == 0
    assert verify_password(row.code_hash, second)
    if first != second:  # 10^-6 확률로 같은 코드가 나올 수 있다
        assert not verify_password(row.code_hash, first)
