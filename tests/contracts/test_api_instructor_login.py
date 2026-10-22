"""강사 로그인(POST /v1/auth/instructor/login), T3 계획 결정 v·viii·xiii · 증명 10·14.

T1 관리자 로그인과 같은 규칙이다: 틀림·없는 이메일 같은 401 · 같은 (이메일, 주소) 10 실패 뒤 429 + Retry-After ·
실패 행은 응답 뒤에도 남는다. 정지 강사는 비밀번호가 맞아도 403 이고 그 시도 행은 ok 다. 대기·반려 강사도 로그인한다.
"""

from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import AuthAttempt, AuthSession
from tests.fixtures.courses import admin_headers
from tests.fixtures.enter import bearer
from tests.fixtures.instructors import (
    PASSWORD,
    REJECT_REASON,
    count,
    instructor_headers,
    make_instructor,
    problem_of,
)

LOGIN = "/v1/auth/instructor/login"
EMAIL = "instructor-a@example.com"


def _client_from(app: FastAPI, host: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(host, 1234))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _assert_401(r: httpx.Response) -> dict:
    body = problem_of(r, 401, "/problems/unauthorized")
    assert r.headers["www-authenticate"] == "Bearer"
    return body


async def _login_attempts(session: AsyncSession) -> list[bool]:
    rows = await session.scalars(
        select(AuthAttempt.ok)
        .where(AuthAttempt.kind == "instructor_login")
        .order_by(AuthAttempt.id)
    )
    return list(rows)


async def test_instructor_login_wrong_password_and_unknown_email_same_401(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_instructor(db_session, app.state.settings, email=EMAIL)
    wrong = await client.post(LOGIN, json={"email": EMAIL, "password": "nope-nope"})
    unknown = await client.post(
        LOGIN, json={"email": "nobody@example.com", "password": "nope-nope"}
    )
    assert _assert_401(wrong) == _assert_401(unknown)
    assert await _login_attempts(db_session) == [False, False]
    assert await count(db_session, AuthSession) == 0
    # 모양이 틀린 이메일은 시도로 세지 않는 422 다
    r = await client.post(LOGIN, json={"email": "not-an-email", "password": "x"})
    problem_of(r, 422)
    assert await _login_attempts(db_session) == [False, False]


async def test_instructor_login_lockout_same_client_429_other_client_ok(
    app: FastAPI, db_session: AsyncSession
) -> None:
    await make_instructor(db_session, app.state.settings, email=EMAIL)
    async with _client_from(app, "192.0.2.10") as attacker:
        for _ in range(10):
            _assert_401(
                await attacker.post(LOGIN, json={"email": EMAIL, "password": "nope"})
            )
        locked = await attacker.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    problem_of(locked, 429)  # 맞는 비밀번호라도 잠김
    assert locked.headers["retry-after"] == "900"
    assert await count(db_session, AuthSession) == 0
    async with _client_from(app, "192.0.2.11") as owner:
        r = await owner.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert await _login_attempts(db_session) == [False] * 11 + [True]


async def test_instructor_status_suspended_login_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email=EMAIL, status="approved"
    )
    old = await instructor_headers(db_session, iid)
    assert (await client.get("/v1/me", headers=old)).status_code == 200
    _, admin = await admin_headers(db_session)
    r = await client.post(f"/v1/admin/instructors/{iid}:suspend", headers=admin)
    assert r.status_code == 200, r.text
    _assert_401(await client.get("/v1/me", headers=old))  # 옛 토큰은 폐기됐다
    r = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    problem_of(r, 403, "/problems/instructor-suspended")
    assert await _login_attempts(db_session) == [True]  # 자격은 맞았다
    live = await count(
        db_session,
        AuthSession,
        AuthSession.principal_type == "instructor",
        AuthSession.revoked_at.is_(None),
    )
    assert live == 0
    # 대조: 틀린 비밀번호는 정지와 무관하게 401(정지 여부가 드러나지 않는다)
    _assert_401(await client.post(LOGIN, json={"email": EMAIL, "password": "nope"}))


async def test_instructor_login_rejected_200_me_shows_reason(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_instructor(
        db_session, app.state.settings, email=EMAIL, status="rejected"
    )
    r = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    me = await client.get("/v1/me", headers=bearer(r.json()["access_token"]))
    assert me.status_code == 200, me.text
    assert (me.json()["status"], me.json()["reject_reason"]) == (
        "rejected",
        REJECT_REASON,
    )


async def test_instructor_login_session_lifetime_14_days(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email=EMAIL)
    assert app.state.settings.instructor_session_days == 14
    for days in (14, 3):
        app.state.settings = Settings(instructor_session_days=days)
        r = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200, r.text
        expires_at = datetime.fromisoformat(r.json()["expires_at"])
        expected = datetime.now(UTC) + timedelta(days=days)
        assert abs(expires_at - expected) < timedelta(minutes=1), days
    rows = (
        await db_session.execute(
            select(
                AuthSession.principal_type,
                AuthSession.principal_id,
                AuthSession.course_id,
            ).order_by(AuthSession.id)
        )
    ).all()
    assert [tuple(r) for r in rows] == [("instructor", iid, None)] * 2
