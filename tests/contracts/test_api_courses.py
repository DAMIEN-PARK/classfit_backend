"""강의 끝점(/v1/admin/courses …): 개설 한 트랜잭션, 403·422, 목록 커서·필터, 상태(KST 경계·수동 지정·되돌리기),
일차가 있는 강의의 기간 409, 보관, 삭제 CASCADE. 오늘은 app.dependency_overrides[today] 로 준다(Design 5절 15).
"""

import re
from datetime import UTC, date, datetime

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.core.clock import today_kst
from classfit.models import (
    AuditLog,
    Course,
    CourseDay,
    CourseSession,
    InviteCode,
    Section,
)
from classfit.service.rules.invite import INVITE_ALPHABET, INVITE_LENGTH
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course

URL = "/v1/admin/courses"
BODY = {
    "start": "blank",
    "title": "AI 활용 기초",
    "client_name": "A사",
    "method": "집체",
    "hours_per_person": 16,
    "start_on": "2026-11-02",
    "day_count": 4,
    "day_start": "13:00",
    "day_end": "17:00",
}


def _set_today(app: FastAPI, d: date) -> None:
    app.dependency_overrides[today] = lambda: d


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return (
        await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    )


def _problem(r: httpx.Response, status: int) -> dict:
    assert r.status_code == status, (r.status_code, r.text)
    assert r.headers["content-type"].startswith("application/problem+json")
    return r.json()


async def test_courses_open_creates_days_and_one_code(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 10, 22))
    r = await client.post(URL, headers=auth, json=BODY)
    assert r.status_code == 201, r.text
    course, code = r.json()["course"], r.json()["invite_code"]
    assert (course["start_on"], course["end_on"], course["status"]) == (
        "2026-11-02",
        "2026-11-05",
        "prep",
    )
    assert (code["status"], code["state"], code["expires_on"]) == (
        "active",
        "active",
        "2026-12-05",
    )
    assert re.fullmatch(f"[{INVITE_ALPHABET}]{{{INVITE_LENGTH}}}", code["code"])

    cid = course["id"]
    dates = (
        await db_session.scalars(
            select(CourseDay.date)
            .where(CourseDay.course_id == cid)
            .order_by(CourseDay.day_no)
        )
    ).all()
    assert [d.isoformat() for d in dates] == [
        "2026-11-02",
        "2026-11-03",
        "2026-11-04",
        "2026-11-05",
    ]
    assert await _count(db_session, InviteCode, InviteCode.course_id == cid) == 1
    audits = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "course.open")
            )
        )
        .scalars()
        .all()
    )
    assert [(a.actor, a.target_type, a.target_id) for a in audits] == [
        (f"admin:{admin_id}", "course", str(cid))
    ]


async def test_courses_open_failure_leaves_no_rows(
    client_noraise: httpx.AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("코드 발급 실패(시험)")

    monkeypatch.setattr("classfit.service.courses.open.issue_invite_code", boom)
    _, auth = await admin_headers(db_session)
    r = await client_noraise.post(URL, headers=auth, json=BODY)
    _problem(r, 500)
    assert await _count(db_session, Course) == 0
    assert await _count(db_session, CourseDay) == 0
    assert await _count(db_session, InviteCode) == 0
    assert await _count(db_session, AuditLog) == 0


async def test_courses_non_admin_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    course, _ = await open_test_course(db_session)
    learner = await learner_headers(db_session, course.id)
    _problem(await client.post(URL, headers=learner, json=BODY), 403)
    _problem(await client.get(URL, headers=learner), 403)
    _problem(await client.get(f"{URL}/{course.id}", headers=learner), 403)
    assert await _count(db_session, Course) == 1  # 픽스처 강의만


async def test_courses_invalid_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    missing = _problem(
        await client.post(
            URL, headers=auth, json={"start": "blank", "client_name": "A사"}
        ),
        422,
    )
    assert ["body", "title"] in [v["loc"] for v in missing["violations"]]
    no_end = {**BODY, "day_count": 0}
    _problem(await client.post(URL, headers=auth, json=no_end), 422)
    end_with_days = {**BODY, "end_on": "2026-11-20"}
    _problem(await client.post(URL, headers=auth, json=end_with_days), 422)
    _problem(await client.post(URL, headers=auth, json={**BODY, "start": "copy"}), 422)
    _problem(await client.post(URL, headers=auth, json={**BODY, "day_count": 41}), 422)
    assert await _count(db_session, Course) == 0


async def test_courses_list_bad_cursor_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    for bad in ("@@", "abc", "eyJ0IjoxfQ"):  # 알파벳 밖 · JSON 아님 · 칸 빠짐
        body = _problem(
            await client.get(URL, headers=auth, params={"cursor": bad}), 422
        )
        assert [v["loc"] for v in body["violations"]] == [["query", "cursor"]], bad


async def test_courses_list_keyset_has_more(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 10, 22))
    ids = [
        (await open_test_course(db_session, title=f"강의 {n}"))[0].id for n in range(3)
    ]
    first = (await client.get(URL, headers=auth, params={"limit": 2})).json()
    assert (len(first["items"]), first["has_more"]) == (2, True) and first[
        "next_cursor"
    ]
    second = (
        await client.get(
            URL, headers=auth, params={"limit": 2, "cursor": first["next_cursor"]}
        )
    ).json()
    assert (len(second["items"]), second["has_more"], second["next_cursor"]) == (
        1,
        False,
        None,
    )
    seen = [c["id"] for c in first["items"] + second["items"]]
    assert seen == sorted(
        ids, reverse=True
    )  # 같은 created_at 은 id 내림차순, 빠짐·겹침 없음


