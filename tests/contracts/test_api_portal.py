"""포털 끝점(수강생 GET /v1/learner/courses/{id}/portal · 관리자 미리 보기)과 수강생 첨부 목록(T2b 계획 결정 vii·x).

준비 중 카드(열림 ∧ 첨부 ≥ 1 이 아니면 preparing) · 잠긴 세션 첨부 403 · 개인 키 없음(E-14) · 종료 강의 열람 ·
일정표와 같은 시각 · /v1/learner/ 경로의 403·401. 픽스처 강의는 2026-11-02 ~ 2026-11-05, 하루 13:00~17:00 이다.
"""

import re
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.core.config import Settings
from classfit.main import create_app
from tests.fixtures.courses import admin_headers, open_test_course
from tests.fixtures.enter import (
    PERSONAL_KEYS,
    add_pdf,
    add_section,
    add_session,
    bearer,
    enter_learner,
    json_keys,
)

ADMIN = "/v1/admin"
RUNNING = date(2026, 11, 3)
ENDED = date(2026, 11, 6)
METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _set_today(app: FastAPI, d: date) -> None:
    app.dependency_overrides[today] = lambda: d


async def _learner(
    client: httpx.AsyncClient, code: str, email: str = "kim@example.com"
) -> dict[str, str]:
    r = await enter_learner(client, code, email, "김가명", dept="교육팀")
    assert r.status_code in (200, 201), r.text
    return bearer(r.json()["access_token"])


async def _cards(
    client: httpx.AsyncClient, url: str, headers: dict[str, str]
) -> dict[int, dict]:
    r = await client.get(url, headers=headers)
    assert r.status_code == 200, r.text
    return {s["id"]: s for sec in r.json()["sections"] for s in sec["sessions"]}


def _learner_portal(course_id: int) -> str:
    return f"/v1/learner/courses/{course_id}/portal"


def _admin_portal(course_id: int) -> str:
    return f"{ADMIN}/courses/{course_id}/portal"


