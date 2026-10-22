"""강사의 배정 강의 열람과 내 세션 수정(/v1/me/courses · /v1/me/sessions, T5 계획 결정 i·xii·xiii · 증명 3·4·17).

강사에게 보이는 강의는 세션 하나라도 배정된 강의다. 그 안의 세션은 전부 읽기 전용으로 보고(남의 세션도 강사 이름),
첨부는 개수만이다. 고칠 수 있는 것은 내 세션의 설명·키워드·공개뿐이고 그 밖의 키는 422 extra_forbidden 이다.
판정 순서는 404(없음) → 403(범위 밖·남의 세션)이다. 픽스처 강의는 2026-11-02(월)부터, 하루 13:00~17:00 이다.
"""

from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.instructor import lock_instructor, update_instructor
from classfit.models import AuditLog, Course, CourseSession
from classfit.schemas.my_course import (
    MyCourseInfoOut,
    MyCourseOut,
    MySectionOut,
    MySessionOut,
)
from tests.fixtures.assign import approved, course_with_section
from tests.fixtures.courses import admin_headers, learner_headers
from tests.fixtures.enter import add_section, add_session, json_keys
from tests.fixtures.instructors import count, locs, problem_of

ADMIN = "/v1/admin"
MINE = "/v1/me/courses"
MISSING = 999_999_999


def _session_url(session_id: int) -> str:
    return f"/v1/me/sessions/{session_id}"