async def test_courses_list_status_filter_matches_item_status(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 11, 10))

    async def open_period(start: date, end: date) -> int:
        return (
            await open_test_course(db_session, day_count=0, start_on=start, end_on=end)
        )[0].id

    ended = await open_period(date(2026, 10, 1), date(2026, 10, 5))
    running = await open_period(date(2026, 11, 9), date(2026, 11, 12))
    ends_today = await open_period(
        date(2026, 11, 3), date(2026, 11, 10)
    )  # 종료일 당일은 running
    prep = await open_period(date(2026, 12, 1), date(2026, 12, 3))
    manual = await open_period(date(2026, 12, 1), date(2026, 12, 3))
    await client.post(
        f"{URL}/{manual}:set-status", headers=auth, json={"status": "ended"}
    )

    expected = {
        "prep": {prep},
        "running": {running, ends_today},
        "ended": {ended, manual},
    }
    for status, want in expected.items():
        items = (await client.get(URL, headers=auth, params={"status": status})).json()[
            "items"
        ]
        assert {c["id"] for c in items} == want, status
        assert {c["status"] for c in items} == {status}


async def test_course_status_kst_boundary_utc_15(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)  # 시작 2026-11-02
    url = f"{URL}/{course.id}"
    app.dependency_overrides[today] = lambda: today_kst(
        datetime(2026, 11, 1, 14, 59, tzinfo=UTC)
    )
    assert (await client.get(url, headers=auth)).json()[
        "status"
    ] == "prep"  # KST 11-01 23:59
    app.dependency_overrides[today] = lambda: today_kst(
        datetime(2026, 11, 1, 15, 0, tzinfo=UTC)
    )
    assert (await client.get(url, headers=auth)).json()[
        "status"
    ] == "running"  # KST 11-02 00:00


async def test_course_status_set_status_manual_wins(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 10, 22))  # 날짜로는 prep
    course, _ = await open_test_course(db_session)
    r = await client.post(
        f"{URL}/{course.id}:set-status", headers=auth, json={"status": "ended"}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["status_manual"]) == ("ended", True)
    assert (await client.get(f"{URL}/{course.id}", headers=auth)).json()[
        "status"
    ] == "ended"
    _problem(
        await client.post(
            f"{URL}/{course.id}:set-status", headers=auth, json={"status": "done"}
        ),
        422,
    )
    assert (
        await _count(db_session, AuditLog, AuditLog.action == "course.set_status") == 1
    )


async def test_course_status_reset_status_date_rule_wins(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 11, 3))  # 날짜로는 running
    course, _ = await open_test_course(db_session)
    await client.post(
        f"{URL}/{course.id}:set-status", headers=auth, json={"status": "ended"}
    )
    r = await client.post(f"{URL}/{course.id}:reset-status", headers=auth)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["status_manual"]) == ("running", False)
    assert (
        await _count(db_session, AuditLog, AuditLog.action == "course.reset_status")
        == 1
    )