async def test_portal_locked_when_closed(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    sid = await add_session(
        client, auth, course.id, day_no=1, slot=1, description="설명", keywords=["AI"]
    )
    assert (await add_pdf(client, auth, sid)).status_code == 201
    learner = await _learner(client, code.code)

    for url, headers in (
        (_learner_portal(course.id), learner),
        (_admin_portal(course.id), auth),
    ):
        card = (await _cards(client, url, headers))[sid]
        assert card["state"] == "preparing"
        assert (
            card["title"],
            card["day_no"],
            card["date"],
            card["start"],
            card["end"],
        ) == (
            "세션",
            1,
            "2026-11-02",
            "13:00",
            "13:50",
        )
        assert (card["description"], card["keywords"], card["attachments"]) == (
            None,
            None,
            [],
        )

    r = await client.patch(
        f"{ADMIN}/sessions/{sid}", headers=auth, json={"is_open": True}
    )
    assert r.status_code == 200, r.text
    card = (await _cards(client, _learner_portal(course.id), learner))[sid]
    assert card["state"] == "open"
    assert (card["description"], card["keywords"]) == ("설명", ["AI"])
    assert [a["kind"] for a in card["attachments"]] == ["pdf"]
    assert card["attachments"][0]["href"].startswith("/v1/files/")


async def test_portal_locked_when_no_attachment(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    sid = await add_session(
        client, auth, course.id, day_no=1, slot=1, is_open=True, description="설명"
    )
    learner = await _learner(client, code.code)
    for url, headers in (
        (_learner_portal(course.id), learner),
        (_admin_portal(course.id), auth),
    ):
        card = (await _cards(client, url, headers))[sid]
        assert (card["state"], card["description"], card["attachments"]) == (
            "preparing",
            None,
            [],
        )
    r = await client.get(f"/v1/learner/sessions/{sid}/attachments", headers=learner)
    assert r.status_code == 403, r.text
    # 링크 하나를 붙이면 열린다
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={"kind": "link", "title": "자료", "url": "https://example.com/a"},
    )
    assert r.status_code == 201, r.text
    card = (await _cards(client, _learner_portal(course.id), learner))[sid]
    assert card["state"] == "open"
    assert [a["href"] for a in card["attachments"]] == ["https://example.com/a"]


async def test_portal_locked_attachments_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    sid = await add_session(client, auth, course.id, day_no=1, slot=1)
    up = await add_pdf(client, auth, sid)
    assert up.status_code == 201, up.text
    href = up.json()["href"]
    learner = await _learner(client, code.code)
    listing = f"/v1/learner/sessions/{sid}/attachments"

    r = await client.get(listing, headers=learner)
    assert r.status_code == 403 and r.json()["type"] == "/problems/forbidden", r.text
    assert (await client.get(href, headers=learner)).status_code == 403
    assert (await client.get(href, headers=auth)).status_code == 200  # 관리자는 연다
    assert (
        await client.get("/v1/learner/sessions/999999999/attachments", headers=learner)
    ).status_code == 404

    await client.patch(f"{ADMIN}/sessions/{sid}", headers=auth, json={"is_open": True})
    r = await client.get(listing, headers=learner)
    assert r.status_code == 200, r.text
    assert (r.json()["has_more"], r.json()["next_cursor"]) == (False, None)
    assert [a["href"] for a in r.json()["items"]] == [href]
    assert (await client.get(href, headers=learner)).status_code == 200


async def test_no_personal_keys_portal(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    sid = await add_session(
        client, auth, course.id, day_no=1, slot=1, is_open=True, keywords=["AI"]
    )
    assert (await add_pdf(client, auth, sid)).status_code == 201
    learner = await _learner(client, code.code)
    responses = [
        await client.get(_learner_portal(course.id), headers=learner),
        await client.get(_admin_portal(course.id), headers=auth),
        await client.get(f"/v1/learner/sessions/{sid}/attachments", headers=learner),
    ]
    for r in responses:
        assert r.status_code == 200, r.text
        assert json_keys(r.json()) & PERSONAL_KEYS == set(), r.url
        for secret in ("김가명", "kim@example.com", "교육팀"):
            assert secret not in r.text, (r.url, secret)


async def test_portal_ended_course_existing_learner_200(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    course, code = await open_test_course(db_session)
    learner = await _learner(client, code.code)
    _set_today(app, ENDED)
    r = await client.get(_learner_portal(course.id), headers=learner)
    assert r.status_code == 200, r.text
    assert r.json()["course"]["status"] == "ended"
    # 종료 뒤에도 기존 등록자는 재입장해 새 토큰으로 연다
    again = await _learner(client, code.code)
    assert (
        await client.get(_learner_portal(course.id), headers=again)
    ).status_code == 200


async def test_portal_times_match_admin_schedule(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    _, auth = await admin_headers(db_session)
    course, code = await open_test_course(db_session)
    cid = course.id
    sec = await add_section(client, auth, cid, "1부")
    other = await add_section(client, auth, cid, "2부")
    made = [
        await add_session(client, auth, cid, section_id=sec, day_no=1, slot=1),
        await add_session(
            client, auth, cid, section_id=sec, day_no=1, slot=2, minutes=90
        ),
        await add_session(
            client,
            auth,
            cid,
            section_id=sec,
            day_no=1,
            time_start="09:00",
            time_end="10:00",
        ),
        await add_session(client, auth, cid, section_id=other, day_no=2, slot=1),
        await add_session(client, auth, cid, section_id=other, day_no=3),
        await add_session(client, auth, cid, section_id=other),
    ]
    sched = (await client.get(f"{ADMIN}/courses/{cid}/schedule", headers=auth)).json()
    expected: dict[int, tuple[str | None, str | None, str | None]] = {}
    for day in sched["days"]:
        for s in day["sessions"]:
            expected[s["id"]] = (day["date"], s["start"], s["end"])
    for s in sched["undated"]:
        expected[s["id"]] = (None, s["start"], s["end"])
    assert set(expected) == set(made)
    assert expected[made[1]] == (
        "2026-11-02",
        "14:00",
        "15:30",
    )  # 시각이 실제로 계산된 값인지

    learner = await _learner(client, code.code)
    for url, headers in ((_learner_portal(cid), learner), (_admin_portal(cid), auth)):
        cards = await _cards(client, url, headers)
        assert {
            i: (c["date"], c["start"], c["end"]) for i, c in cards.items()
        } == expected


def _learner_operations() -> list[tuple[str, str]]:
    spec = create_app(Settings()).openapi()
    return sorted(
        (method.upper(), re.sub(r"\{[^}]+\}", "1", path))
        for path, item in spec["paths"].items()
        if path.startswith("/v1/learner/")
        for method in item
        if method in METHODS
    )


async def test_learner_paths_admin_403_and_no_token_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operations = _learner_operations()
    assert len(operations) >= 2, operations
    _, admin = await admin_headers(db_session)
    wrong = []
    for method, path in operations:
        as_admin = await client.request(method, path, headers=admin)
        anonymous = await client.request(method, path)
        if (
            as_admin.status_code != 403
            or anonymous.status_code != 401
            or anonymous.headers.get("www-authenticate") != "Bearer"
        ):
            wrong.append((method, path, as_admin.status_code, anonymous.status_code))
    assert wrong == []
