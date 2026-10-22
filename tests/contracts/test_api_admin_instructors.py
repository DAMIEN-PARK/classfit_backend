"""관리자 강사 끝점(목록·상세·:approve·:reject·:suspend·:unsuspend·memo), T3 계획 결정 vi·vii·xviii · 증명 7·8·9.

전이표는 기획안 A2 4행 = 5전이다(대기→승인 · 대기→반려 · 반려→대기(강사 :reapply) · 승인→정지 · 정지→승인).
관리자 동작 넷 × 상태 넷 중 표 밖 12쌍은 409 + current_status 이고 행·audit 이 그대로다.
승인·반려는 audit 1 + outbox 1(params {instructor_id, audit_id}), 반려 메일 본문은 audit detail 의 사유를 쓴다.
"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from classfit.core.config import Settings
from classfit.database.session import make_session_factory
from classfit.models import AuditLog, AuthSession, Instructor, MailOutbox
from scripts import outbox_preview
from tests.fixtures.courses import admin_headers
from tests.fixtures.enter import bearer, json_keys
from tests.fixtures.instructors import (
    PASSWORD,
    count,
    instructor_headers,
    locs,
    make_instructor,
    pdf_bytes,
    problem_of,
)

ADMIN = "/v1/admin/instructors"
EMAIL = "instructor-a@example.com"
STATUSES = ("pending", "approved", "rejected", "suspended")
ACTIONS = ("approve", "reject", "suspend", "unsuspend")
INSIDE = {
    ("pending", "approve"): "approved",
    ("pending", "reject"): "rejected",
    ("approved", "suspend"): "suspended",
    ("suspended", "unsuspend"): "approved",
}
REASON = "강의 이력을 보완해 주세요"


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


async def _act(
    client: httpx.AsyncClient, admin: dict[str, str], iid: int, action: str
) -> httpx.Response:
    body = {"reason": REASON} if action == "reject" else None
    return await client.post(f"{ADMIN}/{iid}:{action}", headers=admin, json=body)


async def _status(session: AsyncSession, iid: int) -> str | None:
    return await session.scalar(select(Instructor.status).where(Instructor.id == iid))


async def _audit(session: AsyncSession, iid: int) -> list[tuple]:
    rows = await session.execute(
        select(AuditLog.id, AuditLog.action, AuditLog.actor, AuditLog.detail)
        .where(AuditLog.target_type == "instructor", AuditLog.target_id == str(iid))
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _mail(session: AsyncSession) -> list[tuple]:
    rows = await session.execute(
        select(MailOutbox.kind, MailOutbox.params, MailOutbox.to)
        .where(MailOutbox.kind.like("instructor_%"))
        .order_by(MailOutbox.id)
    )
    return [tuple(r) for r in rows]


async def _preview(
    factory: async_sessionmaker[AsyncSession], capsys: pytest.CaptureFixture[str]
) -> list[dict]:
    capsys.readouterr()
    assert await outbox_preview.run([], factory) == 0
    return json.loads(capsys.readouterr().out)["messages"]


async def test_instructor_status_approve_audit_and_outbox(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email=EMAIL)
    aid, admin = await admin_headers(db_session)
    r = await _act(client, admin, iid, "approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    audit = await _audit(db_session, iid)
    assert [(a[1], a[2]) for a in audit] == [("instructor.approve", f"admin:{aid}")]
    assert await _mail(db_session) == [
        ("instructor_approved", {"instructor_id": iid, "audit_id": audit[0][0]}, EMAIL)
    ]
    # outbox_preview 가 새 kind 를 찍는다(모르는 kind 3 이 아니다)
    approved = [
        m for m in await _preview(factory, capsys) if m["kind"] == "instructor_approved"
    ]
    assert [m["to"] for m in approved] == [EMAIL]


async def test_instructor_status_reject_without_reason_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email=EMAIL)
    _, admin = await admin_headers(db_session)
    for body in ({}, {"reason": "  "}, {"reason": None}):
        r = await client.post(f"{ADMIN}/{iid}:reject", headers=admin, json=body)
        assert locs(problem_of(r, 422)) == [["body", "reason"]], body
    assert await _status(db_session, iid) == "pending"
    assert await _audit(db_session, iid) == []
    assert await _mail(db_session) == []


async def test_instructor_status_reject_sets_reason_and_outbox(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email=EMAIL)
    _, admin = await admin_headers(db_session)
    r = await client.post(
        f"{ADMIN}/{iid}:reject", headers=admin, json={"reason": f"  {REASON} "}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["reject_reason"]) == ("rejected", REASON)
    audit = await _audit(db_session, iid)
    assert [(a[1], a[3]) for a in audit] == [("instructor.reject", {"reason": REASON})]
    mail = await _mail(db_session)
    assert mail == [
        ("instructor_rejected", {"instructor_id": iid, "audit_id": audit[0][0]}, EMAIL)
    ]
    assert REASON not in json.dumps(mail[0][1], ensure_ascii=False)
    # 재신청이 행의 사유를 비워도 메일 본문은 audit 의 사유 그대로다
    auth = await instructor_headers(db_session, iid)
    assert (await client.post("/v1/me:reapply", headers=auth)).status_code == 200
    rejected = [
        m for m in await _preview(factory, capsys) if m["kind"] == "instructor_rejected"
    ]
    assert len(rejected) == 1 and REASON in rejected[0]["body"]


async def test_instructor_status_suspend_revokes_sessions(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email=EMAIL, status="approved"
    )
    direct = await instructor_headers(db_session, iid)
    login = await client.post(
        "/v1/auth/instructor/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    tokens = [direct, bearer(login.json()["access_token"])]
    for auth in tokens:
        assert (await client.get("/v1/me", headers=auth)).status_code == 200
    _, admin = await admin_headers(db_session)
    r = await _act(client, admin, iid, "suspend")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "suspended"
    for auth in tokens:
        problem_of(await client.get("/v1/me", headers=auth), 401)
    live = await count(
        db_session,
        AuthSession,
        AuthSession.principal_type == "instructor",
        AuthSession.revoked_at.is_(None),
    )
    assert live == 0
    # 관리자 세션은 그대로
    assert (await client.get(f"{ADMIN}/{iid}", headers=admin)).status_code == 200
    assert [a[1] for a in await _audit(db_session, iid)] == ["instructor.suspend"]
    assert await _mail(db_session) == []  # 정지는 메일이 없다(결정 vi 기본)


async def test_instructor_status_unsuspend_to_approved(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email=EMAIL, status="approved"
    )
    _, admin = await admin_headers(db_session)
    assert (await _act(client, admin, iid, "suspend")).status_code == 200
    r = await _act(client, admin, iid, "unsuspend")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert [a[1] for a in await _audit(db_session, iid)] == [
        "instructor.suspend",
        "instructor.unsuspend",
    ]
    login = await client.post(
        "/v1/auth/instructor/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text


async def test_instructor_status_approve_rejected_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email=EMAIL, status="rejected"
    )
    _, admin = await admin_headers(db_session)
    body = problem_of(
        await _act(client, admin, iid, "approve"), 409, "/problems/conflict"
    )
    assert body["current_status"] == "rejected"
    assert await _status(db_session, iid) == "rejected"
    assert await _audit(db_session, iid) == []
    assert await _mail(db_session) == []


async def test_instructor_status_transition_table_outside_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    outside = []
    for status in STATUSES:
        iid = await make_instructor(
            db_session,
            app.state.settings,
            email=f"instructor-{status}@example.com",
            status=status,
        )
        for action in ACTIONS:
            if (status, action) in INSIDE:
                continue
            r = await _act(client, admin, iid, action)
            body = problem_of(r, 409, "/problems/conflict")
            outside.append((status, action, body["current_status"]))
            assert await _status(db_session, iid) == status
        assert await _audit(db_session, iid) == []
    assert len(outside) == 12
    assert all(current == status for status, _, current in outside)
    # 대조: 표 안 4쌍(관리자 동작)은 200 이고 audit 1행씩
    for n, ((status, action), after) in enumerate(INSIDE.items()):
        iid = await make_instructor(
            db_session,
            app.state.settings,
            email=f"instructor-in-{n}@example.com",
            status=status,
        )
        r = await _act(client, admin, iid, action)
        assert r.status_code == 200, (status, action, r.text)
        assert r.json()["status"] == after
        assert [a[1] for a in await _audit(db_session, iid)] == [f"instructor.{action}"]


async def test_admin_instructors_list_filter_status_and_q(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    settings = app.state.settings
    first = await make_instructor(db_session, settings, email="alpha@example.com")
    second = await make_instructor(
        db_session, settings, email="beta@example.com", status="approved"
    )
    third = await make_instructor(
        db_session, settings, email="gamma@example.com", status="rejected"
    )
    put = await client.put(
        "/v1/me/documents/resume",
        headers=await instructor_headers(db_session, first),
        files={"file": ("a.pdf", pdf_bytes(), "application/pdf")},
    )
    assert put.status_code == 201, put.text
    _, admin = await admin_headers(db_session)

    async def ids(**params: object) -> list[int]:
        r = await client.get(ADMIN, headers=admin, params=params)
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert await ids(status="approved") == [second]
    assert await ids(q="BETA") == [second]
    assert await ids(q="example.com", status="rejected") == [third]
    # 같은 트랜잭션이라 created_at 이 같고 id 내림차순이다
    page = (await client.get(ADMIN, headers=admin, params={"limit": 2})).json()
    assert [i["id"] for i in page["items"]] == [third, second]
    assert page["has_more"] is True and page["next_cursor"]
    rest = (
        await client.get(
            ADMIN, headers=admin, params={"limit": 2, "cursor": page["next_cursor"]}
        )
    ).json()
    assert ([i["id"] for i in rest["items"]], rest["has_more"]) == ([first], False)
    item = rest["items"][0]
    assert (item["documents_submitted"], item["documents_required"]) == (1, 3)
    assert item["status"] == "pending" and item["applied_at"]
    assert [t["name"] for t in item["tags"]] == ["프롬프트"]
    assert {i["documents_submitted"] for i in page["items"]} == {0}
    problem_of(await client.get(ADMIN, headers=admin, params={"status": "gone"}), 422)


async def test_admin_instructors_list_bad_cursor_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    r = await client.get(ADMIN, headers=admin, params={"cursor": "not-a-cursor"})
    assert locs(problem_of(r, 422)) == [["query", "cursor"]]
    r = await client.get(ADMIN, headers=admin, params={"q": "a\x00b"})
    assert locs(problem_of(r, 422)) == [["query", "q"]]


async def test_admin_instructors_memo_patch_audit_once(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email=EMAIL)
    aid, admin = await admin_headers(db_session)
    for _ in range(2):
        r = await client.patch(
            f"{ADMIN}/{iid}/memo", headers=admin, json={"memo": " 연락 선호: 오전 "}
        )
        assert r.status_code == 200, r.text
        assert r.json()["memo"] == "연락 선호: 오전"
    audit = await _audit(db_session, iid)
    assert [(a[1], a[2], a[3]) for a in audit] == [
        ("instructor.memo", f"admin:{aid}", {})
    ]
    r = await client.patch(f"{ADMIN}/{iid}/memo", headers=admin, json={"memo": None})
    assert r.status_code == 200 and r.json()["memo"] is None
    assert len(await _audit(db_session, iid)) == 2
    problem_of(
        await client.patch(
            f"{ADMIN}/999999999/memo", headers=admin, json={"memo": "x"}
        ),
        404,
    )


async def test_admin_instructors_detail_has_no_href(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email=EMAIL)
    put = await client.put(
        "/v1/me/documents/cert",
        headers=await instructor_headers(db_session, iid),
        files={"file": ("a.pdf", pdf_bytes(), "application/pdf")},
    )
    assert put.status_code == 201, put.text
    _, admin = await admin_headers(db_session)
    detail = await client.get(f"{ADMIN}/{iid}", headers=admin)
    listing = await client.get(ADMIN, headers=admin)
    for r in (detail, listing):
        assert r.status_code == 200, r.text
        assert "href" not in json_keys(r.json())
        assert "/v1/files/" not in r.text
    body = detail.json()
    docs = {d["type_id"]: d for d in body["documents"]}
    assert list(docs) == ["resume", "cert", "pledge"]
    assert docs["cert"]["size"] == len(pdf_bytes()) and docs["cert"]["submitted_at"]
    assert docs["resume"]["size"] is None and docs["resume"]["submitted_at"] is None
    assert (body["documents_submitted"], body["documents_required"]) == (1, 3)
    assert "memo" in body and "password_hash" not in json_keys(body)
    problem_of(await client.get(f"{ADMIN}/999999999", headers=admin), 404)
