"""관리자 로그인(Design 5절 7). 결과 값만 돌려주고 예외를 던지지 않는다.

- 판정 전에는 쓰지 않는다. 실패·잠김도 auth_attempt 1행을 같은 요청 트랜잭션에 남기고, 끝점은 problem() 을
  반환해 db() 가 그 행을 커밋하게 한다(예외로 바꾸면 롤백되어 행이 사라진다).
- 잠금 키는 (정규화한 login_id 의 sha256, 클라이언트 주소). 최근 login_lock_minutes 안 실패가
  login_lock_failures 이상이면 잠김이고, 잠긴 요청도 실패 행을 남긴다.
- 없는 아이디도 DUMMY_HASH 로 같은 대조를 거친다(응답·시간이 틀린 비밀번호와 갈리지 않게).
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.core.passwords import DUMMY_HASH, verify_password
from classfit.crud import admin as crud_admin
from classfit.crud import auth as crud_auth
from classfit.service.auth.sessions import Principal, create_session

ATTEMPT_KIND = "admin_login"


@dataclass(frozen=True)
class LoginResult:
    outcome: Literal["ok", "failed", "locked"]
    token: str | None = None
    expires_at: datetime | None = None


def subject_hash(login_id: str) -> str:
    return hashlib.sha256(crud_admin.normalize_login_id(login_id).encode()).hexdigest()


async def admin_login(
    session: AsyncSession,
    settings: Settings,
    *,
    login_id: str,
    password: str,
    client: str,
) -> LoginResult:
    subject = subject_hash(login_id)
    failures = await crud_auth.count_recent_failures(
        session,
        kind=ATTEMPT_KIND,
        subject_hash=subject,
        client=client,
        window=timedelta(minutes=settings.login_lock_minutes),
    )
    if failures >= settings.login_lock_failures:
        await crud_auth.insert_attempt(
            session, kind=ATTEMPT_KIND, subject_hash=subject, client=client, ok=False
        )
        return LoginResult("locked")

    admin = await crud_admin.get_admin_by_login(session, login_id)
    stored = admin.password_hash if admin is not None else DUMMY_HASH
    matched = await asyncio.to_thread(verify_password, stored, password)
    ok = admin is not None and matched
    await crud_auth.insert_attempt(
        session, kind=ATTEMPT_KIND, subject_hash=subject, client=client, ok=ok
    )
    if admin is None or not ok:
        return LoginResult("failed")

    issued = await create_session(
        session,
        principal=Principal(type="admin", id=admin.id),
        lifetime=timedelta(hours=settings.admin_session_hours),
    )
    return LoginResult("ok", token=issued.token, expires_at=issued.expires_at)
