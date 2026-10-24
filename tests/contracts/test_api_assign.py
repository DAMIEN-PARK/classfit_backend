"""관리자 배정·풀에서 고르기·배정 후보·포털 강사 이름(T5 계획 결정 i·vi·vii·viii·xiv·xv·xvi·xx · 증명 1·13~16).

배정은 승인 강사만이다(대기·반려·정지 409 + instructor_status, 같은 값이어도 상태를 먼저 본다). 배정이 바뀐 요청마다
audit session.assign 1행 + 새 강사에게 outbox session_assigned 1행이다. 풀에서 고르기는 그 섹션의 빈 교시에 차례로
넣는다(픽스처 강의는 하루 13:00~17:00 · 50분 + 10분 → 4교시). 포털 카드에는 강사 이름 칸 하나만 나간다.
"""

from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.instructor import lock_instructor, update_instructor
from classfit.models import (
    AuditLog,
    CourseSession,
    MailOutbox,
    Section,
    SessionAttachment,
)
from tests.fixtures.assign import approved, course_with_section, pool_session
from tests.fixtures.courses import admin_headers, learner_headers
from tests.fixtures.enter import PERSONAL_KEYS, add_section, add_session, json_keys
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.pool import make_pool_course, set_flags

ADMIN = "/v1/admin"
MISSING = 999_999_999
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422(codex 구현 리뷰 1차)
X_NAME = "가명 배정"
# 포털 응답의 허용 키(결정 xiv — 교집합이 아니라 집합을 정확히 잰다)
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
INSTRUCTOR_KEYS = {"instructor_id", "phone", "email"}
DETAIL_KEYS = {
    "instructor_id",
    "sessions",
    "course_title",
    "materials",
    "skipped_missing",
}
BULK_KEYS = {"section_id", "instructor_id", "changed", "materials", "skipped_missing"}
CANDIDATE_KEYS = {"instructor_id", "name", "org", "recommended", "assigned_sessions"}


def _assign_url(course_id: int, section_id: int) -> str:
    return f"{ADMIN}/courses/{course_id}/sections/{section_id}:assign"


def _from_pool_url(course_id: int, section_id: int) -> str:
    return f"{ADMIN}/courses/{course_id}/sections/{section_id}/sessions:from-pool"


async def _instructor_of(session: AsyncSession, session_id: int) -> int | None:
    return await session.scalar(
        select(CourseSession.instructor_id).where(CourseSession.id == session_id)
    )


async def _audits(session: AsyncSession) -> list[tuple[int, str, str, str, Any]]:
    """session.assign audit 의 (id, actor, target_type, target_id, detail), id 순."""
    rows = await session.execute(
        select(
            AuditLog.id,
            AuditLog.actor,
            AuditLog.target_type,
            AuditLog.target_id,
            AuditLog.detail,
        )
        .where(AuditLog.action == "session.assign")
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _outbox(session: AsyncSession) -> list[tuple[dict[str, Any], str]]:
    """session_assigned outbox 의 (params, to), id 순."""
    rows = await session.execute(
        select(MailOutbox.params, MailOutbox.to)
        .where(MailOutbox.kind == "session_assigned")
        .order_by(MailOutbox.id)
    )
    return [tuple(r) for r in rows]


async def _course_sessions(session: AsyncSession, course_id: int) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(CourseSession)
            .join(Section, Section.id == CourseSession.section_id)
            .where(Section.course_id == course_id)
        )
        or 0
    )


async def test_assign_unapproved_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    x, _ = await approved(db_session, settings, email="x@example.com")
    blocked: dict[int, str] = {}
    for status in ("pending", "rejected", "suspended"):
        iid, _ = await approved(
            db_session, settings, email=f"{status}@example.com", status=status
        )
        blocked[iid] = status
    course, section = await course_with_section(db_session)
    ax = await make_pool_course(db_session, source="ax")
    first = await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    second = await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    sids = [first.id, second.id]

    for iid, status in blocked.items():
        for r in (
            await client.patch(
                f"{ADMIN}/sessions/{first.id}",
                headers=auth,
                json={"instructor_id": iid},
            ),
            await client.post(
                _assign_url(course.id, section.id),
                headers=auth,
                json={"instructor_id": iid},
            ),
        ):
            body = problem_of(r, 409, "/problems/conflict")
            assert body["instructor_status"] == status, (iid, body)
    assert [await _instructor_of(db_session, s) for s in sids] == [None, None]
    assert await count(db_session, SessionAttachment) == 0
    assert await _audits(db_session) == []
    assert await _outbox(db_session) == []

    r = await client.patch(
        f"{ADMIN}/sessions/{first.id}", headers=auth, json={"instructor_id": x}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        _assign_url(course.id, section.id), headers=auth, json={"instructor_id": x}
    )
    assert r.status_code == 200, r.text
    assert [await _instructor_of(db_session, s) for s in sids] == [x, x]

    # 배정 뒤 정지된 강사를 같은 값으로 다시 주면 409 다(상태 판정이 같은 값 비교보다 먼저, 결정 i)
    r = await client.post(f"{ADMIN}/instructors/{x}:suspend", headers=auth)
    assert r.status_code == 200, r.text
    body = problem_of(
        await client.patch(
            f"{ADMIN}/sessions/{first.id}", headers=auth, json={"instructor_id": x}
        ),
        409,
        "/problems/conflict",
    )
    assert body["instructor_status"] == "suspended"
    assert await _instructor_of(db_session, first.id) == x


