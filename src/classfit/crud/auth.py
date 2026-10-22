"""인증 표 읽기·쓰기: auth_session · auth_attempt · email_verification. flush 까지만.

시각 비교는 DB 의 now() 로 한다(앱과 DB 의 시계가 갈려도 판정이 한 시계에 묶이게).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

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
    """인증 코드 해시를 덮고 tries 를 0 으로. 행이 없으면 False."""
    stmt = (
        update(EmailVerification)
        .where(EmailVerification.id == verification_id)
        .values(code_hash=code_hash, tries=0)
        .returning(EmailVerification.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
