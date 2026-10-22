"""관리자 수강생 명단(GET /v1/admin/courses/{id}/enrollments)과 강의 DELETE 의 수강생·세션 행 처리(T2b 계획 결정 xi).

- 명단은 키셋 커서 {items, next_cursor, has_more}, (created_at, id) 내림차순이다. 깨진 커서는 422(loc query.cursor).
- 수강생이 있는 강의 DELETE 는 409 /problems/conflict, 행은 그대로다.
- 수강생 없는 강의의 auth_session 행(살아 있는·폐기·만료)은 DELETE 가 같은 트랜잭션에서 먼저 지운다(FK NO ACTION, 500 아님).
"""

import hashlib
from datetime import UTC, date, datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.models import AuditLog, AuthSession, Course, Enrollment
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.enter import enter_learner

ADMIN = "/v1/admin/courses"
RUNNING = date(2026, 11, 3)


def _set_today(app: FastAPI, d: date) -> None:
    app.dependency_overrides[today] = lambda: d


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return (
        await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    )


async def test_admin_enrollments_list_keyset(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    _, other_code = await open_test_course(db_session, title="다른 강의")
    for email, name in (
        ("a@example.com", "가"),
        ("b@example.com", "나"),
        ("c@example.com", "다"),
    ):
        r = await enter_learner(client, code.code, email, name, dept="교육팀")
        assert r.status_code == 201, r.text
    assert (
        await enter_learner(client, other_code.code, "z@example.com", "하")
    ).status_code == 201

    url = f"{ADMIN}/{course.id}/enrollments"
    first = await client.get(url, headers=auth, params={"limit": 2})
    assert first.status_code == 200, first.text
    page = first.json()
    assert page["has_more"] is True and page["next_cursor"]
    assert [(e["name"], e["email"], e["dept"]) for e in page["items"]] == [
        ("다", "c@example.com", "교육팀"),
        ("나", "b@example.com", "교육팀"),
    ]
    assert set(page["items"][0]) == {"id", "name", "dept", "email", "enrolled_at"}
    rest = (
        await client.get(
            url, headers=auth, params={"limit": 2, "cursor": page["next_cursor"]}
        )
    ).json()
    assert (rest["has_more"], rest["next_cursor"]) == (False, None)
    assert [e["name"] for e in rest["items"]] == ["가"]  # 다른 강의 수강생은 없다
    missing = await client.get(f"{ADMIN}/999999999/enrollments", headers=auth)
    assert missing.status_code == 404, missing.text


async def test_admin_enrollments_bad_cursor_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    r = await client.get(
        f"{ADMIN}/{course.id}/enrollments", headers=auth, params={"cursor": "깨진-커서"}
    )
    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    assert [v["loc"] for v in r.json()["violations"]] == [["query", "cursor"]]


async def test_courses_delete_with_enrollments_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    assert (
        await enter_learner(client, code.code, "kim@example.com", "김가명")
    ).status_code == 201
    r = await client.delete(f"{ADMIN}/{course.id}", headers=auth)
    assert r.status_code == 409, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "/problems/conflict"
    assert await _count(db_session, Course, Course.id == course.id) == 1
    assert await _count(db_session, Enrollment, Enrollment.course_id == course.id) == 1
    assert (
        await _count(db_session, AuthSession, AuthSession.course_id == course.id) == 1
    )
    assert await _count(db_session, AuditLog, AuditLog.action == "course.delete") == 0


async def test_courses_delete_clears_course_sessions(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="남는 강의")
    await learner_headers(
        db_session, course.id
    )  # 살아 있는 세션(가짜 수강생 principal_id 1)
    await learner_headers(db_session, other.id)
    now = datetime.now(UTC)
    for name, revoked, expires in (
        ("revoked", now, now + timedelta(hours=1)),
        ("expired", None, now - timedelta(hours=1)),
    ):
        db_session.add(
            AuthSession(
                token_hash=hashlib.sha256(f"{name}-{course.id}".encode()).hexdigest(),
                principal_type="learner",
                principal_id=1,
                course_id=course.id,
                expires_at=expires,
                revoked_at=revoked,
            )
        )
    await db_session.flush()
    assert (
        await _count(db_session, AuthSession, AuthSession.course_id == course.id) == 3
    )

    r = await client.delete(f"{ADMIN}/{course.id}", headers=auth)
    assert r.status_code == 204, r.text
    assert (
        await _count(db_session, AuthSession, AuthSession.course_id == course.id) == 0
    )
    assert await _count(db_session, Course, Course.id == course.id) == 0
    assert await _count(db_session, AuthSession, AuthSession.course_id == other.id) == 1
    assert await _count(db_session, AuditLog, AuditLog.action == "course.delete") == 1
