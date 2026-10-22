"""인증 표 읽기·쓰기: auth_session · auth_attempt · email_verification. flush 까지만.

시각 비교는 DB 의 now() 로 한다(앱과 DB 의 시계가 갈려도 판정이 한 시계에 묶이게).
email_verification 은 이메일당 열린(미소비) 요청 1행이다(부분 유일 색인 uq_email_verification_open, T3 결정 xvi).
이메일은 정규화해 넘기고 비교는 색인과 같은 SQL lower() 로 한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict
from classfit.models import AuthAttempt, AuthSession, EmailVerification


async def insert_session(
    session: AsyncSession,
    *,
    token_hash: str,
    principal_type: str,
    principal_id: int,
    course_id: int | None,
    expires_at: datetime,
) -> AuthSession:
    row = AuthSession(
        token_hash=token_hash,
        principal_type=principal_type,
        principal_id=principal_id,
        course_id=course_id,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    return row


async def find_live_session(
    session: AsyncSession, token_hash: str
) -> AuthSession | None:
    """폐기되지 않고 만료 전인 세션만."""
    stmt = select(AuthSession).where(
        AuthSession.token_hash == token_hash,
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > func.now(),
    )
    return await session.scalar(stmt)


async def revoke_session(session: AsyncSession, token_hash: str) -> bool:
    """살아 있던 세션을 폐기했으면 True."""
    stmt = (
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash, AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
        .returning(AuthSession.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def delete_course_sessions(session: AsyncSession, course_id: int) -> int:
    """그 강의의 auth_session 행을 전부 지운다(만료·폐기 포함). 지운 수.

    강의 삭제가 course 행보다 먼저 부른다. auth_session.course_id FK 가 NO ACTION 이라서다(T2b 결정 xi).
    """
    stmt = (
        delete(AuthSession)
        .where(AuthSession.course_id == course_id)
        .returning(AuthSession.id)
    )
    return len((await session.execute(stmt)).scalars().all())


async def lock_attempt_key(
    session: AsyncSession, *, kind: str, subject_hash: str, client: str
) -> None:
    """같은 (kind, subject_hash, client) 의 시도를 트랜잭션 끝(커밋·롤백)까지 줄 세운다.

    실패를 세고 넣는 사이에 동시 요청이 끼어 잠금 한도를 넘기지 않게 한다. 쓰기가 아니라 잠금이다.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{kind}|{subject_hash}|{client}"},
    )


async def insert_attempt(
    session: AsyncSession, *, kind: str, subject_hash: str, client: str, ok: bool
) -> AuthAttempt:
    row = AuthAttempt(kind=kind, subject_hash=subject_hash, client=client, ok=ok)
    session.add(row)
    await session.flush()
    return row


async def count_recent_failures(
    session: AsyncSession,
    *,
    kind: str,
    subject_hash: str,
    client: str,
    window: timedelta,
) -> int:
    """(kind, subject_hash, client) 의 최근 window 안 실패 수. 키에 client 가 있어 다른 주소는 따로 센다."""
    stmt = (
        select(func.count())
        .select_from(AuthAttempt)
        .where(
            AuthAttempt.kind == kind,
            AuthAttempt.subject_hash == subject_hash,
            AuthAttempt.client == client,
            AuthAttempt.ok.is_(False),
            AuthAttempt.at > func.now() - window,
        )
    )
    return await session.scalar(stmt) or 0


async def set_code_hash(
    session: AsyncSession, verification_id: int, code_hash: str
) -> bool:
    """인증 코드 해시를 덮고 tries 를 0 으로, issued_at 을 now() 로(코드 수명의 기준). 행이 없으면 False."""
    stmt = (
        update(EmailVerification)
        .where(EmailVerification.id == verification_id)
        .values(code_hash=code_hash, tries=0, issued_at=func.now())
        .returning(EmailVerification.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


def _open(email: str) -> ColumnElement[bool]:
    return and_(
        func.lower(EmailVerification.email) == func.lower(email),
        EmailVerification.consumed_at.is_(None),
    )


async def find_open_verification(
    session: AsyncSession, email: str
) -> tuple[EmailVerification, datetime] | None:
    """그 이메일의 열린 요청 행과 DB now()(만료 판정의 "지금")를 한 문장으로. 없으면 None.

    행을 FOR UPDATE 로 잠근다. 다른 주소에서 같은 코드를 동시에 맞혀 봐도 tries 상한을 넘기지 않게 줄 세운다.
    """
    stmt = (
        select(EmailVerification, func.now())
        .where(_open(email))
        .order_by(EmailVerification.id)
        .limit(1)
        .with_for_update(of=EmailVerification)
        .execution_options(populate_existing=True)
    )
    found = (await session.execute(stmt)).first()
    return None if found is None else (found[0], found[1])


async def insert_verification(session: AsyncSession, email: str) -> EmailVerification:
    """그 이메일의 열린 요청 행. 없으면 만든다(있으면 그 행 그대로 — 재요청은 같은 행이다).

    INSERT … ON CONFLICT (lower(email)) WHERE consumed_at IS NULL DO NOTHING 뒤 읽는다(동시 요청도 23505 없음).
    DO NOTHING 과 읽기 사이에 다른 트랜잭션이 그 열린 행을 소비·커밋하면 읽기가 비므로 넣기를 한 번 더 한다.
    그래도 비면 Conflict(409, 다시 요청).
    """
    stmt = (
        insert(EmailVerification)
        .values(email=email)
        .on_conflict_do_nothing(
            index_elements=[func.lower(EmailVerification.email)],
            index_where=EmailVerification.consumed_at.is_(None),
        )
    )
    read = (
        select(EmailVerification)
        .where(_open(email))
        .execution_options(populate_existing=True)
    )
    for _ in range(2):
        await session.execute(stmt)
        row = (await session.scalars(read)).one_or_none()
        if row is not None:
            return row
    raise Conflict("인증 요청이 겹쳤습니다. 다시 요청하세요")


async def bump_tries(session: AsyncSession, verification_id: int) -> int:
    """틀린 시도 1회를 더하고 새 tries 를 돌려준다."""
    stmt = (
        update(EmailVerification)
        .where(EmailVerification.id == verification_id)
        .values(tries=EmailVerification.tries + 1)
        .returning(EmailVerification.tries)
    )
    return (await session.execute(stmt)).scalar_one()


async def consume_verification(
    session: AsyncSession, verification_id: int, instructor_id: int
) -> None:
    """가입이 그 요청을 소비했다(consumed_at = now(), instructor_id). 이후 그 이메일은 새 요청 행을 열 수 있다."""
    await session.execute(
        update(EmailVerification)
        .where(EmailVerification.id == verification_id)
        .values(consumed_at=func.now(), instructor_id=instructor_id)
    )


async def revoke_principal_sessions(
    session: AsyncSession, principal_type: str, principal_id: int
) -> int:
    """그 주체의 산(폐기 안 된) 세션을 전부 폐기한다(revoked_at = now()). 폐기한 수. 강사 정지가 부른다."""
    stmt = (
        update(AuthSession)
        .where(
            AuthSession.principal_type == principal_type,
            AuthSession.principal_id == principal_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
        .returning(AuthSession.id)
    )
    return len((await session.execute(stmt)).scalars().all())
