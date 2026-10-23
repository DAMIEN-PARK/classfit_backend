"""강사 화면 읽기: 포털 미리 보기 · 초대코드·안내문 · 명단 · 홈(T6 계획 결정 xiii·xiv·xxi·xxii · 증명 18~21).

강의를 가리키는 읽기는 없는 강의 404 → 내 세션이 없는 강의 403 이고 경로 id 2**63 이상은 422 다. 포털 미리 보기는 같은
날 수강생 포털과 같은 JSON 이다. 명단은 이름·부서·등록일만 준다(이메일 없음, 정본과 다름 — spec 3절). 홈은 보관 안 한
배정 강의의 셈·표·할 일과 안 낸 필수 서류·가능 과정 수다. 응답은 허용 키 집합을 정확히 잰다.
픽스처 강의는 2026-11-02(월)부터 평일, 하루 13:00~17:00 이다.
"""

from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.core.config import Settings
from tests.fixtures.assign import approved, course_with_section
from tests.fixtures.courses import admin_headers, open_test_course
from tests.fixtures.enter import (
    add_section,
    add_session,
    bearer,
    enter_learner,
    json_keys,
)
from tests.fixtures.instructors import locs, problem_of
from tests.fixtures.my_attachments import ROSTER_KEYS, SAMPLES, link, upload
from tests.fixtures.pool import make_pool_course

ADMIN = "/v1/admin"
ME = "/v1/me"
RUNNING = date(2026, 11, 3)
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422
# 포털 응답의 허용 키(T5 test_assign_portal_instructor_name 과 같은 집합)
TOP_KEYS = {"course", "sections", "survey"}
COURSE_KEYS = {"id", "title", "start_on", "end_on", "status", "intro", "notice"}
SECTION_KEYS = {"id", "title", "description", "sessions"}
CARD_KEYS = {
    "id",
    "title",
    "day_no",
    "date",
    "start",
    "end",
    "state",
    "description",
    "keywords",
    "attachments",
    "instructor_name",
}
ATTACHMENT_KEYS = {"id", "kind", "title", "description", "href", "size"}
CODE_KEYS = {
    "code",
    "status",
    "state",
    "expires_on",
    "max_seats",
    "issued_at",
    "enrolled",
}
PAGE_KEYS = {"items", "next_cursor", "has_more"}
HOME_KEYS = {
    "status",
    "summary",
    "courses",
    "courses_more",
    "todo",
    "todo_more",
    "records_todo",
    "records_todo_more",
    "surveys",
    "surveys_more",
    "documents_missing",
    "capable",
}
SUMMARY_KEYS = {"courses", "running", "prep", "ended", "my_sessions", "my_ready"}
HOME_COURSE_KEYS = {
    "id",
    "title",
    "course_type",
    "client_name",
    "status",
    "start_on",
    "end_on",
    "my_sessions",
    "my_ready",
    "code",
    "code_state",
}
TODO_KEYS = {
    "course_id",
    "course_title",
    "section_id",
    "section_title",
    "session_id",
    "session_title",
    "day_no",
    "slot",
}
REQUIRED_DOCUMENTS = ["resume", "cert", "pledge"]  # 0005 시드, (sort, id) 순


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _set_today(app: FastAPI, d: date) -> None:
    app.dependency_overrides[today] = lambda: d


