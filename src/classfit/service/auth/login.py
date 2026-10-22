"""관리자·강사 로그인(Design 5절 7). 결과 값만 돌려주고 예외를 던지지 않는다.

- 판정 전에는 쓰지 않는다. 실패·잠김도 auth_attempt 1행을 같은 요청 트랜잭션에 남기고, 끝점은 problem() 을
  반환해 db() 가 그 행을 커밋하게 한다(예외로 바꾸면 롤백되어 행이 사라진다).
- 잠금 키는 (정규화한 login_id 의 sha256, 클라이언트 주소). 최근 login_lock_minutes 안 실패가
  login_lock_failures 이상이면 잠김이고, 잠긴 요청도 실패 행을 남긴다. 같은 키의 요청은 맨 앞의
  advisory 잠금(pg_advisory_xact_lock)으로 줄 세워 세기와 넣기 사이의 경쟁을 막는다.
- 없는 아이디도 DUMMY_HASH 로 같은 대조를 거친다(응답·시간이 틀린 비밀번호와 갈리지 않게).
- 잠금 판정·잠김 기록은 _lockout 한 곳이고 두 로그인이 kind 만 달리해 같이 쓴다(admin_login · instructor_login).
- 강사(T3 결정 viii·xiii): 키는 (정규화한 이메일의 sha256, 주소). 대조가 맞으면 강사 행을 잠그며 다시 읽어
  (crud.instructor.lock_instructor) 정지면 성공 시도 행만 남기고 suspended 다(자격은 맞았다). 대조 뒤에 잠그므로
  argon2 시간 동안 행 잠금을 쥐지 않는다. 대기·반려 강사도 로그인된다(결정 v). 세션 수명은 instructor_session_days.
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
from classfit.crud import instructor as crud_instructor
from classfit.schemas.enter import normalize_email
from classfit.service.auth.sessions import Principal, create_session

ATTEMPT_KIND = "admin_login"
INSTRUCTOR_ATTEMPT_KIND = "instructor_login"


@dataclass(frozen=True)
class LoginResult:
    outcome: Literal["ok", "failed", "locked", "suspended"]
    token: str | None = None
    expires_at: datetime | None = None


def subject_hash(login_id: str) -> str:
    return hashlib.sha256(crud_admin.normalize_login_id(login_id).encode()).hexdigest()


def instructor_subject_hash(email: str) -> str:
    """정규화한 이메일의 sha256 hex. 이메일은 스키마(schemas.enter.Email)를 거친 모양이어야 한다."""
    return hashlib.sha256(normalize_email(email).encode()).hexdigest()


async def _lockout(
    session: AsyncSession, settings: Settings, *, kind: str, subject: str, client: str
) -> bool:
    """잠겼으면 실패 시도 행을 남기고 True. 같은 (kind, 계정, 주소)의 요청을 트랜잭션 끝까지 줄 세운다."""
    # 세기와 넣기 사이에 동시 요청이 끼어들어 한도를 넘기지 않게
    await crud_auth.lock_attempt_key(
        session, kind=kind, subject_hash=subject, client=client
    )
    failures = await crud_auth.count_recent_failures(
        session,
        kind=kind,
        subject_hash=subject,
        client=client,
        window=timedelta(minutes=settings.login_lock_minutes),
    )
    if failures < settings.login_lock_failures:
        return False
    await crud_auth.insert_attempt(
        session, kind=kind, subject_hash=subject, client=client, ok=False
    )
    return True


async def admin_login(
    session: AsyncSession,
    settings: Settings,
    *,
    login_id: str,
    password: str,
    client: str,
) -> LoginResult:
    subject = subject_hash(login_id)
    if await _lockout(
        session, settings, kind=ATTEMPT_KIND, subject=subject, client=client
    ):
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


async def instructor_login(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
    client: str,
) -> LoginResult:
    """강사 로그인. outcome ok · failed(틀림·없는 이메일 같음) · locked · suspended."""
    subject = instructor_subject_hash(email)
    if await _lockout(
        session, settings, kind=INSTRUCTOR_ATTEMPT_KIND, subject=subject, client=client
    ):
        return LoginResult("locked")

    found = await crud_instructor.find_by_email(session, normalize_email(email))
    stored = found.password_hash if found is not None else DUMMY_HASH
    matched = await asyncio.to_thread(verify_password, stored, password)
    # 대조 뒤에 잠그고 다시 읽는다. 정지와 엇갈려도 정지 뒤 산 세션이 남지 않게(결정 viii)
    row = (
        await crud_instructor.lock_instructor(session, found.id)
        if found is not None and matched
        else None
    )
    await crud_auth.insert_attempt(
        session,
        kind=INSTRUCTOR_ATTEMPT_KIND,
        subject_hash=subject,
        client=client,
        ok=row is not None,
    )
    if row is None:
        return LoginResult("failed")
    if row.status == "suspended":
        return LoginResult("suspended")

    issued = await create_session(
        session,
        principal=Principal(type="instructor", id=row.id),
        lifetime=timedelta(days=settings.instructor_session_days),
    )
    return LoginResult("ok", token=issued.token, expires_at=issued.expires_at)
