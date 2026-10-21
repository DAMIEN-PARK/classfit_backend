"""시험용 강의와 주체 토큰. 시험도 강의를 단일 진입점 open_course() 로 만든다(Design 5절 13).

기본값은 A사 · 시험 강의 · 2026-11-02(월)부터 평일 4일(끝 날 2026-11-05) · 13:00~17:00 이다.
over 로 CourseOpenIn 칸을 바꾼다. day_count=0 이면 end_on 도 준다.
admin_headers·learner_headers 는 auth_session 행을 직접 넣어 Bearer 헤더를 만든다(로그인·argon2 를 건너뛴다).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.admin import insert_admin
from classfit.models import AuthSession, Course, InviteCode
from classfit.schemas.course import CourseOpenIn
from classfit.service.courses.open import open_course

DEFAULTS: dict[str, Any] = {
    "start": "blank",
    "title": "시험 강의",
    "client_name": "A사",
    "method": "집체",
    "hours_per_person": 16,
    "start_on": date(2026, 11, 2),
    "day_count": 4,
    "day_start": "13:00",
    "day_end": "17:00",
}


async def open_test_course(
    session: AsyncSession, **over: Any
) -> tuple[Course, InviteCode]:
    body = CourseOpenIn.model_validate({**DEFAULTS, **over})
    return await open_course(session, body, actor="system", invite_expiry_days=30)


async def _bearer(
    session: AsyncSession,
    token: str,
    principal_type: str,
    principal_id: int,
    course_id: int | None,
) -> dict[str, str]:
    session.add(
        AuthSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            principal_type=principal_type,
            principal_id=principal_id,
            course_id=course_id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await session.flush()
    return {"Authorization": f"Bearer {token}"}


async def admin_headers(session: AsyncSession) -> tuple[int, dict[str, str]]:
    """(관리자 id, 헤더)."""
    admin = await insert_admin(session, login_id="admin-a", password_hash="unused")
    return admin.id, await _bearer(
        session, f"admin-token-{admin.id}", "admin", admin.id, None
    )


async def learner_headers(session: AsyncSession, course_id: int) -> dict[str, str]:
    return await _bearer(session, f"learner-token-{course_id}", "learner", 1, course_id)
