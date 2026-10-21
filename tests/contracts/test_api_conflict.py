"""flush_or_conflict: 유일 위반(23505)만 409, CHECK 위반은 500. 409 로 끝난 요청의 outbox 는 0행."""

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict
from classfit.core.passwords import hash_password
from classfit.crud.admin import insert_admin
from classfit.models import AdminAccount, AuthSession, MailOutbox


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return (
        await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    )


async def test_flush_or_conflict_unique_is_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await insert_admin(
        db_session, login_id="admin-a", password_hash=hash_password("pw-a-123")
    )
    login = await client.post(
        "/v1/auth/admin/login", json={"login_id": "admin-a", "password": "pw-a-123"}
    )
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    first = await client.post(
        "/v1/admin/admins",
        headers=auth,
        json={"login_id": "admin-b", "password": "x" * 12},
    )
    again = await client.post(
        "/v1/admin/admins",
        headers=auth,
        json={"login_id": "ADMIN-B", "password": "y" * 12},
    )
    assert first.status_code == 201
    assert again.status_code == 409
    assert again.headers["content-type"].startswith("application/problem+json")
    assert again.json()["type"] == "/problems/conflict"
    assert (
        await _count(db_session, AdminAccount, AdminAccount.login_id == "admin-b") == 1
    )


async def test_flush_or_conflict_check_is_500(
    client_noraise: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    r = await client_noraise.post("/v1/_probe/check-violation")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    assert (
        "learner_course" not in r.text and "CHECK" not in r.text
    )  # 내부 메시지를 흘리지 않는다
    assert await _count(db_session, AuthSession) == 0


async def test_flush_or_conflict_keeps_outer_transaction(
    db_session: AsyncSession,
) -> None:
    await insert_admin(db_session, login_id="admin-a", password_hash="h")
    with pytest.raises(Conflict):
        await insert_admin(db_session, login_id="Admin-A", password_hash="h")
    await insert_admin(
        db_session, login_id="admin-b", password_hash="h"
    )  # 바깥 트랜잭션은 산다
    assert await _count(db_session, AdminAccount) == 2


async def test_outbox_rolled_back_on_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await insert_admin(db_session, login_id="admin-a", password_hash="h")
    r = await client.post(
        "/v1/_probe/outbox-then-conflict", params={"login_id": "admin-a"}
    )
    assert r.status_code == 409
    assert await _count(db_session, MailOutbox) == 0
