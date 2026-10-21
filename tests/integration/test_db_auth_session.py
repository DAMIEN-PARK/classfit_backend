"""auth_session CHECK: 수강생 행 ⇔ course_id 있음(ADR-002). alembic check 는 CHECK 를 비교하지 않아 라이브 PG 로 잰다."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import AuthSession

CHECK_VIOLATION = "23514"


def _row(principal_type: str, course_id: int | None, token: str) -> AuthSession:
    return AuthSession(
        token_hash=token,
        principal_type=principal_type,
        principal_id=1,
        course_id=course_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def _flush_violation(session: AsyncSession, row: AuthSession) -> str:
    session.add(row)
    with pytest.raises(IntegrityError) as caught:
        await session.flush()
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


async def test_auth_session_learner_without_course_violates_check(
    db_session: AsyncSession,
) -> None:
    assert (
        await _flush_violation(db_session, _row("learner", None, "t-learner"))
        == CHECK_VIOLATION
    )


async def test_auth_session_admin_with_course_violates_check(
    db_session: AsyncSession,
) -> None:
    assert (
        await _flush_violation(db_session, _row("admin", 7, "t-admin"))
        == CHECK_VIOLATION
    )
