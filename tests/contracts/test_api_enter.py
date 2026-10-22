"""입장 끝점(POST /v1/enter/lookup · POST /v1/enter): 기획안 P3 표 · 재발급 · 교차 강의 · 이름 분리(T2b 계획 증명 1~13).

픽스처 강의는 2026-11-02(월) ~ 2026-11-05 · 코드 만료일 2026-12-05 다. 오늘은 app.dependency_overrides[today] 로 준다.
E-10: 접두 test_p3_ · test_reissue_ · test_cross_course_ · test_enrollment_name_ 는 이 파일의 13건에만 쓰고 parametrize 하지 않는다.
"""

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.core.config import Settings
from classfit.models import AuthSession, Enrollment, Learner
from tests.fixtures.courses import admin_headers, open_test_course
from tests.fixtures.enter import (
    PERSONAL_KEYS,
    add_pdf,
    add_session,
    bearer,
    enter_learner,
    json_keys,
)

LOOKUP = "/v1/enter/lookup"
ADMIN = "/v1/admin/courses"
PREP = date(2026, 10, 22)  # 시작 전
RUNNING = date(2026, 11, 3)  # 진행 중
ENDED = date(2026, 11, 6)  # 종료일 다음 날
NOTICE = "준비 중인 강의입니다. 시작일 2026-11-02"


def _set_today(app: FastAPI, d: date) -> None:
    app.dependency_overrides[today] = lambda: d


def _problem(r: httpx.Response, status: int, type_: str | None = None) -> dict:
    assert r.status_code == status, (r.status_code, r.text)
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    if type_ is not None:
        assert body["type"] == type_, body
    return body


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return (
        await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    )


def _missing_code(*taken: str) -> str:
    """알파벳 안의, 어느 강의에도 없는 코드."""
    for c in "ZYXWVU":
        if c * 6 not in taken:
            return c * 6
    raise AssertionError("빈 코드를 못 찾았다")


def _portal(course_id: int) -> str:
    return f"/v1/learner/courses/{course_id}/portal"