async def _assign(
    client: httpx.AsyncClient, auth: dict[str, str], session_id: int, iid: int | None
) -> None:
    r = await client.patch(
        f"{ADMIN}/sessions/{session_id}", headers=auth, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


async def _owned_session(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    course_id: int,
    section_id: int,
    iid: int,
    **fields: Any,
) -> int:
    """관리자 API 로 만든 세션을 그 강사에게 배정한다."""
    sid = await add_session(client, admin, course_id, section_id=section_id, **fields)
    await _assign(client, admin, sid, iid)
    return sid


async def _out_of_range(
    client: httpx.AsyncClient, headers: dict[str, str], path: str
) -> None:
    """path 의 {id} 에 없는 id 를 넣으면 404, BIGINT 밖이면 422 loc ["path", "course_id"]."""
    problem_of(
        await client.get(path.format(id=LARGEST), headers=headers),
        404,
        "/problems/not_found",
    )
    body = problem_of(await client.get(path.format(id=OVERFLOW), headers=headers), 422)
    assert locs(body) == [["path", "course_id"]]
    assert [v["type"] for v in body["violations"]] == ["less_than"]


async def test_instructor_view_portal_preview_matches_learner(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _set_today(app, RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    course, code = await open_test_course(db_session)
    section = await add_section(client, admin, course.id)
    sessions = {}
    for title, iid, auth, day_no, slot, is_open in (
        ("X 열림", x, x_auth, 1, 1, True),
        ("Y 열림", y, y_auth, 1, 2, True),
        ("Y 닫힘", y, y_auth, 2, 1, False),
    ):
        sid = await _owned_session(
            client,
            admin,
            course.id,
            section,
            iid,
            title=title,
            day_no=day_no,
            slot=slot,
            is_open=is_open,
        )
        r = await upload(
            client, auth, sid, "자료.pdf", SAMPLES[".pdf"] + title.encode()
        )
        assert r.status_code == 201, r.text
        sessions[title] = sid
    r = await enter_learner(
        client, code.code, "kim@example.com", "김가명", dept="교육팀"
    )
    assert r.status_code == 201, r.text
    learner = bearer(r.json()["access_token"])

    url = f"{ME}/courses/{course.id}/portal"
    preview = await client.get(url, headers=x_auth)
    assert preview.status_code == 200, preview.text
    portal = await client.get(
        f"/v1/learner/courses/{course.id}/portal", headers=learner
    )
    assert portal.status_code == 200, portal.text
    assert preview.json() == portal.json()
    body = preview.json()
    assert set(body) == TOP_KEYS
    assert set(body["course"]) == COURSE_KEYS
    cards = {}
    for sec in body["sections"]:
        assert set(sec) == SECTION_KEYS
        for card in sec["sessions"]:
            assert set(card) == CARD_KEYS, card
            for item in card["attachments"]:
                assert set(item) == ATTACHMENT_KEYS, item
            cards[card["id"]] = card
    assert (
        json_keys(body)
        & {
            "email",
            "phone",
            "instructor_id",
            "origin",
            "learner_id",
        }
        == set()
    )
    assert {
        title: (cards[sid]["state"], len(cards[sid]["attachments"]))
        for title, sid in sessions.items()
    } == {"X 열림": ("open", 1), "Y 열림": ("open", 1), "Y 닫힘": ("preparing", 0)}
    hrefs = [a["href"] for c in cards.values() for a in c["attachments"]]
    assert len(hrefs) == 2
    for href in hrefs:  # 미리 보기에 보이는 href 는 강사도 연다
        assert (await client.get(href, headers=x_auth)).status_code == 200, href

    theirs, theirs_section = await course_with_section(db_session, title="Y 만의 강의")
    await _owned_session(client, admin, theirs.id, theirs_section.id, y)
    problem_of(
        await client.get(f"{ME}/courses/{theirs.id}/portal", headers=x_auth),
        403,
        "/problems/forbidden",
    )
    await _out_of_range(client, x_auth, ME + "/courses/{id}/portal")
    problem_of(await client.get(url, headers=admin), 403, "/problems/forbidden")


async def test_instructor_view_invite_code_and_notice(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    course, section = await course_with_section(db_session)
    await _owned_session(client, admin, course.id, section.id, x)
    other, other_section = await course_with_section(db_session, title="다른 강의")
    await _owned_session(client, admin, other.id, other_section.id, y)
    url = f"{ME}/courses/{course.id}/invite-code"
    admin_url = f"{ADMIN}/courses/{course.id}/invite-code"

    async def mine() -> dict[str, Any]:
        r = await client.get(url, headers=x_auth)
        assert r.status_code == 200, r.text
        body: dict[str, Any] = r.json()
        assert set(body) == CODE_KEYS
        return body

    async def admins() -> dict[str, Any]:
        r = await client.get(admin_url, headers=admin)
        assert r.status_code == 200, r.text
        body: dict[str, Any] = r.json()
        return body

    first = await mine()
    assert first == {**await admins(), "enrolled": 0}
    for n, email in enumerate(("a@example.com", "b@example.com")):
        r = await enter_learner(client, first["code"], email, f"수강생 {n}")
        assert r.status_code == 201, r.text
    assert await mine() == {**await admins(), "enrolled": 2}

    notice = await client.get(url + "/notice", headers=x_auth)
    assert notice.status_code == 200, notice.text
    assert set(notice.json()) == {"text"}
    admin_notice = await client.get(admin_url + "/notice", headers=admin)
    assert notice.json() == admin_notice.json()
    assert first["code"] in notice.json()["text"]

    r = await client.post(admin_url + ":reissue", headers=admin)
    assert r.status_code == 200, r.text
    reissued = await mine()
    assert reissued["code"] == r.json()["code"] != first["code"]
    assert reissued["enrolled"] == 2
    r = await client.post(admin_url + ":pause", headers=admin)
    assert r.status_code == 200, r.text
    assert (await mine())["state"] == "paused"

    for path in (url, url + "/notice"):
        problem_of(await client.get(path, headers=y_auth), 403, "/problems/forbidden")
    await _out_of_range(client, x_auth, ME + "/courses/{id}/invite-code")
    await _out_of_range(client, x_auth, ME + "/courses/{id}/invite-code/notice")


async def test_instructor_view_roster_minimal(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    course, code = await open_test_course(db_session)
    section = await add_section(client, admin, course.id)
    mine = await _owned_session(client, admin, course.id, section, x)
    other, other_section = await course_with_section(db_session, title="다른 강의")
    await _owned_session(client, admin, other.id, other_section.id, y)
    people = (
        ("kim@example.com", "김가명", "교육팀"),
        ("lee@example.com", "이가명", "인사팀"),
        ("park@example.com", "박가명", None),
    )
    for email, name, dept in people:
        extra = {} if dept is None else {"dept": dept}
        r = await enter_learner(client, code.code, email, name, **extra)
        assert r.status_code == 201, r.text

    url = f"{ME}/courses/{course.id}/enrollments"
    r = await client.get(url, headers=x_auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == PAGE_KEYS
    assert [set(i) for i in body["items"]] == [ROSTER_KEYS] * 3
    assert json_keys(body) & {"email", "learner_id", "phone", "id"} == set()
    for email, _, _ in people:
        assert email not in r.text
    r = await client.get(f"{ADMIN}/courses/{course.id}/enrollments", headers=admin)
    assert r.status_code == 200, r.text
    assert [(i["name"], i["dept"], i["enrolled_at"]) for i in body["items"]] == [
        (i["name"], i["dept"], i["enrolled_at"]) for i in r.json()["items"]
    ]
    assert {i["name"] for i in body["items"]} == {name for _, name, _ in people}

    first = (await client.get(url, headers=x_auth, params={"limit": 2})).json()
    assert (len(first["items"]), first["has_more"]) == (2, True)
    assert first["next_cursor"] is not None
    second = (
        await client.get(
            url, headers=x_auth, params={"limit": 2, "cursor": first["next_cursor"]}
        )
    ).json()
    assert (len(second["items"]), second["has_more"], second["next_cursor"]) == (
        1,
        False,
        None,
    )
    assert first["items"] + second["items"] == body["items"]  # 두 쪽이 겹치지 않는다

    bad = problem_of(
        await client.get(url, headers=x_auth, params={"cursor": "깨진커서"}), 422
    )
    assert locs(bad) == [["query", "cursor"]]
    problem_of(await client.get(url, headers=y_auth), 403, "/problems/forbidden")
    await _out_of_range(client, x_auth, ME + "/courses/{id}/enrollments")
    await _assign(client, admin, mine, y)  # 다시 배정되어 그 강의에 내 세션이 없다
    problem_of(await client.get(url, headers=x_auth), 403, "/problems/forbidden")


async def test_instructor_view_home_summary_and_todo(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _set_today(app, RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    running, rs = await course_with_section(
        db_session, title="진행 강의", start_on=date(2026, 11, 2), day_count=4
    )
    prep, ps = await course_with_section(
        db_session, title="준비 강의", start_on=date(2026, 11, 16)
    )
    ended, es = await course_with_section(
        db_session, title="종료 강의", start_on=date(2026, 10, 19)
    )
    archived, ars = await course_with_section(db_session, title="보관 강의")
    ready = await _owned_session(
        client, admin, running.id, rs.id, x, title="자료 있음", day_no=1, slot=1
    )
    empty = await _owned_session(
        client, admin, running.id, rs.id, x, title="자료 없음", day_no=2, slot=1
    )
    await _owned_session(
        client, admin, running.id, rs.id, y, title="Y 빈 세션", day_no=1, slot=2
    )
    waiting = await _owned_session(
        client, admin, prep.id, ps.id, x, title="준비 세션", day_no=1, slot=1
    )
    await _owned_session(client, admin, ended.id, es.id, x, title="끝난 세션")
    await _owned_session(client, admin, archived.id, ars.id, x, title="보관 세션")
    r = await client.post(f"{ADMIN}/courses/{archived.id}:archive", headers=admin)
    assert r.status_code == 200, r.text
    r = await link(client, x_auth, ready, "https://example.com/a")
    assert r.status_code == 201, r.text

    r = await client.get(f"{ME}/home", headers=x_auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == HOME_KEYS
    assert json_keys(body) & {"email", "learner_id"} == set()
    assert body["status"] == "approved"
    assert body["summary"] == {
        "courses": 3,
        "running": 1,
        "prep": 1,
        "ended": 1,
        "my_sessions": 4,
        "my_ready": 1,
    }
    assert set(body["summary"]) == SUMMARY_KEYS
    for item in body["courses"]:
        assert set(item) == HOME_COURSE_KEYS, item
    assert [
        (c["id"], c["status"], c["my_sessions"], c["my_ready"]) for c in body["courses"]
    ] == [
        (running.id, "running", 2, 1),
        (prep.id, "prep", 1, 0),
        (ended.id, "ended", 1, 0),
    ]
    for item in body["courses"]:
        r = await client.get(f"{ADMIN}/courses/{item['id']}/invite-code", headers=admin)
        assert r.status_code == 200, r.text
        assert (item["code"], item["code_state"]) == (
            r.json()["code"],
            r.json()["state"],
        )
    first = body["courses"][0]
    assert (first["title"], first["client_name"], first["course_type"]) == (
        "진행 강의",
        "A사",
        None,
    )
    assert (first["start_on"], first["end_on"]) == ("2026-11-02", "2026-11-05")
    assert body["courses_more"] is False
    for item in body["todo"]:
        assert set(item) == TODO_KEYS, item
    assert body["todo"] == [
        {
            "course_id": running.id,
            "course_title": "진행 강의",
            "section_id": rs.id,
            "section_title": rs.title,
            "session_id": empty,
            "session_title": "자료 없음",
            "day_no": 2,
            "slot": 1,
        },
        {
            "course_id": prep.id,
            "course_title": "준비 강의",
            "section_id": ps.id,
            "section_title": ps.title,
            "session_id": waiting,
            "session_title": "준비 세션",
            "day_no": 1,
            "slot": 1,
        },
    ]
    assert body["todo_more"] is False
    assert body["documents_missing"] == REQUIRED_DOCUMENTS
    assert body["capable"] == 0

    ax = await make_pool_course(db_session, source="ax")
    r = await client.put(f"{ME}/capabilities/{ax.id}", headers=x_auth, json={})
    assert r.status_code == 201, r.text
    r = await client.get(f"{ME}/home", headers=x_auth)
    assert r.json()["capable"] == 1


async def test_instructor_view_home_pending_empty(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await approved(
        db_session, app.state.settings, email="p@example.com", status="pending"
    )
    r = await client.get(f"{ME}/home", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "status": "pending",
        "summary": dict.fromkeys(SUMMARY_KEYS, 0),
        "courses": [],
        "courses_more": False,
        "todo": [],
        "todo_more": False,
        "records_todo": [],
        "records_todo_more": False,
        "surveys": [],
        "surveys_more": False,
        "documents_missing": REQUIRED_DOCUMENTS,
        "capable": 0,
    }
