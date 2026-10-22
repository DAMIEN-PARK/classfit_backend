"""일정 끝점: 일차 PUT(다시 매김·기간 따라감)·PATCH(순서 409)·DELETE(세션 일차 미정), 세션의 없는 일차 409,
다른 강의 섹션 404, 일정표 시각(rules.schedule 규칙: 교시+휴식 · 길이 · 예외 시각 · 점심 밀기 · 그날 끝 자름).

픽스처 강의는 2026-11-02(월)부터 평일 4일 · 13:00~17:00 · 교시 50분 · 휴식 10분이다.
"""

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import CourseDay, CourseSession, Section
from tests.fixtures.courses import admin_headers, open_test_course

URL = "/v1/admin/courses"


def _problem(r: httpx.Response, status: int) -> dict:
    assert r.status_code == status, (r.status_code, r.text)
    assert r.headers["content-type"].startswith("application/problem+json")
    return r.json()


async def _section(
    client: httpx.AsyncClient, auth: dict, course_id: int, title: str = "1부"
) -> int:
    r = await client.post(
        f"{URL}/{course_id}/sections", headers=auth, json={"title": title}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _session(
    client: httpx.AsyncClient,
    auth: dict,
    course_id: int,
    section_id: int,
    **body: object,
) -> int:
    r = await client.post(
        f"{URL}/{course_id}/sections/{section_id}/sessions",
        headers=auth,
        json={"title": "세션", **body},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _times(schedule: dict) -> dict[int, tuple[int | None, str | None, str | None]]:
    """세션 id → (일차, 시작, 끝). 일차 미정은 일차 None."""
    out = {
        s["id"]: (d["day_no"], s["start"], s["end"])
        for d in schedule["days"]
        for s in d["sessions"]
    }
    out.update({s["id"]: (None, s["start"], s["end"]) for s in schedule["undated"]})
    return out


async def test_schedule_put_days_renumbers_and_period_follows(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    sec = await _section(client, auth, course.id)
    on_day4 = await _session(client, auth, course.id, sec, day_no=4, slot=1)
    on_day1 = await _session(client, auth, course.id, sec, day_no=1, slot=1)
    days = [
        {"date": "2026-11-09", "start_time": "09:00", "end_time": "12:00"},
        {"date": "2026-11-10", "start_time": "09:00", "end_time": "12:00"},
    ]
    r = await client.put(f"{URL}/{course.id}/days", headers=auth, json={"days": days})
    assert r.status_code == 200, r.text
    schedule = r.json()
    assert [(d["day_no"], d["date"]) for d in schedule["days"]] == [
        (1, "2026-11-09"),
        (2, "2026-11-10"),
    ]
    got = (await client.get(f"{URL}/{course.id}", headers=auth)).json()
    assert (got["start_on"], got["end_on"]) == ("2026-11-09", "2026-11-10")
    times = _times(schedule)
    assert times[on_day4] == (None, None, None)  # 없어진 일차 → 일차 미정
    assert times[on_day1] == (1, "09:00", "09:50")
    row = await db_session.get(CourseSession, on_day4, populate_existing=True)
    assert row is not None and (row.day_no, row.slot) == (None, None)


async def test_schedule_put_days_not_ascending_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    day = {"start_time": "09:00", "end_time": "12:00"}
    for dates in (["2026-11-10", "2026-11-09"], ["2026-11-09", "2026-11-09"]):
        body = {"days": [{**day, "date": d} for d in dates]}
        _problem(
            await client.put(f"{URL}/{course.id}/days", headers=auth, json=body), 422
        )
    too_many = {
        "days": [
            {**day, "date": f"2027-{m:02d}-{d:02d}"}
            for m in (1, 2, 3)
            for d in range(1, 22)
        ]
    }
    _problem(
        await client.put(f"{URL}/{course.id}/days", headers=auth, json=too_many), 422
    )
    count = (
        select(func.count())
        .select_from(CourseDay)
        .where(CourseDay.course_id == course.id)
    )
    assert await db_session.scalar(count) == 4


async def test_schedule_patch_day_out_of_order_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)  # 11-02 · 11-03 · 11-04 · 11-05
    day2 = f"{URL}/{course.id}/days/2"
    for date in ("2026-11-01", "2026-11-02", "2026-11-04"):
        body = _problem(
            await client.patch(day2, headers=auth, json={"date": date}), 409
        )
        assert body["type"] == "/problems/conflict"
    _problem(
        await client.patch(
            f"{URL}/{course.id}/days/1", headers=auth, json={"start_time": "18:00"}
        ),
        409,
    )
    _problem(
        await client.patch(
            f"{URL}/{course.id}/days/9", headers=auth, json={"date": "2026-11-20"}
        ),
        404,
    )
    # 대조: 순서를 지키면 200 이고 기간이 따라간다
    r = await client.patch(
        f"{URL}/{course.id}/days/4", headers=auth, json={"date": "2026-11-06"}
    )
    assert r.status_code == 200, r.text
    got = (await client.get(f"{URL}/{course.id}", headers=auth)).json()
    assert (got["start_on"], got["end_on"]) == ("2026-11-02", "2026-11-06")


async def test_schedule_delete_day_unsets_sessions(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    sec = await _section(client, auth, course.id)
    on_day2 = await _session(client, auth, course.id, sec, day_no=2, slot=1)
    r = await client.delete(f"{URL}/{course.id}/days/2", headers=auth)
    assert r.status_code == 204
    schedule = (await client.get(f"{URL}/{course.id}/schedule", headers=auth)).json()
    assert [d["day_no"] for d in schedule["days"]] == [
        1,
        3,
        4,
    ]  # 번호를 다시 매기지 않는다
    assert _times(schedule)[on_day2] == (None, None, None)
    row = await db_session.get(CourseSession, on_day2, populate_existing=True)
    assert row is not None and (row.day_no, row.slot) == (None, None)
    _problem(await client.delete(f"{URL}/{course.id}/days/2", headers=auth), 404)
    # 끝 일차를 지우면 종료일이 따라간다
    assert (
        await client.delete(f"{URL}/{course.id}/days/4", headers=auth)
    ).status_code == 204
    assert (await client.get(f"{URL}/{course.id}", headers=auth)).json()[
        "end_on"
    ] == "2026-11-04"


async def test_schedule_session_unknown_day_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    sec = await _section(client, auth, course.id)
    url = f"{URL}/{course.id}/sections/{sec}/sessions"
    body = _problem(
        await client.post(
            url, headers=auth, json={"title": "x", "day_no": 9, "slot": 1}
        ),
        409,
    )
    assert body["type"] == "/problems/conflict"
    _problem(
        await client.post(url, headers=auth, json={"title": "x", "slot": 1}), 422
    )  # 일차 없는 교시
    existing = await _session(client, auth, course.id, sec, day_no=1, slot=1)
    _problem(
        await client.patch(
            f"/v1/admin/sessions/{existing}", headers=auth, json={"day_no": 9}
        ),
        409,
    )
    _problem(
        await client.patch(
            f"/v1/admin/sessions/{existing}", headers=auth, json={"time_start": "09:00"}
        ),
        409,
    )
    moved = await client.patch(
        f"/v1/admin/sessions/{existing}", headers=auth, json={"day_no": None}
    )
    assert (moved.status_code, moved.json()["day_no"], moved.json()["slot"]) == (
        200,
        None,
        None,
    )
    count = (
        select(func.count())
        .select_from(CourseSession)
        .where(CourseSession.section_id == sec)
    )
    assert await db_session.scalar(count) == 1


async def test_schedule_session_other_course_section_404(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    a, _ = await open_test_course(db_session, title="A 강의")
    b, _ = await open_test_course(db_session, title="B 강의")
    sec_a = await _section(client, auth, a.id)
    other = f"{URL}/{b.id}/sections/{sec_a}"
    _problem(
        await client.post(f"{other}/sessions", headers=auth, json={"title": "x"}), 404
    )
    _problem(await client.patch(other, headers=auth, json={"title": "y"}), 404)
    _problem(await client.delete(other, headers=auth), 404)
    _problem(
        await client.post(f"{URL}/999999/sections", headers=auth, json={"title": "z"}),
        404,
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Section).where(Section.id == sec_a)
        )
        == 1
    )
    # 대조: 제 강의 경로면 된다
    assert (
        await client.patch(
            f"{URL}/{a.id}/sections/{sec_a}", headers=auth, json={"title": "y"}
        )
    ).status_code == 200


async def test_schedule_times_follow_rules(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    cid = course.id
    sec_a = await _section(client, auth, cid, "A")
    sec_b = await _section(client, auth, cid, "B")
    # 1일차 13:00~17:00: 교시 50 + 휴식 10, 길이 90 이 끼면 뒤가 밀린다. 예외 시각은 그 값. 섹션마다 따로 센다
    a1 = await _session(client, auth, cid, sec_a, day_no=1, slot=1)
    a2 = await _session(client, auth, cid, sec_a, day_no=1, slot=2, minutes=90)
    a3 = await _session(client, auth, cid, sec_a, day_no=1, slot=3)
    a_fixed = await _session(
        client, auth, cid, sec_a, day_no=1, time_start="09:00", time_end="10:00"
    )
    b1 = await _session(client, auth, cid, sec_b, day_no=1, slot=1)
    # 2일차 09:00~18:00 · 점심 12:00~13:00: 넷째 교시는 점심 뒤로 민다
    r = await client.patch(
        f"{URL}/{cid}/days/2",
        headers=auth,
        json={
            "start_time": "09:00",
            "end_time": "18:00",
            "lunch_start": "12:00",
            "lunch_end": "13:00",
        },
    )
    assert r.status_code == 200, r.text
    d2 = [
        await _session(client, auth, cid, sec_a, day_no=2, slot=n) for n in (1, 2, 3, 4)
    ]
    # 3일차: 300분은 그날 끝(17:00)에서 자르고, 교시 없는 세션은 시각을 못 정한다
    long = await _session(client, auth, cid, sec_a, day_no=3, slot=1, minutes=300)
    no_slot = await _session(client, auth, cid, sec_a, day_no=3)
    undated = await _session(client, auth, cid, sec_b)

    times = _times((await client.get(f"{URL}/{cid}/schedule", headers=auth)).json())
    assert times[a1] == (1, "13:00", "13:50")
    assert times[a2] == (1, "14:00", "15:30")
    assert times[a3] == (1, "15:40", "16:30")
    assert times[a_fixed] == (1, "09:00", "10:00")
    assert times[b1] == (1, "13:00", "13:50")
    assert [times[s] for s in d2] == [
        (2, "09:00", "09:50"),
        (2, "10:00", "10:50"),
        (2, "11:00", "11:50"),
        (2, "13:00", "13:50"),
    ]
    assert times[long] == (3, "13:00", "17:00")
    assert times[no_slot] == (3, None, None)
    assert times[undated] == (None, None, None)
