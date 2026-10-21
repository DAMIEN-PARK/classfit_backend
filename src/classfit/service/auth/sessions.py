"""세션 토큰(Design 2절). 토큰은 secrets.token_urlsafe(32) 불투명 값이고 DB 에는 sha256 hex 만 둔다.

수명은 부르는 쪽이 설정 칸(admin_session_hours · learner_session_days …)에서 읽어 넘긴다.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import auth as crud_auth


@dataclass(frozen=True)
class Principal:
    """요청 주체. type 은 admin·instructor·learner, 수강생만 course_id 가 있다(ADR-002)."""

    type: str
    id: int
    course_id: int | None = None


@dataclass(frozen=True)
class IssuedToken:
    token: str  # 평문은 응답으로 한 번만 나간다
    expires_at: datetime


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(
    session: AsyncSession, *, principal: Principal, lifetime: timedelta
) -> IssuedToken:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + lifetime
    await crud_auth.insert_session(
        session,
        token_hash=hash_token(token),
        principal_type=principal.type,
        principal_id=principal.id,
        course_id=principal.course_id,
        expires_at=expires_at,
    )
    return IssuedToken(token=token, expires_at=expires_at)


async def authenticate(session: AsyncSession, token: str) -> Principal | None:
    """살아 있는 세션의 주체. 없는 토큰·폐기·만료는 None."""
    row = await crud_auth.find_live_session(session, hash_token(token))
    if row is None:
        return None
    return Principal(
        type=row.principal_type, id=row.principal_id, course_id=row.course_id
    )


async def revoke(session: AsyncSession, token: str) -> bool:
    return await crud_auth.revoke_session(session, hash_token(token))
