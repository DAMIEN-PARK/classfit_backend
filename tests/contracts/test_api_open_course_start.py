"""개설 시작점 ②(지난 강의 복제)·④(강사 커리큘럼) — POST /v1/admin/courses 의 start(T5 계획 결정 iii·iv·v·viii · 증명 9~12).

복제는 섹션·세션 구조와 배정을 옮기고(세션은 전부 닫힘, 승인 아닌 강사는 미배정, 새 강의 일차 밖은 일차 미정) 첨부·일차는
옮기지 않는다. 커리큘럼 시작점은 섹션 「전체」 하나에 차시마다 세션을 만들고 소유 강사를 배정한다. 원본을 나중에 고쳐도
강의는 그대로다(CAT-007). 픽스처 강의는 2026-11-02(월)부터 평일, 하루 13:00~17:00 이다.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import (
    AuditLog,
    Course,
    CourseSession,
    InviteCode,
    MailOutbox,
    Section,
    SessionAttachment,
)
from tests.fixtures.assign import approved, course_with_section, pool_session
from tests.fixtures.courses import admin_headers, open_test_course
from tests.fixtures.enter import add_pdf, add_section, add_session
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.pool import ME, curriculum_body, make_pool_course

ADMIN = "/v1/admin"
URL = f"{ADMIN}/courses"
MISSING = 999_999_999
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422(codex 구현 리뷰 1차)
BODY: dict[str, Any] = {
    "start": "blank",
    "title": "새 강의",
    "client_name": "B사",
    "method": "집체",
    "hours_per_person": 8,
    "start_on": "2026-12-07",
    "day_count": 4,
    "day_start": "13:00",
    "day_end": "17:00",
}
SLOTS = [
    {"day": 1, "slot": 1, "title": "차시 1-1", "description": "설명 1"},
    {"day": 1, "slot": 2, "title": "차시 1-2"},
    {"day": 2, "slot": 1, "title": "차시 2-1", "description": "설명 3"},
]


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _undated(**over: Any) -> dict[str, Any]:
    """day_count 0 본문(기간은 end_on 이 정한다)."""
    body = {**BODY, "day_count": 0, "end_on": "2026-12-31", **over}
    del body["day_start"], body["day_end"]
    return body


async def _open(
    client: httpx.AsyncClient, auth: dict[str, str], **over: Any
) -> dict[str, Any]:
    r = await client.post(URL, headers=auth, json={**BODY, **over})
    assert r.status_code == 201, r.text
    return r.json()


async def _curriculum(
    client: httpx.AsyncClient, headers: dict[str, str], slots: list[dict[str, Any]]
) -> str:
    """강사 API 로 커리큘럼(2일, 미검토)을 만들고 차시표를 넣는다."""
    r = await client.post(
        f"{ME}/curricula", headers=headers, json=curriculum_body(days=2)
    )
    assert r.status_code == 201, r.text
    cid: str = r.json()["id"]
    r = await client.put(
        f"{ME}/curricula/{cid}/slots", headers=headers, json={"slots": slots}
    )
    assert r.status_code == 200, r.text
    return cid


async def _sections(session: AsyncSession, course_id: int) -> list[tuple[Any, ...]]:
    rows = await session.execute(
        select(Section.title, Section.sort, Section.description)
        .where(Section.course_id == course_id)
        .order_by(Section.sort, Section.id)
    )
    return [tuple(r) for r in rows]


async def _sessions(session: AsyncSession, course_id: int) -> list[dict[str, Any]]:
    """세션 칸(섹션 제목 포함). 비교는 순서와 무관하게 정렬해서 한다."""
    rows = await session.execute(
        select(
            CourseSession.id,
            Section.title.label("section"),
            CourseSession.title,
            CourseSession.description,
            CourseSession.keywords,
            CourseSession.minutes,
            CourseSession.day_no,
            CourseSession.slot,
            CourseSession.time_start,
            CourseSession.time_end,
            CourseSession.is_open,
            CourseSession.pool_course_id,
            CourseSession.curriculum_id,
            CourseSession.instructor_id,
        )
        .join(Section, Section.id == CourseSession.section_id)
        .where(Section.course_id == course_id)
        .order_by(CourseSession.id)
    )
    return [dict(r._mapping) for r in rows]


def _content(rows: list[dict[str, Any]]) -> list[str]:
    """id 를 뺀 세션 칸의 정렬된 글자(순서·id 와 무관한 비교)."""
    return sorted(repr({k: v for k, v in r.items() if k != "id"}) for r in rows)


async def _audit_detail(
    session: AsyncSession, action: str, course_id: int
) -> list[Any]:
    rows = await session.execute(
        select(AuditLog.id, AuditLog.detail)
        .where(AuditLog.action == action, AuditLog.target_id == str(course_id))
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _outbox_for(
    session: AsyncSession, audit_id: int
) -> list[tuple[dict[str, Any], str]]:
    rows = await session.execute(
        select(MailOutbox.params, MailOutbox.to).where(
            MailOutbox.kind == "session_assigned",
            MailOutbox.params["audit_id"].as_integer() == audit_id,
        )
    )
    return [tuple(r) for r in rows]


async def _course_attachments(session: AsyncSession, course_id: int) -> int:
    return await count(
        session,
        SessionAttachment,
        SessionAttachment.session_id.in_(
            select(CourseSession.id)
            .join(Section, Section.id == CourseSession.section_id)
            .where(Section.course_id == course_id)
        ),
    )


async def test_open_course_start_clone_copies_structure(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    x, _ = await approved(db_session, settings, email="x@example.com")
    s, _ = await approved(db_session, settings, email="s@example.com")
    ax = await make_pool_course(db_session, source="ax")
    source, code = await open_test_course(db_session, title="원본 강의")
    first = await add_section(client, auth, source.id, "1부")
    r = await client.patch(
        f"{ADMIN}/courses/{source.id}/sections/{first}",
        headers=auth,
        json={"sort": 1, "description": "앞 절반"},
    )
    assert r.status_code == 200, r.text
    second = await add_section(client, auth, source.id, "2부")
    pooled = await pool_session(
        db_session, section_id=first, pool_id=ax.id, day_no=1, slot=1
    )
    made = {
        pooled.id: {
            "keywords": ["AI"],
            "minutes": 90,
            "description": "설명 가",
            "is_open": True,
            "instructor_id": x,
        },
        await add_session(
            client,
            auth,
            source.id,
            section_id=first,
            title="예외 시각",
            day_no=2,
            time_start="09:00",
            time_end="10:00",
            keywords=["보안"],
        ): {"instructor_id": x},
        await add_session(
            client,
            auth,
            source.id,
            section_id=second,
            title="정지될 강사",
            day_no=3,
            slot=1,
        ): {"instructor_id": s},
        await add_session(
            client, auth, source.id, section_id=second, title="미배정", is_open=True
        ): {},
    }
    for sid, fields in made.items():
        if fields:
            r = await client.patch(f"{ADMIN}/sessions/{sid}", headers=auth, json=fields)
            assert r.status_code == 200, r.text
    assert (await add_pdf(client, auth, pooled.id)).status_code == 201
    r = await client.post(f"{ADMIN}/instructors/{s}:suspend", headers=auth)
    assert r.status_code == 200, r.text
    before = (
        await _sections(db_session, source.id),
        await _sessions(db_session, source.id),
        await _course_attachments(db_session, source.id),
    )

    body = await _open(
        client, auth, start="clone", source_course_id=source.id, title="복제 강의"
    )
    new_id = body["course"]["id"]
    assert new_id != source.id
    assert body["invite_code"]["code"] != code.code
    assert await _sections(db_session, new_id) == before[0]
    expected = [
        {
            **row,
            "is_open": False,
            "instructor_id": None
            if row["instructor_id"] == s
            else row["instructor_id"],
        }
        for row in before[1]
    ]
    copied = await _sessions(db_session, new_id)
    assert _content(copied) == _content(expected)
    assert sorted(r["instructor_id"] or 0 for r in copied) == [0, 0, x, x]

    ((_, opened),) = await _audit_detail(db_session, "course.open", new_id)
    assert (opened["start"], opened["source"]) == ("clone", source.id)
    ((audit_id, assigned),) = await _audit_detail(db_session, "session.assign", new_id)
    assert assigned["instructor_id"] == x
    assert len(assigned["sessions"]) == 2
    assert await _outbox_for(db_session, audit_id) == [
        ({"instructor_id": x, "audit_id": audit_id}, "x@example.com")
    ]
    assert (
        await _sections(db_session, source.id),
        await _sessions(db_session, source.id),
        await _course_attachments(db_session, source.id),
    ) == before


async def test_open_course_start_clone_days_beyond_undated(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    source, _ = await open_test_course(db_session)  # 4일
    section = await add_section(client, auth, source.id)
    for day in (1, 2, 3, 4):
        await add_session(
            client,
            auth,
            source.id,
            section_id=section,
            title=f"{day}일",
            day_no=day,
            slot=1,
        )

    new_id = (
        await _open(
            client, auth, start="clone", source_course_id=source.id, day_count=2
        )
    )["course"]["id"]
    rows = await _sessions(db_session, new_id)
    assert {r["title"]: (r["day_no"], r["slot"]) for r in rows} == {
        "1일": (1, 1),
        "2일": (2, 1),
        "3일": (None, None),
        "4일": (None, None),
    }
    r = await client.get(f"{URL}/{new_id}/schedule", headers=auth)
    assert r.status_code == 200, r.text
    assert sorted(s["title"] for s in r.json()["undated"]) == ["3일", "4일"]

    r = await client.post(
        URL,
        headers=auth,
        json=_undated(start="clone", source_course_id=source.id),
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["course"]["id"]
    rows = await _sessions(db_session, new_id)
    assert [(r["day_no"], r["slot"]) for r in rows] == [(None, None)] * 4
    r = await client.get(f"{URL}/{new_id}/schedule", headers=auth)
    assert (r.json()["days"], len(r.json()["undated"])) == ([], 4)


async def test_open_course_start_curriculum_builds_sessions(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    o, o_auth = await approved(db_session, app.state.settings, email="o@example.com")
    cid = await _curriculum(client, o_auth, SLOTS)  # 미검토 그대로 고른다

    body = await _open(
        client, auth, start="curriculum", curriculum_id=cid, day_count=2, slot_min=45
    )
    new_id = body["course"]["id"]
    assert await _sections(db_session, new_id) == [("전체", 0, None)]
    rows = await _sessions(db_session, new_id)
    assert sorted(
        (r["day_no"], r["slot"], r["title"], r["description"]) for r in rows
    ) == [(s["day"], s["slot"], s["title"], s.get("description")) for s in SLOTS]
    for row in rows:
        assert (
            row["minutes"],
            row["curriculum_id"],
            row["instructor_id"],
            row["is_open"],
            row["keywords"],
            row["pool_course_id"],
        ) == (45, cid, o, False, [], None)
    assert (
        await db_session.scalar(
            select(Course.curriculum_src_id).where(Course.id == new_id)
        )
        == cid
    )
    ((_, opened),) = await _audit_detail(db_session, "course.open", new_id)
    assert (opened["start"], opened["source"]) == ("curriculum", cid)
    ((audit_id, assigned),) = await _audit_detail(db_session, "session.assign", new_id)
    assert (assigned["instructor_id"], len(assigned["sessions"])) == (o, 3)
    assert await _outbox_for(db_session, audit_id) == [
        ({"instructor_id": o, "audit_id": audit_id}, "o@example.com")
    ]

    # 일차가 모자란 강의: 2일차 차시는 일차 미정
    short = (
        await _open(client, auth, start="curriculum", curriculum_id=cid, day_count=1)
    )["course"]["id"]
    rows = await _sessions(db_session, short)
    assert sorted((r["title"], r["day_no"], r["slot"]) for r in rows) == [
        ("차시 1-1", 1, 1),
        ("차시 1-2", 1, 2),
        ("차시 2-1", None, None),
    ]
    r = await client.get(f"{URL}/{short}/schedule", headers=auth)
    assert [s["title"] for s in r.json()["undated"]] == ["차시 2-1"]


async def test_open_course_start_rejections(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    _, o_auth = await approved(db_session, settings, email="o@example.com")
    _, p_auth = await approved(
        db_session, settings, email="p@example.com", status="pending"
    )
    inactive = await _curriculum(client, o_auth, SLOTS[:1])
    r = await client.delete(f"{ME}/curricula/{inactive}", headers=o_auth)
    assert r.status_code == 204, r.text
    pending_owner = await _curriculum(client, p_auth, SLOTS[:1])
    existing, _ = await open_test_course(db_session)
    counts = (await count(db_session, Course), await count(db_session, InviteCode))

    async def rejected(
        body: dict[str, Any], status: int, type_: str | None = None
    ) -> dict[str, Any]:
        got = problem_of(await client.post(URL, headers=auth, json=body), status, type_)
        assert (
            await count(db_session, Course),
            await count(db_session, InviteCode),
        ) == counts, body
        return got

    await rejected(
        {**BODY, "start": "clone", "source_course_id": MISSING},
        404,
        "/problems/not_found",
    )
    await rejected(
        {**BODY, "start": "curriculum", "curriculum_id": "cur-999-999"},
        404,
        "/problems/not_found",
    )
    await rejected(
        {**BODY, "start": "curriculum", "curriculum_id": inactive},
        409,
        "/problems/conflict",
    )
    got = await rejected(
        {**BODY, "start": "curriculum", "curriculum_id": pending_owner},
        409,
        "/problems/conflict",
    )
    assert got["instructor_status"] == "pending"
    await rejected(
        {**BODY, "start": "clone", "source_course_id": LARGEST},
        404,
        "/problems/not_found",
    )
    got = await rejected({**BODY, "start": "clone", "source_course_id": OVERFLOW}, 422)
    assert locs(got) == [["body", "source_course_id"]]
    assert [v["type"] for v in got["violations"]] == ["less_than"]
    await rejected({**BODY, "start": "clone"}, 422)
    await rejected({**BODY, "start": "blank", "curriculum_id": pending_owner}, 422)
    await rejected(
        {
            **BODY,
            "start": "curriculum",
            "curriculum_id": pending_owner,
            "source_course_id": existing.id,
        },
        422,
    )


async def test_open_course_start_source_edit_keeps_course(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await admin_headers(db_session)
    _, o_auth = await approved(db_session, app.state.settings, email="o@example.com")
    cid = await _curriculum(client, o_auth, SLOTS)
    from_curriculum = (
        await _open(client, auth, start="curriculum", curriculum_id=cid)
    )["course"]["id"]
    kept = _content(await _sessions(db_session, from_curriculum))

    r = await client.patch(
        f"{ME}/curricula/{cid}", headers=o_auth, json={"title": "바뀐 커리큘럼"}
    )
    assert r.status_code == 200, r.text
    r = await client.put(
        f"{ME}/curricula/{cid}/slots",
        headers=o_auth,
        json={"slots": [{"day": 1, "slot": 1, "title": "바뀐 차시"}]},
    )
    assert r.status_code == 200, r.text
    r = await client.patch(
        f"{ADMIN}/curricula/{cid}", headers=auth, json={"active": False}
    )
    assert r.status_code == 200, r.text
    assert _content(await _sessions(db_session, from_curriculum)) == kept

    ax = await make_pool_course(db_session, source="ax", title="원래 AX")
    course, section = await course_with_section(db_session)
    r = await client.post(
        f"{ADMIN}/courses/{course.id}/sections/{section.id}/sessions:from-pool",
        headers=auth,
        json={"pool_ids": [ax.id], "day": 1},
    )
    assert r.status_code == 201, r.text
    r = await client.patch(
        f"{ADMIN}/pool/{ax.id}", headers=auth, json={"title": "바뀐 AX"}
    )
    assert r.status_code == 200, r.text
    assert [row["title"] for row in await _sessions(db_session, course.id)] == [
        "원래 AX"
    ]

    cloned = (
        await _open(client, auth, start="clone", source_course_id=from_curriculum)
    )["course"]["id"]
    copied = _content(await _sessions(db_session, cloned))
    source_rows = await _sessions(db_session, from_curriculum)
    r = await client.patch(
        f"{ADMIN}/sessions/{source_rows[0]['id']}",
        headers=auth,
        json={"title": "원본 고침"},
    )
    assert r.status_code == 200, r.text
    assert _content(await _sessions(db_session, cloned)) == copied
