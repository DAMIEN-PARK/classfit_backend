"""POST /v1/admin/admins: 관리자만(403), 201 + audit 1행, 모양 틀림 422."""

import hashlib
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.passwords import hash_password
from classfit.crud.admin import insert_admin
from classfit.models import AdminAccount, AuditLog, AuthSession
from tests.fixtures.courses import open_test_course

URL = "/v1/admin/admins"


async def _admin_token(
    client: httpx.AsyncClient, session: AsyncSession
) -> tuple[int, dict]:
    admin = await insert_admin(
        session, login_id="admin-a", password_hash=hash_password("pw-a-123")
    )
    r = await client.post(
        "/v1/auth/admin/login", json={"login_id": "admin-a", "password": "pw-a-123"}
    )
    return admin.id, {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_admin_create_ok_201(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, auth = await _admin_token(client, db_session)
    r = await client.post(
        URL, headers=auth, json={"login_id": " Admin-B ", "password": "x" * 12}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["login_id"] == "admin-b" and set(body) == {
        "id",
        "login_id",
        "created_at",
    }
    audits = (await db_session.execute(select(AuditLog))).scalars().all()
    assert [(a.actor, a.action, a.target_type, a.target_id) for a in audits] == [
        (f"admin:{admin_id}", "admin.create", "admin_account", str(body["id"]))
    ]


async def test_admin_create_non_admin_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    course, _ = await open_test_course(db_session)  # 0003 FK: 실제 강의 id 를 쓴다
    db_session.add(
        AuthSession(
            token_hash=hashlib.sha256(b"learner-token").hexdigest(),
            principal_type="learner",
            principal_id=1,
            course_id=course.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db_session.flush()
    r = await client.post(
        URL,
        headers={"Authorization": "Bearer learner-token"},
        json={"login_id": "admin-d", "password": "x" * 12},
    )
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/problem+json")
    assert await db_session.scalar(select(func.count()).select_from(AdminAccount)) == 0


async def test_admin_create_invalid_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await _admin_token(client, db_session)
    missing = await client.post(URL, headers=auth, json={"login_id": "admin-c"})
    assert missing.status_code == 422
    assert ["body", "password"] in [v["loc"] for v in missing.json()["violations"]]
    short = await client.post(
        URL, headers=auth, json={"login_id": "ab", "password": "short"}
    )
    assert short.status_code == 422
    assert {"login_id", "password"} == {
        v["loc"][-1] for v in short.json()["violations"]
    }
    assert await db_session.scalar(select(func.count()).select_from(AdminAccount)) == 1