async def _assign(
    client: httpx.AsyncClient, auth: dict[str, str], session_id: int, iid: int | None
) -> None:
    r = await client.patch(
        f"{ADMIN}/sessions/{session_id}", headers=auth, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


async def _row(session: AsyncSession, session_id: int) -> tuple[Any, ...]:
    row = (
        await session.execute(
            select(
                CourseSession.section_id,
                CourseSession.title,
                CourseSession.description,
                CourseSession.keywords,
                CourseSession.is_open,
                CourseSession.day_no,
                CourseSession.slot,
                CourseSession.minutes,
                CourseSession.time_start,
                CourseSession.instructor_id,
            ).where(CourseSession.id == session_id)
        )
    ).one()
    return tuple(row)


async def test_instructor_session_title_patch_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    x, x_auth = await approved(db_session, app.state.settings, email="x@example.com")
    course, section = await course_with_section(db_session)
    sid = await add_session(
        client, auth, course.id, section_id=section.id, day_no=1, slot=1
    )
    await _assign(client, auth, sid, x)
    before = await _row(db_session, sid)

    for key, value in (
        ("title", "새 주제"),
        ("day_no", 2),
        ("slot", 2),
        ("minutes", 30),
        ("time_start", "09:00"),
        ("instructor_id", x),
        ("section_id", section.id),
    ):
        body = problem_of(
            await client.patch(_session_url(sid), headers=x_auth, json={key: value}),
            422,
        )
        assert locs(body) == [["body", key]], body
        assert [v["type"] for v in body["violations"]] == ["extra_forbidden"]
    for key in ("keywords", "is_open"):
        problem_of(
            await client.patch(_session_url(sid), headers=x_auth, json={key: None}), 422
        )
    assert await _row(db_session, sid) == before


async def test_instructor_session_other_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    a, _ = await approved(db_session, settings, email="a@example.com")
    b, b_auth = await approved(db_session, settings, email="b@example.com")
    course, section = await course_with_section(db_session)
    mine_a, mine_b, nobody = [
        await add_session(client, auth, course.id, section_id=section.id, title=t)
        for t in ("가", "나", "다")
    ]
    await _assign(client, auth, mine_a, a)
    await _assign(client, auth, mine_b, b)
    other, other_section = await course_with_section(db_session)
    await _assign(
        client,
        auth,
        await add_session(client, auth, other.id, section_id=other_section.id),
        a,
    )
    before = [await _row(db_session, s) for s in (mine_a, nobody)]

    for sid in (mine_a, nobody):
        problem_of(
            await client.patch(
                _session_url(sid), headers=b_auth, json={"description": "남의 것"}
            ),
            403,
            "/problems/forbidden",
        )
    problem_of(
        await client.patch(
            _session_url(MISSING), headers=b_auth, json={"description": "x"}
        ),
        404,
        "/problems/not_found",
    )
    assert [await _row(db_session, s) for s in (mine_a, nobody)] == before

    # 같은 강의의 남의 세션은 읽기는 된다(쓰기만 403)
    r = await client.get(f"{MINE}/{course.id}", headers=b_auth)
    assert r.status_code == 200, r.text
    seen = {s["id"] for sec in r.json()["sections"] for s in sec["sessions"]}
    assert seen == {mine_a, mine_b, nobody}
    for url in (f"{MINE}/{other.id}", f"{MINE}/{other.id}/schedule"):
        problem_of(await client.get(url, headers=b_auth), 403, "/problems/forbidden")
    for url in (f"{MINE}/{MISSING}", f"{MINE}/{MISSING}/schedule"):
        problem_of(await client.get(url, headers=b_auth), 404, "/problems/not_found")


async def test_instructor_session_patch_own_fields(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    x, x_auth = await approved(db_session, app.state.settings, email="x@example.com")
    course, section = await course_with_section(db_session)
    sid = await add_session(
        client, auth, course.id, section_id=section.id, day_no=1, slot=1
    )
    await _assign(client, auth, sid, x)
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={"kind": "link", "title": "자료", "url": "https://example.com/a"},
    )
    assert r.status_code == 201, r.text
    audits = await count(db_session, AuditLog)
    change = {"description": "새 설명", "keywords": ["보안", "AI"], "is_open": True}

    r = await client.patch(_session_url(sid), headers=x_auth, json=change)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == set(MySessionOut.model_fields)
    assert {k: body[k] for k in change} == change
    assert (body["instructor_id"], body["attachments"]) == (x, 1)
    row = await _row(db_session, sid)
    assert (row[2], list(row[3]), row[4]) == ("새 설명", ["보안", "AI"], True)
    assert await count(db_session, AuditLog) == audits
    r = await client.patch(_session_url(sid), headers=x_auth, json=change)  # 같은 값
    assert r.status_code == 200, r.text

    learner = await learner_headers(db_session, course.id)
    r = await client.get(f"/v1/learner/courses/{course.id}/portal", headers=learner)
    assert r.status_code == 200, r.text
    cards = {s["id"]: s for sec in r.json()["sections"] for s in sec["sessions"]}
    assert cards[sid]["state"] == "open"
    assert (cards[sid]["description"], cards[sid]["keywords"]) == (
        "새 설명",
        ["보안", "AI"],
    )


async def test_instructor_session_courses_list_scope(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    _, y_auth = await approved(db_session, settings, email="y@example.com")
    courses = [await course_with_section(db_session) for _ in range(4)]
    (c1, s1), (c2, s2), (c3, s3), (c4, s4) = courses
    for course, section, mine in ((c1, s1, 2), (c2, s2, 1), (c3, s3, 0), (c4, s4, 1)):
        made = [
            await add_session(client, auth, course.id, section_id=section.id)
            for _ in range(2)
        ]
        for sid in made[:mine]:
            await _assign(client, auth, sid, x)
    r = await client.post(f"{ADMIN}/courses/{c2.id}:archive", headers=auth)
    assert r.status_code == 200, r.text
    created = dict(
        (
            await db_session.execute(
                select(Course.id, Course.created_at).where(
                    Course.id.in_([c1.id, c4.id])
                )
            )
        ).all()
    )
    order = sorted(created, key=lambda i: (created[i], i), reverse=True)

    r = await client.get(MINE, headers=x_auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["has_more"], body["next_cursor"]) == (False, None)
    assert [i["id"] for i in body["items"]] == order
    for item in body["items"]:
        assert set(item) == set(MyCourseOut.model_fields)
    assert {i["id"]: i["my_sessions"] for i in body["items"]} == {c1.id: 2, c4.id: 1}

    first = (await client.get(MINE, headers=x_auth, params={"limit": 1})).json()
    assert (len(first["items"]), first["has_more"]) == (1, True)
    assert first["next_cursor"] is not None
    second = (
        await client.get(
            MINE, headers=x_auth, params={"limit": 1, "cursor": first["next_cursor"]}
        )
    ).json()
    assert (len(second["items"]), second["has_more"], second["next_cursor"]) == (
        1,
        False,
        None,
    )
    assert [i["id"] for i in first["items"] + second["items"]] == order

    r = await client.get(MINE, headers=x_auth, params={"archived": "true"})
    assert [i["id"] for i in r.json()["items"]] == [c2.id]
    r = await client.get(MINE, headers=y_auth)
    assert r.json()["items"] == []
    body = problem_of(
        await client.get(MINE, headers=x_auth, params={"cursor": "깨진커서"}), 422
    )
    assert locs(body) == [["query", "cursor"]]


async def test_instructor_session_detail_and_schedule(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    a, a_auth = await approved(db_session, settings, email="a@example.com")
    b, _ = await approved(db_session, settings, email="b@example.com")
    row = await lock_instructor(db_session, b)
    assert row is not None
    await update_instructor(db_session, row, name="가명 나")
    course, section = await course_with_section(db_session)
    other_section = await add_section(client, auth, course.id, "2부")
    mine = await add_session(
        client,
        auth,
        course.id,
        section_id=section.id,
        title="내 세션",
        day_no=1,
        slot=1,
    )
    theirs = await add_session(
        client,
        auth,
        course.id,
        section_id=other_section,
        title="남의 세션",
        day_no=1,
        slot=2,
    )
    undated = await add_session(
        client, auth, course.id, section_id=other_section, title="미정"
    )
    await _assign(client, auth, mine, a)
    await _assign(client, auth, theirs, b)
    r = await client.post(
        f"{ADMIN}/sessions/{mine}/attachments",
        headers=auth,
        data={"kind": "link", "title": "자료", "url": "https://example.com/a"},
    )
    assert r.status_code == 201, r.text

    admin_schedule = await client.get(
        f"{ADMIN}/courses/{course.id}/schedule", headers=auth
    )
    assert admin_schedule.status_code == 200, admin_schedule.text
    times = {
        s["id"]: (day["date"], s["start"], s["end"])
        for day in admin_schedule.json()["days"]
        for s in day["sessions"]
    }
    times |= {
        s["id"]: (None, s["start"], s["end"]) for s in admin_schedule.json()["undated"]
    }
    assert times[mine] == ("2026-11-02", "13:00", "13:50")

    r = await client.get(f"{MINE}/{course.id}", headers=a_auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"course", "sections"}
    assert set(body["course"]) == set(MyCourseInfoOut.model_fields)
    assert body["course"]["id"] == course.id
    assert json_keys(body) & {"href", "email", "phone"} == set()
    sessions = {}
    for sec in body["sections"]:
        assert set(sec) == set(MySectionOut.model_fields)
        for item in sec["sessions"]:
            assert set(item) == set(MySessionOut.model_fields)
            sessions[item["id"]] = item
    assert {
        sid: (s["instructor_id"], s["instructor_name"], s["attachments"])
        for sid, s in sessions.items()
    } == {mine: (a, "강사", 1), theirs: (b, "가명 나", 0), undated: (None, None, 0)}
    # 시각은 관리자 일정표와 같은 계산이다
    assert {
        sid: (s["date"], s["start"], s["end"]) for sid, s in sessions.items()
    } == times

    mine_schedule = await client.get(f"{MINE}/{course.id}/schedule", headers=a_auth)
    assert mine_schedule.status_code == 200, mine_schedule.text
    assert mine_schedule.json() == admin_schedule.json()


async def test_instructor_session_reassigned_loses_access(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    a, a_auth = await approved(db_session, settings, email="a@example.com")
    b, b_auth = await approved(db_session, settings, email="b@example.com")
    course, section = await course_with_section(db_session)
    sid = await add_session(client, auth, course.id, section_id=section.id)
    await _assign(client, auth, sid, a)
    r = await client.patch(_session_url(sid), headers=a_auth, json={"description": "A"})
    assert r.status_code == 200, r.text

    await _assign(client, auth, sid, b)
    problem_of(
        await client.patch(
            _session_url(sid), headers=a_auth, json={"description": "A2"}
        ),
        403,
        "/problems/forbidden",
    )
    assert (await client.get(MINE, headers=a_auth)).json()["items"] == []
    problem_of(await client.get(f"{MINE}/{course.id}", headers=a_auth), 403)
    r = await client.patch(_session_url(sid), headers=b_auth, json={"description": "B"})
    assert r.status_code == 200, r.text
    assert (await _row(db_session, sid))[2] == "B"