async def test_assign_patch_session_audit_outbox(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin_id, auth = await admin_headers(db_session)
    x, _ = await approved(db_session, app.state.settings, email="x@example.com")
    course, section = await course_with_section(db_session)
    ax = await make_pool_course(db_session, source="ax")
    first = await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    second = await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    title = await db_session.scalar(
        select(CourseSession.title).where(CourseSession.id == first.id)
    )
    url = f"{ADMIN}/sessions/{first.id}"

    r = await client.patch(url, headers=auth, json={"instructor_id": x})
    assert r.status_code == 200, r.text
    assert (r.json()["instructor_id"], r.json()["pool_course_id"]) == (x, ax.id)
    audits = await _audits(db_session)
    assert len(audits) == 1
    audit_id, actor, target_type, target_id, detail = audits[0]
    assert (actor, target_type, target_id) == (
        f"admin:{admin_id}",
        "course",
        str(course.id),
    )
    assert set(detail) == DETAIL_KEYS
    assert (detail["instructor_id"], detail["course_title"]) == (x, course.title)
    assert (detail["materials"], detail["skipped_missing"]) == (0, 0)  # 경합 없음
    assert detail["sessions"] == [{"id": first.id, "title": title, "from": None}]
    outbox = await _outbox(db_session)
    assert len(outbox) == 1
    params, to = outbox[0]
    assert params == {"instructor_id": x, "audit_id": audit_id}
    assert to == "x@example.com"

    # 같은 값은 200 + audit·outbox 없음
    r = await client.patch(url, headers=auth, json={"instructor_id": x})
    assert r.status_code == 200, r.text
    assert (len(await _audits(db_session)), len(await _outbox(db_session))) == (1, 1)

    # 해제: audit 은 남기고(from = 이전 강사) 알림은 없다
    r = await client.patch(url, headers=auth, json={"instructor_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["instructor_id"] is None
    audits = await _audits(db_session)
    assert len(audits) == 2
    detail = audits[1][4]
    assert detail["instructor_id"] is None
    assert [(s["id"], s["from"]) for s in detail["sessions"]] == [(first.id, x)]
    assert len(await _outbox(db_session)) == 1

    # 제목과 배정을 한 번에: audit 의 세션 제목은 이번 PATCH 가 준 새 제목이다(결정 vii)
    r = await client.patch(
        f"{ADMIN}/sessions/{second.id}",
        headers=auth,
        json={"title": "새 제목", "instructor_id": x},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["title"], r.json()["instructor_id"]) == ("새 제목", x)
    audits = await _audits(db_session)
    assert len(audits) == 3
    assert [(s["id"], s["title"]) for s in audits[2][4]["sessions"]] == [
        (second.id, "새 제목")
    ]
    outbox = await _outbox(db_session)
    assert len(outbox) == 2
    assert outbox[1][0] == {"instructor_id": x, "audit_id": audits[2][0]}


async def test_assign_section_bulk(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    x, _ = await approved(db_session, app.state.settings, email="x@example.com")
    course, section = await course_with_section(db_session)
    ax = await make_pool_course(db_session, source="ax")
    sids = [
        (await pool_session(db_session, section_id=section.id, pool_id=ax.id)).id
        for _ in range(3)
    ]
    other_section = await add_section(client, auth, course.id, "다른 섹션")
    other = await pool_session(db_session, section_id=other_section, pool_id=ax.id)
    r = await client.patch(
        f"{ADMIN}/sessions/{sids[0]}", headers=auth, json={"instructor_id": x}
    )
    assert r.status_code == 200, r.text
    before = (len(await _audits(db_session)), len(await _outbox(db_session)))
    assert before == (1, 1)

    r = await client.post(
        _assign_url(course.id, section.id), headers=auth, json={"instructor_id": x}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == BULK_KEYS
    assert (body["section_id"], body["instructor_id"]) == (section.id, x)
    assert sorted(body["changed"]) == sorted(sids[1:])
    assert type(body["skipped_missing"]) is int and body["skipped_missing"] == 0
    assert body["materials"] == 0
    assert [await _instructor_of(db_session, s) for s in sids] == [x, x, x]
    assert await _instructor_of(db_session, other.id) is None
    audits = await _audits(db_session)
    assert len(audits) == 2
    assert sorted(s["id"] for s in audits[1][4]["sessions"]) == sorted(sids[1:])
    assert len(await _outbox(db_session)) == 2

    r = await client.post(
        _assign_url(course.id, section.id), headers=auth, json={"instructor_id": x}
    )
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == []
    assert (len(await _audits(db_session)), len(await _outbox(db_session))) == (2, 2)


async def test_assign_unknown_404(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    x, _ = await approved(db_session, app.state.settings, email="x@example.com")
    course, section = await course_with_section(db_session)
    other_course, other_section = await course_with_section(db_session)
    ax = await make_pool_course(db_session, source="ax")
    row = await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    foreign = await pool_session(db_session, section_id=other_section.id, pool_id=ax.id)

    cases = [
        ("PATCH", f"{ADMIN}/sessions/{row.id}", MISSING),
        ("POST", _assign_url(course.id, section.id), MISSING),
        ("PATCH", f"{ADMIN}/sessions/{MISSING}", x),
        ("POST", _assign_url(course.id, MISSING), x),
        ("POST", _assign_url(MISSING, section.id), x),
        ("POST", _assign_url(course.id, other_section.id), x),  # 다른 강의의 섹션
        ("PATCH", f"{ADMIN}/sessions/{row.id}", LARGEST),
        ("POST", _assign_url(course.id, section.id), LARGEST),
    ]
    for method, url, iid in cases:
        r = await client.request(method, url, headers=auth, json={"instructor_id": iid})
        problem_of(r, 404, "/problems/not_found")
    overflow = [
        (
            "PATCH",
            f"{ADMIN}/sessions/{row.id}",
            {"instructor_id": OVERFLOW},
            "body",
            "instructor_id",
        ),
        (
            "POST",
            _assign_url(course.id, section.id),
            {"instructor_id": OVERFLOW},
            "body",
            "instructor_id",
        ),
        (
            "POST",
            _assign_url(course.id, OVERFLOW),
            {"instructor_id": x},
            "path",
            "section_id",
        ),
        (
            "POST",
            _from_pool_url(OVERFLOW, section.id),
            {"pool_ids": [ax.id]},
            "path",
            "course_id",
        ),
        (
            "GET",
            f"{ADMIN}/courses/{OVERFLOW}/assignee-candidates",
            None,
            "path",
            "course_id",
        ),
    ]
    for method, url, body, where, name in overflow:
        got = problem_of(
            await client.request(method, url, headers=auth, json=body), 422
        )
        assert locs(got) == [[where, name]], (url, got)
        assert [v["type"] for v in got["violations"]] == ["less_than"], got
    assert await _instructor_of(db_session, row.id) is None
    assert await _instructor_of(db_session, foreign.id) is None
    assert await _audits(db_session) == []
    assert await _outbox(db_session) == []
    assert await _course_sessions(db_session, other_course.id) == 1
    assert await _course_sessions(db_session, course.id) == 1


async def test_assign_candidates_recommended_first(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    a, a_auth = await approved(db_session, settings, email="a@example.com")
    b, _ = await approved(db_session, settings, email="b@example.com")
    c, _ = await approved(db_session, settings, email="c@example.com")
    await approved(db_session, settings, email="d@example.com", status="pending")
    await approved(db_session, settings, email="e@example.com", status="suspended")
    ax = await make_pool_course(db_session, source="ax")
    own = await make_pool_course(db_session, source="own", owner_instructor_id=b)
    r = await client.put(f"/v1/me/capabilities/{ax.id}", headers=a_auth, json={})
    assert r.status_code == 201, r.text
    course, section = await course_with_section(db_session)
    for _ in range(2):
        await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    r = await client.post(
        _assign_url(course.id, section.id), headers=auth, json={"instructor_id": a}
    )
    assert r.status_code == 200, r.text
    url = f"{ADMIN}/courses/{course.id}/assignee-candidates"

    async def items(query: dict[str, str]) -> list[dict[str, Any]]:
        r = await client.get(url, headers=auth, params=query)
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["next_cursor"], body["has_more"]) == (None, False)
        for item in body["items"]:
            assert set(item) == CANDIDATE_KEYS, item
        return body["items"]

    got = await items({"pool_id": ax.id})
    assert [(i["instructor_id"], i["recommended"]) for i in got] == [
        (a, True),
        (b, False),
        (c, False),
    ]
    assert {i["instructor_id"]: i["assigned_sessions"] for i in got} == {
        a: 2,
        b: 0,
        c: 0,
    }
    got = await items({"pool_id": own.id})
    assert [(i["instructor_id"], i["recommended"]) for i in got] == [
        (b, True),
        (a, False),
        (c, False),
    ]
    got = await items({})
    assert [(i["instructor_id"], i["recommended"]) for i in got] == [
        (a, False),
        (b, False),
        (c, False),
    ]
    for r in (
        await client.get(url, headers=auth, params={"pool_id": "ax-missing-1"}),
        await client.get(url, headers=auth, params={"pool_id": "모양 밖"}),
        await client.get(
            f"{ADMIN}/courses/{MISSING}/assignee-candidates",
            headers=auth,
            params={"pool_id": ax.id},
        ),
    ):
        problem_of(r, 404, "/problems/not_found")


async def test_assign_from_pool_places_in_free_slots(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, section = await course_with_section(db_session, day_count=2)
    other_section = await add_section(client, auth, course.id, "다른 섹션")
    await add_session(client, auth, course.id, section_id=section.id, day_no=1, slot=1)
    await add_session(
        client, auth, course.id, section_id=other_section, day_no=1, slot=2
    )  # 다른 섹션의 교시는 이 섹션의 빈 교시를 막지 않는다
    pools = [
        await make_pool_course(
            db_session, source="ax", title=f"과정 {n}", goal=f"목표 {n}"
        )
        for n in range(5)
    ]
    picked = list(reversed(pools))  # 고른 순서대로 놓는다(id 순이 아니다)
    audits_before = await count(db_session, AuditLog)

    r = await client.post(
        _from_pool_url(course.id, section.id),
        headers=auth,
        json={"pool_ids": [p.id for p in picked], "day": 1},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body) == {"items", "spilled"}
    assert body["spilled"] == 0
    items = body["items"]
    assert [(i["day_no"], i["slot"]) for i in items] == [
        (1, 2),
        (1, 3),
        (1, 4),
        (2, 1),
        (2, 2),
    ]
    assert [(i["title"], i["description"], i["pool_course_id"]) for i in items] == [
        (p.title, p.goal, p.id) for p in picked
    ]
    for item in items:
        assert item["section_id"] == section.id
        assert item["minutes"] == course.slot_min
        assert (item["instructor_id"], item["is_open"], item["keywords"]) == (
            None,
            False,
            [],
        )
    assert await count(db_session, SessionAttachment) == 0
    assert await count(db_session, AuditLog) == audits_before

    # day 없이 고르면 전부 일차 미정이고 넘친 것이 아니다
    r = await client.post(
        _from_pool_url(course.id, section.id),
        headers=auth,
        json={"pool_ids": [pools[0].id, pools[1].id]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["spilled"] == 0
    assert [(i["day_no"], i["slot"], i["minutes"]) for i in r.json()["items"]] == [
        (None, None, pools[0].minutes),
        (None, None, pools[1].minutes),
    ]


async def test_assign_from_pool_rejections(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    course, section = await course_with_section(db_session, day_count=2)
    other_course, other_section = await course_with_section(db_session, day_count=2)
    pools = [
        await make_pool_course(db_session, source="ax", title=f"과정 {n}")
        for n in range(10)
    ]
    url = _from_pool_url(course.id, section.id)

    r = await client.post(
        url, headers=auth, json={"pool_ids": [p.id for p in pools], "day": 2}
    )
    assert r.status_code == 201, r.text
    assert r.json()["spilled"] == 6
    assert [(i["day_no"], i["slot"]) for i in r.json()["items"]] == [
        (2, 1),
        (2, 2),
        (2, 3),
        (2, 4),
    ] + [(None, None)] * 6

    counts = (
        await _course_sessions(db_session, course.id),
        await _course_sessions(db_session, other_course.id),
    )
    assert counts == (10, 0)
    await set_flags(db_session, pools[0], active=False)
    good = pools[1].id

    async def rejected(
        target: str, body: dict[str, Any], status: int, type_: str | None = None
    ) -> dict[str, Any]:
        got = problem_of(
            await client.post(target, headers=auth, json=body), status, type_
        )
        assert (
            await _course_sessions(db_session, course.id),
            await _course_sessions(db_session, other_course.id),
        ) == counts, body
        return got

    await rejected(url, {"pool_ids": [good], "day": 3}, 409, "/problems/conflict")
    got = await rejected(
        url, {"pool_ids": [pools[0].id, good], "day": 1}, 409, "/problems/conflict"
    )
    assert got["inactive"] == [pools[0].id]
    got = await rejected(
        url, {"pool_ids": ["ax-missing-1", good]}, 404, "/problems/not_found"
    )
    assert got["missing"] == ["ax-missing-1"]
    got = await rejected(url, {"pool_ids": [good, good]}, 422)
    assert locs(got) == [["body", "pool_ids"]]
    await rejected(url, {"pool_ids": []}, 422)
    many = [f"ax-many-{n}" for n in range(21)]
    await rejected(url, {"pool_ids": many}, 422)
    await rejected(
        _from_pool_url(course.id, MISSING),
        {"pool_ids": [good]},
        404,
        "/problems/not_found",
    )
    # 다른 강의의 섹션을 이 강의 경로로(결정 vi ①)
    await rejected(
        _from_pool_url(course.id, other_section.id),
        {"pool_ids": [good], "day": 1},
        404,
        "/problems/not_found",
    )


async def test_assign_portal_instructor_name(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    x, _ = await approved(db_session, app.state.settings, email="x@example.com")
    row = await lock_instructor(db_session, x)
    assert row is not None
    await update_instructor(db_session, row, name=X_NAME)
    course, section = await course_with_section(db_session)
    ax = await make_pool_course(db_session, source="ax")
    opened, preparing, unassigned = [
        (
            await pool_session(
                db_session, section_id=section.id, pool_id=ax.id, day_no=1, slot=n
            )
        ).id
        for n in (1, 2, 3)
    ]
    for sid in (opened, preparing):
        r = await client.patch(
            f"{ADMIN}/sessions/{sid}", headers=auth, json={"instructor_id": x}
        )
        assert r.status_code == 200, r.text
    for sid in (opened, unassigned):
        r = await client.post(
            f"{ADMIN}/sessions/{sid}/attachments",
            headers=auth,
            data={"kind": "link", "title": "자료", "url": "https://example.com/a"},
        )
        assert r.status_code == 201, r.text
        r = await client.patch(
            f"{ADMIN}/sessions/{sid}", headers=auth, json={"is_open": True}
        )
        assert r.status_code == 200, r.text
    learner = await learner_headers(db_session, course.id)

    def no_instructor_leak(r: httpx.Response) -> None:
        assert r.status_code == 200, r.text
        keys = json_keys(r.json())
        assert keys & INSTRUCTOR_KEYS == set(), r.url
        assert keys & PERSONAL_KEYS == set(), r.url
        for secret in ("x@example.com", "010-0000-0000"):
            assert secret not in r.text, (r.url, secret)

    for url, headers in (
        (f"/v1/learner/courses/{course.id}/portal", learner),
        (f"{ADMIN}/courses/{course.id}/portal", auth),
    ):
        r = await client.get(url, headers=headers)
        no_instructor_leak(r)
        body = r.json()
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
        assert {
            sid: (cards[sid]["state"], cards[sid]["instructor_name"])
            for sid in (opened, preparing, unassigned)
        } == {
            opened: ("open", X_NAME),
            preparing: ("preparing", X_NAME),  # 준비 중 카드도 이름
            unassigned: ("open", None),
        }

    r = await client.get(f"/v1/learner/sessions/{opened}/attachments", headers=learner)
    no_instructor_leak(r)
    assert [set(item) for item in r.json()["items"]] == [ATTACHMENT_KEYS]

    r = await client.get(f"{ADMIN}/courses/{course.id}/schedule", headers=auth)
    assert r.status_code == 200, r.text
    slots = {s["id"]: s for day in r.json()["days"] for s in day["sessions"]}
    assert {
        sid: (slots[sid]["instructor_id"], slots[sid]["instructor_name"])
        for sid in (opened, preparing, unassigned)
    } == {opened: (x, X_NAME), preparing: (x, X_NAME), unassigned: (None, None)}
