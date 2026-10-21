"""초대코드 끝점: 종료 강의 :resume 409, 정지·재개, 재발급(옛 행 replaced · audit), 만료일·정원 PATCH, 안내문.

픽스처 강의는 2026-11-02 ~ 2026-11-05 이고 코드 만료일은 2026-12-05(종료일 + 30)다.
"""

from datetime import date

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.models import AuditLog, InviteCode
from tests.fixtures.courses import admin_headers, open_test_course

URL = "/v1/admin/courses"


def _set_today(app: FastAPI, d: date) -> None:
    app.dependency_overrides[today] = lambda: d


async def _audits(session: AsyncSession, action: str) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
        or 0
    )


async def test_code_state_resume_ended_course_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 11, 6))  # 종료일 다음 날 → 강의 ended(날짜 규칙)
    course, _ = await open_test_course(db_session)
    code_url = f"{URL}/{course.id}/invite-code"
    paused = await client.post(f"{code_url}:pause", headers=auth)
    assert paused.status_code == 200, paused.text
    assert (paused.json()["status"], paused.json()["state"]) == ("paused", "stopped")
    r = await client.post(f"{code_url}:resume", headers=auth)
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == "/problems/conflict"
    assert (await client.get(code_url, headers=auth)).json()[
        "status"
    ] == "paused"  # 그대로
    assert await _audits(db_session, "invite_code.resume") == 0
    # 수동 종료도 같다
    _set_today(app, date(2026, 10, 22))
    await client.post(
        f"{URL}/{course.id}:set-status", headers=auth, json={"status": "ended"}
    )
    assert (await client.post(f"{code_url}:resume", headers=auth)).status_code == 409


async def test_code_state_pause_resume_200(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 10, 22))
    course, code = await open_test_course(db_session)
    code_url = f"{URL}/{course.id}/invite-code"
    paused = (await client.post(f"{code_url}:pause", headers=auth)).json()
    assert (paused["code"], paused["status"], paused["state"]) == (
        code.code,
        "paused",
        "paused",
    )
    resumed = await client.post(f"{code_url}:resume", headers=auth)
    assert resumed.status_code == 200, resumed.text
    assert (resumed.json()["status"], resumed.json()["state"]) == ("active", "active")
    assert (
        await _audits(db_session, "invite_code.pause"),
        await _audits(db_session, "invite_code.resume"),
    ) == (1, 1)


async def test_invite_code_reissue_api_old_replaced(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 10, 22))
    course, old = await open_test_course(db_session)
    old_id, old_code = old.id, old.code
    r = await client.post(f"{URL}/{course.id}/invite-code:reissue", headers=auth)
    assert r.status_code == 200, r.text
    new_code = r.json()["code"]
    assert new_code != old_code and (r.json()["status"], r.json()["expires_on"]) == (
        "active",
        "2026-12-05",
    )
    rows = (
        await db_session.execute(
            select(InviteCode.id, InviteCode.code, InviteCode.status)
            .where(InviteCode.course_id == course.id)
            .order_by(InviteCode.id)
        )
    ).all()
    assert [(row.code, row.status) for row in rows] == [
        (old_code, "replaced"),
        (new_code, "active"),
    ]
    assert rows[0].id == old_id
    assert (await client.get(f"{URL}/{course.id}/invite-code", headers=auth)).json()[
        "code"
    ] == new_code
    audits = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "invite_code.reissue")
            )
        )
        .scalars()
        .all()
    )
    assert [(a.actor, a.target_type, a.target_id) for a in audits] == [
        (f"admin:{admin_id}", "course", str(course.id))
    ]
    assert old_code not in str(audits[0].detail) and new_code not in str(
        audits[0].detail
    )


async def test_invite_code_patch_expires_on_and_max_seats(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 10, 22))
    course, _ = await open_test_course(db_session)
    code_url = f"{URL}/{course.id}/invite-code"
    r = await client.patch(
        code_url, headers=auth, json={"expires_on": "2027-01-31", "max_seats": 25}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["expires_on"], r.json()["max_seats"]) == ("2027-01-31", 25)
    cleared = (
        await client.patch(code_url, headers=auth, json={"max_seats": None})
    ).json()
    assert (cleared["expires_on"], cleared["max_seats"]) == ("2027-01-31", None)
    for bad in ({"expires_on": None}, {"max_seats": 0}):
        assert (await client.patch(code_url, headers=auth, json=bad)).status_code == 422
    assert await _audits(db_session, "invite_code.update") == 2
    # 새 만료일이 상태에 쓰인다(강의는 수동 running 으로 두어 stopped 가 먼저 서지 않게)
    await client.post(
        f"{URL}/{course.id}:set-status", headers=auth, json={"status": "running"}
    )
    _set_today(app, date(2027, 1, 31))
    assert (await client.get(code_url, headers=auth)).json()[
        "state"
    ] == "active"  # 만료일 당일까지 유효
    _set_today(app, date(2027, 2, 1))
    assert (await client.get(code_url, headers=auth)).json()["state"] == "expired"


async def test_invite_code_notice_has_code_and_period(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session, title="AI 활용 기초")
    r = await client.get(f"{URL}/{course.id}/invite-code/notice", headers=auth)
    assert r.status_code == 200, r.text
    text = r.json()["text"]
    for part in ("AI 활용 기초", "2026-11-02", "2026-11-05", code.code, "2026-12-05"):
        assert part in text, part