async def test_p3_active(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    course, code = await open_test_course(db_session)
    look = await client.post(LOOKUP, json={"code": code.code.lower()})
    assert look.status_code == 200, look.text
    assert look.json() == {
        "course": {
            "title": "시험 강의",
            "start_on": "2026-11-02",
            "end_on": "2026-11-05",
            "status": "running",
        },
        "state": "active",
        "accepts_new": True,
        "notice": None,
    }
    before = datetime.now(UTC)
    r = await enter_learner(
        client,
        f"  {code.code.lower()} ",
        " Learner-A@Example.com ",
        "김가명",
        dept="교육팀",
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert (body["course_id"], body["name"], body["reentered"], body["notice"]) == (
        course.id,
        "김가명",
        False,
        None,
    )
    lifetime = datetime.fromisoformat(body["expires_at"]) - before
    assert timedelta(hours=23, minutes=59) < lifetime < timedelta(days=1, minutes=1)
    emails = (await db_session.scalars(select(Learner.email))).all()
    assert list(emails) == ["learner-a@example.com"]
    rows = (
        await db_session.execute(
            select(Enrollment.course_id, Enrollment.name, Enrollment.dept)
        )
    ).all()
    assert [tuple(x) for x in rows] == [(course.id, "김가명", "교육팀")]
    portal = await client.get(_portal(course.id), headers=bearer(body["access_token"]))
    assert portal.status_code == 200, portal.text


async def test_p3_preparing(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, PREP)
    _, code = await open_test_course(db_session)
    look = await client.post(LOOKUP, json={"code": code.code})
    assert look.status_code == 200, look.text
    assert (look.json()["state"], look.json()["accepts_new"]) == ("preparing", True)
    assert look.json()["notice"] == NOTICE
    assert look.json()["course"]["status"] == "prep"
    r = await enter_learner(client, code.code, "kim@example.com", "김가명")
    assert r.status_code == 201, r.text
    assert r.json()["notice"] == NOTICE


async def test_p3_ended(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    course, code = await open_test_course(db_session)
    first = await enter_learner(client, code.code, "kim@example.com", "김가명")
    assert first.status_code == 201, first.text
    _set_today(app, ENDED)
    look = await client.post(LOOKUP, json={"code": code.code})
    assert look.status_code == 200, look.text
    assert (look.json()["state"], look.json()["accepts_new"]) == ("ended", False)
    assert look.json()["course"]["status"] == "ended"
    _problem(
        await enter_learner(client, code.code, "lee@example.com", "이가명"),
        409,
        "/problems/course-ended",
    )
    assert await _count(db_session, Enrollment, Enrollment.course_id == course.id) == 1
    again = await enter_learner(client, code.code, "kim@example.com")
    assert again.status_code == 200, again.text
    assert (again.json()["reentered"], again.json()["name"]) == (True, "김가명")


async def test_p3_expired(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    assert (
        await enter_learner(client, code.code, "kim@example.com", "김가명")
    ).status_code == 201
    r = await client.patch(
        f"{ADMIN}/{course.id}/invite-code",
        headers=auth,
        json={"expires_on": "2026-11-02"},
    )
    assert r.status_code == 200 and r.json()["state"] == "expired", r.text
    look = await client.post(LOOKUP, json={"code": code.code})
    assert (look.json()["state"], look.json()["accepts_new"]) == ("expired", False)
    _problem(
        await enter_learner(client, code.code, "lee@example.com", "이가명"),
        409,
        "/problems/invite-code-expired",
    )
    assert (
        await enter_learner(client, code.code, "kim@example.com")
    ).status_code == 200


async def test_p3_paused(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    assert (
        await enter_learner(client, code.code, "kim@example.com", "김가명")
    ).status_code == 201
    r = await client.post(f"{ADMIN}/{course.id}/invite-code:pause", headers=auth)
    assert r.status_code == 200, r.text
    look = await client.post(LOOKUP, json={"code": code.code})
    assert (look.json()["state"], look.json()["accepts_new"]) == ("paused", False)
    _problem(
        await enter_learner(client, code.code, "lee@example.com", "이가명"),
        409,
        "/problems/invite-code-paused",
    )
    assert (
        await enter_learner(client, code.code, "kim@example.com")
    ).status_code == 200


async def test_p3_full(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    r = await client.patch(
        f"{ADMIN}/{course.id}/invite-code", headers=auth, json={"max_seats": 1}
    )
    assert r.status_code == 200, r.text
    assert (
        await enter_learner(client, code.code, "kim@example.com", "김가명")
    ).status_code == 201
    _problem(
        await enter_learner(client, code.code, "lee@example.com", "이가명"),
        409,
        "/problems/course-full",
    )
    look = await client.post(LOOKUP, json={"code": code.code})
    assert (look.json()["state"], look.json()["accepts_new"]) == ("full", False)
    assert await _count(db_session, Enrollment, Enrollment.course_id == course.id) == 1
    again = await enter_learner(client, code.code, "kim@example.com")
    assert again.status_code == 200 and again.json()["reentered"] is True, again.text


async def test_p3_not_found(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, code = await open_test_course(db_session)
    missing = _missing_code(code.code)
    _problem(
        await client.post(LOOKUP, json={"code": missing}),
        404,
        "/problems/invite-code-not-found",
    )
    _problem(
        await enter_learner(client, missing, "kim@example.com", "김가명"),
        404,
        "/problems/invite-code-not-found",
    )
    assert await _count(db_session, Learner) == 0


async def test_p3_existing_email(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    course, code = await open_test_course(db_session)
    first = await enter_learner(client, code.code, "kim@example.com", "김가명")
    assert first.status_code == 201, first.text
    again = await enter_learner(
        client, code.code, "  KIM@Example.COM ", "다른이름", dept="X"
    )
    assert again.status_code == 200, again.text
    assert (again.json()["reentered"], again.json()["name"]) == (True, "김가명")
    assert again.json()["access_token"] != first.json()["access_token"]
    learner_id = await db_session.scalar(select(Learner.id))
    rows = (await db_session.execute(select(Enrollment.name, Enrollment.dept))).all()
    assert [tuple(x) for x in rows] == [
        ("김가명", None)
    ]  # 재입장은 이름·부서를 덮지 않는다
    sessions = await _count(
        db_session,
        AuthSession,
        AuthSession.principal_type == "learner",
        AuthSession.principal_id == learner_id,
        AuthSession.course_id == course.id,
    )
    assert sessions == 2


async def test_p3_confusable(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    await open_test_course(db_session)
    for raw in ("AB0CDE", "abcdo1"):
        _problem(
            await client.post(LOOKUP, json={"code": raw}),
            422,
            "/problems/invite-code-confusable",
        )
        _problem(
            await enter_learner(client, raw, "kim@example.com", "김가명"),
            422,
            "/problems/invite-code-confusable",
        )


async def test_reissue_old_code_not_found(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    old = code.code
    assert (
        await enter_learner(client, old, "kim@example.com", "김가명")
    ).status_code == 201
    r = await client.post(f"{ADMIN}/{course.id}/invite-code:reissue", headers=auth)
    assert r.status_code == 200, r.text
    missing = _missing_code(old, r.json()["code"])

    def _same(a: httpx.Response, b: httpx.Response) -> None:
        assert a.status_code == b.status_code == 404
        body_a, body_b = a.json(), b.json()
        body_a.pop("instance")
        body_b.pop("instance")
        assert body_a == body_b
        assert body_a["type"] == "/problems/invite-code-not-found"

    _same(
        await client.post(LOOKUP, json={"code": old}),
        await client.post(LOOKUP, json={"code": missing}),
    )
    _same(
        await enter_learner(client, old, "lee@example.com", "이가명"),
        await enter_learner(client, missing, "lee@example.com", "이가명"),
    )
    # 기존 등록자도 옛 코드로는 못 들어온다(replaced 는 재입장 판정보다 앞)
    _same(
        await enter_learner(client, old, "kim@example.com"),
        await enter_learner(client, missing, "kim@example.com"),
    )


async def test_reissue_keeps_sessions(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    first = await enter_learner(client, code.code, "kim@example.com", "김가명")
    assert first.status_code == 201, first.text
    r = await client.post(f"{ADMIN}/{course.id}/invite-code:reissue", headers=auth)
    assert r.status_code == 200, r.text
    portal = await client.get(
        _portal(course.id), headers=bearer(first.json()["access_token"])
    )
    assert portal.status_code == 200, portal.text
    again = await enter_learner(client, r.json()["code"], "kim@example.com")
    assert again.status_code == 200 and again.json()["reentered"] is True, again.text


async def test_cross_course_portal_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    app.state.settings = Settings(file_store_root=tmp_path)
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course_a, _ = await open_test_course(db_session, title="A 강의")
    course_b, code_b = await open_test_course(
        db_session, title="B 강의", client_name="B사"
    )
    sid = await add_session(client, auth, course_a.id, day_no=1, slot=1, is_open=True)
    up = await add_pdf(client, auth, sid)
    assert up.status_code == 201, up.text
    href = up.json()["href"]
    entered = await enter_learner(client, code_b.code, "lee@example.com", "이가명")
    assert entered.status_code == 201, entered.text
    as_b = bearer(entered.json()["access_token"])

    _problem(await client.get(_portal(course_a.id), headers=as_b), 403)
    _problem(
        await client.get(f"/v1/learner/sessions/{sid}/attachments", headers=as_b), 403
    )
    _problem(await client.get(href, headers=as_b), 403)
    # 자기 강의는 열리고, 같은 href 는 관리자에게 열린다
    assert (await client.get(_portal(course_b.id), headers=as_b)).status_code == 200
    assert (await client.get(href, headers=auth)).status_code == 200


async def test_enrollment_name_isolated(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course_a, code_a = await open_test_course(db_session, title="A 강의")
    course_b, code_b = await open_test_course(db_session, title="B 강의")
    assert (
        await enter_learner(client, code_a.code, "Kim@Example.com", "김가명")
    ).status_code == 201
    in_b = await enter_learner(
        client, code_b.code, "kim@example.com", "이가명", dept="영업"
    )
    assert in_b.status_code == 201 and in_b.json()["name"] == "이가명", in_b.text

    async def roster(course_id: int) -> list[tuple[str, str | None, str]]:
        r = await client.get(f"{ADMIN}/{course_id}/enrollments", headers=auth)
        assert r.status_code == 200, r.text
        return [(e["name"], e["dept"], e["email"]) for e in r.json()["items"]]

    assert await roster(course_a.id) == [("김가명", None, "kim@example.com")]
    assert await roster(course_b.id) == [("이가명", "영업", "kim@example.com")]
    assert await _count(db_session, Learner) == 1
    again = await enter_learner(client, code_a.code, "kim@example.com")
    assert again.json()["name"] == "김가명"


async def test_enter_new_email_requires_name_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, code = await open_test_course(db_session)
    for name in (None, "   "):
        body = _problem(
            await enter_learner(client, code.code, "new@example.com", name), 422
        )
        assert [v["loc"] for v in body["violations"]] == [["body", "name"]]
    assert await _count(db_session, Learner) == 0
    assert await _count(db_session, Enrollment) == 0


async def test_enter_malformed_code_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    await open_test_course(db_session)
    for raw in ("ABCDE", "ABCDEFG", "AB-CDE", "AB CDE", "", "   "):
        _problem(
            await client.post(LOOKUP, json={"code": raw}),
            422,
            "/problems/invite-code-malformed",
        )
        _problem(
            await enter_learner(client, raw, "kim@example.com", "김가명"),
            422,
            "/problems/invite-code-malformed",
        )


async def test_enter_invalid_email_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, code = await open_test_course(db_session)
    bad = (
        "not-an-email",
        "kim@example",
        "@example.com",
        "kim@@example.com",
        "kim lee@example.com",
        "kim@exa\x00mple.com",
        "k" * 243 + "@example.com",  # 255자
    )
    for email in bad:
        body = _problem(await enter_learner(client, code.code, email, "김가명"), 422)
        assert [v["loc"] for v in body["violations"]] == [["body", "email"]], email
    assert await _count(db_session, Learner) == 0
    # 254자는 받는다
    ok = await enter_learner(client, code.code, "k" * 242 + "@example.com", "김가명")
    assert ok.status_code == 201, ok.text


async def test_enter_session_lifetime_one_day(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    course, code = await open_test_course(db_session)
    before = datetime.now(UTC)
    r = await enter_learner(client, code.code, "kim@example.com", "김가명")
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    row = await db_session.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    assert row is not None
    assert (row.principal_type, row.course_id) == ("learner", course.id)
    assert row.expires_at == datetime.fromisoformat(r.json()["expires_at"])
    assert (
        timedelta(hours=23, minutes=59)
        < row.expires_at - before
        < timedelta(days=1, minutes=1)
    )
    # 수명은 설정 칸 하나로 바뀐다(ADR-002 결정 5)
    app.state.settings = Settings(learner_session_days=2)
    again = await enter_learner(client, code.code, "kim@example.com")
    assert again.status_code == 200, again.text
    lifetime = datetime.fromisoformat(again.json()["expires_at"]) - before
    assert timedelta(days=1, hours=23) < lifetime < timedelta(days=2, minutes=1)


async def test_enter_lookup_hides_personal_fields(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, code = await open_test_course(db_session)
    r = await enter_learner(
        client, code.code, "kim@example.com", "김가명", dept="교육팀"
    )
    assert r.status_code == 201, r.text
    look = await client.post(LOOKUP, json={"code": code.code})
    assert look.status_code == 200, look.text
    assert json_keys(look.json()) & PERSONAL_KEYS == set()
    for secret in ("김가명", "kim@example.com", "교육팀"):
        assert secret not in look.text
