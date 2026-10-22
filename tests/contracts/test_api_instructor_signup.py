"""강사 가입(POST /v1/instructors/email-codes · POST /v1/instructors), T3 계획 결정 i·ii·iii·iv·xi·xvi · 증명 1~6.

코드는 요청 끝점이 만들지 않는다. 시험도 운영처럼 scripts.outbox_preview.run(["--apply"]) 의 stdout 에서 받는다
(시험 연결에 묶은 session_factory 를 넘긴다). 한 시험은 바깥 트랜잭션 하나라 DB now() 가 시험 내내 같다.
코드 실패 셋(틀림 422 · 만료 410 · 초과 429)은 problem() 반환이라 tries·auth_attempt 행이 응답 뒤에도 남는다.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from classfit.database.session import make_session_factory
from classfit.models import (
    AuthAttempt,
    EmailVerification,
    Instructor,
    InstructorTag,
    MailOutbox,
    Tag,
)
from classfit.service.auth.email_code import issue_email_code
from scripts import outbox_preview
from tests.fixtures.enter import bearer
from tests.fixtures.instructors import (
    DOCUMENT_TYPES,
    PASSWORD,
    count,
    locs,
    make_instructor,
    problem_of,
)

CODES = "/v1/instructors/email-codes"
SIGNUP = "/v1/instructors"
LOGIN = "/v1/auth/instructor/login"
EMAIL = "instructor-a@example.com"


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


def _body(email: str, code: str, **over: object) -> dict[str, object]:
    return {
        "email": email,
        "code": code,
        "password": PASSWORD,
        "name": "강사A",
        "phone": "010-0000-0000",
        "org": None,
        "tags": ["프롬프트"],
        "terms_agreed": True,
        "privacy_agreed": True,
        **over,
    }


async def _send_codes(
    factory: async_sessionmaker[AsyncSession], capsys: pytest.CaptureFixture[str]
) -> dict[str, str]:
    """안 보낸 outbox 를 --apply 로 발송(해시 저장)하고 {받는 이메일: 코드}."""
    capsys.readouterr()
    assert await outbox_preview.run(["--apply"], factory) == 0
    out = json.loads(capsys.readouterr().out)
    codes: dict[str, str] = {}
    for m in out["messages"]:
        if m["kind"] == "email_code":
            found = re.search(r"\d{6}", m["body"])
            assert found is not None, m
            codes[m["to"]] = found.group(0)
    return codes


async def _code_for(
    client: httpx.AsyncClient,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
    email: str = EMAIL,
) -> str:
    r = await client.post(CODES, json={"email": email})
    assert r.status_code == 202, r.text
    return (await _send_codes(factory, capsys))[email.strip().lower()]


def _other(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


async def _attempts(session: AsyncSession) -> list[tuple[str, bool]]:
    rows = await session.execute(
        select(AuthAttempt.kind, AuthAttempt.ok).order_by(AuthAttempt.id)
    )
    return [(r.kind, r.ok) for r in rows]


async def test_instructor_email_code_request_enqueues_outbox_without_plaintext(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    r = await client.post(CODES, json={"email": " Instructor-A@Example.com "})
    assert r.status_code == 202, r.text
    assert r.json() == {"email": EMAIL}
    assert re.search(r"\d{6}", r.text) is None
    rows = (
        await db_session.execute(
            select(
                MailOutbox.kind, MailOutbox.params, MailOutbox.to, MailOutbox.sent_at
            )
        )
    ).all()
    assert len(rows) == 1
    kind, params, to, sent_at = rows[0]
    assert (kind, set(params), to, sent_at) == (
        "email_code",
        {"verification_id"},
        EMAIL,
        None,
    )
    assert re.search(r"\d{6}", json.dumps(params)) is None
    requests = (
        await db_session.execute(
            select(
                EmailVerification.id,
                EmailVerification.email,
                EmailVerification.code_hash,
                EmailVerification.consumed_at,
            )
        )
    ).all()
    assert [tuple(v) for v in requests] == [
        (params["verification_id"], EMAIL, None, None)
    ]
    assert await count(db_session, Instructor) == 0


async def test_instructor_email_code_request_registered_email_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_instructor(db_session, app.state.settings, email=EMAIL)
    queued = await count(db_session, MailOutbox)
    r = await client.post(CODES, json={"email": "INSTRUCTOR-A@example.com"})
    problem_of(r, 409, "/problems/conflict")
    assert await count(db_session, MailOutbox) == queued  # 새 outbox 없음
    assert await count(db_session, EmailVerification) == 1


async def test_instructor_email_code_signup_pending_then_login_200(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await _code_for(client, factory, capsys, "Instructor-A@example.com")
    r = await client.post(SIGNUP, json=_body(" Instructor-A@Example.com", code))
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["status"], body["email"], body["org"], body["reject_reason"]) == (
        "pending",
        EMAIL,
        None,
        None,
    )
    assert [t["name"] for t in body["tags"]] == ["프롬프트"]
    assert body["terms_version"] == app.state.settings.terms_version
    assert [d["type_id"] for d in body["documents"]] == DOCUMENT_TYPES
    assert all(d["href"] is None for d in body["documents"])
    request = (
        await db_session.execute(
            select(EmailVerification.consumed_at, EmailVerification.instructor_id)
        )
    ).one()
    assert request.consumed_at is not None and request.instructor_id == body["id"]
    assert await _attempts(db_session) == [("email_code", True)]

    login = await client.post(
        LOGIN, json={"email": "INSTRUCTOR-A@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    issued = login.json()
    assert issued["token_type"] == "bearer"
    expires_at = datetime.fromisoformat(issued["expires_at"])
    assert abs(expires_at - (datetime.now(UTC) + timedelta(days=14))) < timedelta(
        minutes=1
    )
    me = await client.get("/v1/me", headers=bearer(issued["access_token"]))
    assert me.status_code == 200 and me.json()["id"] == body["id"]


async def test_instructor_email_code_mismatch_422_increments_tries(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await _code_for(client, factory, capsys)
    r = await client.post(SIGNUP, json=_body(EMAIL, _other(code)))
    wrong = problem_of(r, 422, "/problems/email-code-mismatch")
    tries = await db_session.scalar(select(EmailVerification.tries))
    assert tries == 1
    assert await _attempts(db_session) == [("email_code", False)]
    assert await count(db_session, Instructor) == 0
    # 열린 요청이 없는 이메일도 같은 422 · 같은 안내다(요청 존재가 드러나지 않는다)
    r = await client.post(SIGNUP, json=_body("nobody@example.com", code))
    nobody = problem_of(r, 422, "/problems/email-code-mismatch")
    assert nobody["detail"] == wrong["detail"]
    assert await count(db_session, Instructor) == 0


async def test_instructor_email_code_expired_410(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await _code_for(client, factory, capsys)
    # 수명 기준은 해시 저장 시각(issued_at)이다. 10분 + 1분 전으로 돌린다
    await db_session.execute(
        update(EmailVerification).values(issued_at=func.now() - timedelta(minutes=11))
    )
    r = await client.post(SIGNUP, json=_body(EMAIL, code))
    problem_of(r, 410, "/problems/email-code-expired")
    assert await _attempts(db_session) == [("email_code", False)]
    assert await count(db_session, Instructor) == 0
    # 대조: 수명 안(9분 전)이면 같은 코드가 통과한다
    await db_session.execute(
        update(EmailVerification).values(issued_at=func.now() - timedelta(minutes=9))
    )
    assert (await client.post(SIGNUP, json=_body(EMAIL, code))).status_code == 201


async def test_instructor_email_code_locked_after_5_tries_429(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await _code_for(client, factory, capsys)
    for _ in range(5):
        r = await client.post(SIGNUP, json=_body(EMAIL, _other(code)))
        problem_of(r, 422, "/problems/email-code-mismatch")
    locked = await client.post(SIGNUP, json=_body(EMAIL, _other(code)))
    problem_of(locked, 429, "/problems/email-code-locked")
    assert "retry-after" not in locked.headers
    right = await client.post(SIGNUP, json=_body(EMAIL, code))
    problem_of(right, 429, "/problems/email-code-locked")  # 맞는 코드도 잠김
    assert await db_session.scalar(select(EmailVerification.tries)) == 5
    assert await count(db_session, Instructor) == 0
    assert await count(db_session, AuthAttempt, AuthAttempt.ok.is_(False)) == 7


async def test_instructor_email_code_resend_invalidates_previous(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = await _code_for(client, factory, capsys)
    second = await _code_for(client, factory, capsys)
    sent = 2
    while second == first:  # 10^-6 확률로 같은 숫자가 나오면 한 번 더 보낸다
        second = await _code_for(client, factory, capsys)
        sent += 1
    old = await client.post(SIGNUP, json=_body(EMAIL, first))
    problem_of(old, 422, "/problems/email-code-mismatch")
    new = await client.post(SIGNUP, json=_body(EMAIL, second))
    assert new.status_code == 201, new.text
    assert await count(db_session, EmailVerification) == 1  # 재요청은 같은 행
    assert await count(db_session, MailOutbox, MailOutbox.kind == "email_code") == sent


async def test_instructor_signup_zero_tags_422(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await _code_for(client, factory, capsys)
    r = await client.post(SIGNUP, json=_body(EMAIL, code, tags=[]))
    assert ["body", "tags"] in locs(problem_of(r, 422))
    r = await client.post(SIGNUP, json=_body(EMAIL, code, tags=["  "]))
    assert ["body", "tags", 0] in locs(problem_of(r, 422))
    assert await count(db_session, Instructor) == 0
    assert await count(db_session, Tag) == 0
    assert await _attempts(db_session) == []  # 모양 거절은 시도로 세지 않는다
    assert await db_session.scalar(select(EmailVerification.tries)) == 0


async def test_instructor_signup_terms_required_422(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await _code_for(client, factory, capsys)
    r = await client.post(SIGNUP, json=_body(EMAIL, code, privacy_agreed=False))
    assert locs(problem_of(r, 422)) == [["body", "privacy_agreed"]]
    body = _body(EMAIL, code)
    del body["terms_agreed"]
    r = await client.post(SIGNUP, json=body)
    assert locs(problem_of(r, 422)) == [["body", "terms_agreed"]]
    body = _body(EMAIL, code)
    del body["org"]  # 무소속은 null 로 준다. 키가 빠지면 422
    r = await client.post(SIGNUP, json=body)
    assert locs(problem_of(r, 422)) == [["body", "org"]]
    r = await client.post(SIGNUP, json=_body(EMAIL, code, password="short7!"))
    assert locs(problem_of(r, 422)) == [["body", "password"]]
    assert await count(db_session, Instructor) == 0


async def test_instructor_signup_duplicate_email_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_instructor(db_session, app.state.settings, email=EMAIL)
    # 요청 끝점은 가입된 이메일을 409 로 막으므로, 열린 요청 행은 준비 단계에서 직접 둔다
    request = EmailVerification(email=EMAIL)
    db_session.add(request)
    await db_session.flush()
    code = await issue_email_code(db_session, request.id)
    r = await client.post(SIGNUP, json=_body("Instructor-A@EXAMPLE.com", code))
    problem_of(r, 409, "/problems/conflict")
    assert await count(db_session, Instructor) == 1
    consumed = await db_session.scalar(
        select(EmailVerification.consumed_at).where(EmailVerification.id == request.id)
    )
    assert consumed is None  # 롤백: 요청 행은 소비되지 않았다


async def test_instructor_signup_new_tag_created_with_default_group(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await _code_for(client, factory, capsys)
    r = await client.post(SIGNUP, json=_body(EMAIL, code, tags=["생성형 AI"]))
    assert r.status_code == 201, r.text
    tags = (
        await db_session.execute(
            select(Tag.kind, Tag.name, Tag.group_name, Tag.source, Tag.active)
        )
    ).all()
    assert [tuple(t) for t in tags] == [
        ("field", "생성형 AI", "기타", "instructor", True)
    ]
    assert r.json()["tags"][0]["group"] == "기타"
    # 같은 이름(공백만 다름)은 새 행을 만들지 않고 같은 태그를 붙인다
    other = "instructor-b@example.com"
    code = await _code_for(client, factory, capsys, other)
    r = await client.post(
        SIGNUP, json=_body(other, code, tags=[" 생성형   AI ", "생성형 AI"])
    )
    assert r.status_code == 201, r.text
    assert [t["name"] for t in r.json()["tags"]] == ["생성형 AI"]
    assert await count(db_session, Tag) == 1
    assert await count(db_session, InstructorTag) == 2
