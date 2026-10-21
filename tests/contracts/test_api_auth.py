"""관리자 로그인·Bearer·잠금(Design 5절 7 · 부록 A T1). 실패 시도는 401 응답 뒤에도 남는다."""

import hashlib
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.passwords import hash_password
from classfit.crud.admin import insert_admin
from classfit.models import AdminAccount, AuthAttempt, AuthSession

PASSWORD = "correct-horse-battery"
LOGIN = "/v1/auth/admin/login"


async def _admin(session: AsyncSession, login_id: str = "admin-a") -> AdminAccount:
    return await insert_admin(
        session, login_id=login_id, password_hash=hash_password(PASSWORD)
    )


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return (
        await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    )


def _client_from(app: FastAPI, host: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(host, 1234))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _assert_401(r: httpx.Response) -> None:
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_admin_login_wrong_password_and_unknown_id_same_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _admin(db_session)
    wrong = await client.post(LOGIN, json={"login_id": "admin-a", "password": "nope"})
    unknown = await client.post(LOGIN, json={"login_id": "nobody", "password": "nope"})
    _assert_401(wrong)
    _assert_401(unknown)
    assert wrong.json() == unknown.json()


async def test_admin_login_ok_returns_opaque_token(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _admin(db_session)
    r = await client.post(LOGIN, json={"login_id": " Admin-A ", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_at"]
    token = body["access_token"]
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert await _count(db_session, AuthSession, AuthSession.token_hash == digest) == 1
    assert await _count(db_session, AuthSession, AuthSession.token_hash == token) == 0
    ok = await _count(db_session, AuthAttempt, AuthAttempt.ok.is_(True))
    assert ok == 1


async def test_admin_login_missing_or_malformed_bearer_401(
    client: httpx.AsyncClient,
) -> None:
    _assert_401(await client.post("/v1/auth/logout"))
    malformed: tuple[str | bytes, ...] = (
        "Basic abc",
        "Bearer",
        "Bearer a b",
        "Bearer " + "x" * 300,
        "Bearer ünï".encode(),  # httpx 는 비 ASCII 헤더를 bytes 로만 보낸다
    )
    for header in malformed:
        _assert_401(
            await client.post("/v1/auth/logout", headers={"Authorization": header})
        )
    _assert_401(
        await client.post("/v1/auth/logout", headers={"Authorization": "Bearer nope"})
    )


async def test_admin_login_revoked_token_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _admin(db_session)
    token = (
        await client.post(LOGIN, json={"login_id": "admin-a", "password": PASSWORD})
    ).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert (await client.post("/v1/auth/logout", headers=auth)).status_code == 204
    _assert_401(await client.post("/v1/auth/logout", headers=auth))
    _assert_401(
        await client.post(
            "/v1/admin/admins",
            headers=auth,
            json={"login_id": "admin-z", "password": "x" * 12},
        )
    )


async def test_admin_login_expired_token_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _admin(db_session)
    now = datetime.now(UTC)
    for token, expires_at in (
        ("live-token", now + timedelta(hours=1)),
        ("old-token", now - timedelta(seconds=1)),
    ):
        db_session.add(
            AuthSession(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                principal_type="admin",
                principal_id=admin.id,
                expires_at=expires_at,
            )
        )
    await db_session.flush()
    _assert_401(
        await client.post(
            "/v1/auth/logout", headers={"Authorization": "Bearer old-token"}
        )
    )
    live = await client.post(
        "/v1/auth/logout", headers={"Authorization": "Bearer live-token"}
    )
    assert live.status_code == 204  # 대조: 같은 모양의 산 토큰은 통과


async def test_auth_attempt_row_survives_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _admin(db_session)
    r = await client.post(LOGIN, json={"login_id": "admin-a", "password": "nope"})
    _assert_401(r)
    rows = (await db_session.execute(select(AuthAttempt.kind, AuthAttempt.ok))).all()
    assert [tuple(x) for x in rows] == [("admin_login", False)]
    assert await _count(db_session, AdminAccount) == 1  # 판정 전 다른 쓰기 없음
    assert await _count(db_session, AuthSession) == 0


async def test_auth_lockout_same_client_429_after_10_failures(
    app: FastAPI, db_session: AsyncSession
) -> None:
    await _admin(db_session)
    async with _client_from(app, "192.0.2.10") as c:
        for _ in range(10):
            _assert_401(
                await c.post(LOGIN, json={"login_id": "admin-a", "password": "nope"})
            )
        locked = await c.post(LOGIN, json={"login_id": "admin-a", "password": PASSWORD})
    assert locked.status_code == 429  # 맞는 비밀번호라도 잠김
    assert locked.headers["content-type"].startswith("application/problem+json")
    assert int(locked.headers["retry-after"]) > 0
    assert await _count(db_session, AuthAttempt, AuthAttempt.ok.is_(False)) == 11
    assert await _count(db_session, AuthSession) == 0


async def test_auth_lockout_other_client_not_locked(
    app: FastAPI, db_session: AsyncSession
) -> None:
    await _admin(db_session)
    async with _client_from(app, "192.0.2.10") as attacker:
        for _ in range(10):
            _assert_401(
                await attacker.post(
                    LOGIN, json={"login_id": "admin-a", "password": "nope"}
                )
            )
        assert (
            await attacker.post(
                LOGIN, json={"login_id": "admin-a", "password": PASSWORD}
            )
        ).status_code == 429
    async with _client_from(app, "192.0.2.11") as owner:
        r = await owner.post(LOGIN, json={"login_id": "admin-a", "password": PASSWORD})
    assert r.status_code == 200