async def test_courses_patch_period_with_days_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _set_today(app, date(2026, 10, 22))
    with_days, _ = await open_test_course(db_session)
    body = _problem(
        await client.patch(
            f"{URL}/{with_days.id}", headers=auth, json={"start_on": "2026-11-03"}
        ),
        409,
    )
    assert body["type"] == "/problems/conflict"
    ok = await client.patch(
        f"{URL}/{with_days.id}", headers=auth, json={"title": "새 이름"}
    )
    assert (ok.status_code, ok.json()["title"], ok.json()["start_on"]) == (
        200,
        "새 이름",
        "2026-11-02",
    )
    # 대조: 일차가 없으면 기간을 바꿀 수 있다. 뒤집히면 409, 본문에서 뒤집히면 422
    no_days, _ = await open_test_course(
        db_session, day_count=0, end_on=date(2026, 11, 6)
    )
    moved = await client.patch(
        f"{URL}/{no_days.id}", headers=auth, json={"end_on": "2026-11-20"}
    )
    assert (moved.status_code, moved.json()["end_on"]) == (200, "2026-11-20")
    _problem(
        await client.patch(
            f"{URL}/{no_days.id}", headers=auth, json={"start_on": "2026-12-01"}
        ),
        409,
    )
    _problem(
        await client.patch(
            f"{URL}/{no_days.id}",
            headers=auth,
            json={"start_on": "2026-12-01", "end_on": "2026-11-01"},
        ),
        422,
    )
    _problem(
        await client.patch(f"{URL}/{no_days.id}", headers=auth, json={"title": None}),
        422,
    )

    # 같은 값 PATCH 는 200 이고 audit 이 없다(일차가 있어도 기간이 그대로면 409 아님). audit fields 는 바뀐 칸만
    same = await client.patch(
        f"{URL}/{with_days.id}",
        headers=auth,
        json={"title": "새 이름", "start_on": "2026-11-02"},
    )
    assert same.status_code == 200, same.text
    audits = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.action == "course.update")
                .order_by(AuditLog.id)
            )
        )
        .scalars()
        .all()
    )
    assert [a.detail["fields"] for a in audits] == [["title"], ["end_on"]]


async def test_courses_archive_hidden_from_default_list(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    kept, _ = await open_test_course(db_session, title="둔 강의")
    archived, _ = await open_test_course(db_session, title="보관 강의")
    r = await client.post(f"{URL}/{archived.id}:archive", headers=auth)
    assert r.status_code == 200 and r.json()["archived_at"] is not None
    default = (await client.get(URL, headers=auth)).json()["items"]
    assert [c["id"] for c in default] == [kept.id]
    only_archived = (
        await client.get(URL, headers=auth, params={"archived": "true"})
    ).json()["items"]
    assert [c["id"] for c in only_archived] == [archived.id]


async def test_courses_delete_cascades(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="남는 강의")
    sec = (
        await client.post(
            f"{URL}/{course.id}/sections", headers=auth, json={"title": "1부"}
        )
    ).json()
    ses = (
        await client.post(
            f"{URL}/{course.id}/sections/{sec['id']}/sessions",
            headers=auth,
            json={"title": "도입", "day_no": 1, "slot": 1},
        )
    ).json()

    r = await client.delete(f"{URL}/{course.id}", headers=auth)
    assert r.status_code == 204
    assert await _count(db_session, Course, Course.id == course.id) == 0
    assert await _count(db_session, CourseDay, CourseDay.course_id == course.id) == 0
    assert await _count(db_session, Section, Section.id == sec["id"]) == 0
    assert await _count(db_session, CourseSession, CourseSession.id == ses["id"]) == 0
    assert await _count(db_session, InviteCode, InviteCode.course_id == course.id) == 0
    assert (
        await _count(db_session, CourseDay, CourseDay.course_id == other.id) == 4
    )  # 다른 강의는 그대로
    _problem(await client.get(f"{URL}/{course.id}", headers=auth), 404)
    _problem(await client.delete(f"{URL}/{course.id}", headers=auth), 404)
    assert await _count(db_session, AuditLog, AuditLog.action == "course.delete") == 1
