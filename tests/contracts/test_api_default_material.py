"""기본 강의안 자동 첨부 — 행 복제(같은 sha · 다른 key)(T5 계획 결정 iv·v·x·xi · 증명 2·5~9·24).

강사가 새로 배정된 세션이 풀 과정을 가리키고 첨부가 0개면 그 강사의 기본 강의안이 붙는다: 소유자면 고유 과정 파일 먼저,
그다음 그 강사의 역량 파일. 사본은 session_attachment 행 + 새 stored_file 행(원본 sha·크기, 새 key)이고 바이트는 쓰지
않는다. 출처는 session_attachment.origin(응답에는 없다)에 원본 owner_kind 로 남는다. 커리큘럼 시작점은 커리큘럼 자료를
모든 세션에 붙인다. 복제는 원본 첨부를 옮기지 않고 기본 강의안만 다시 붙인다.
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
    CourseSession,
    CurriculumFile,
    MailOutbox,
    Section,
    SessionAttachment,
    StoredFile,
)
from classfit.service.files.store import href_for
from tests.fixtures.assign import PDF, approved, course_with_section, pool_session
from tests.fixtures.courses import admin_headers, learner_headers
from tests.fixtures.enter import add_pdf, add_session
from tests.fixtures.instructors import count
from tests.fixtures.pool import (
    ME,
    add_pool_link,
    add_pool_pdf,
    curriculum_body,
    make_pool_course,
)

ADMIN = "/v1/admin"
ADMIN_PDF = (
    PDF + b"% admin\n"
)  # 관리자 첨부는 역량 파일과 다른 바이트(sha 로 섞이지 않게)


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


async def _capability(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    pool_id: str,
    *,
    title: str,
    links: int = 0,
) -> list[dict[str, Any]]:
    """역량 표시 + PDF 1개(+ 링크 links 개)를 강사 API 로 올린다. 올린 순서가 sort 순서다."""
    r = await client.put(f"{ME}/capabilities/{pool_id}", headers=headers, json={})
    assert r.status_code == 201, r.text
    path = f"{ME}/capabilities/{pool_id}/files"
    made = [await add_pool_pdf(client, headers, path, title=title)]
    made += [
        await add_pool_link(client, headers, path, title=f"{title} 링크 {n}")
        for n in range(links)
    ]
    for r in made:
        assert r.status_code == 201, r.text
    return [r.json() for r in made]


async def _assign(
    client: httpx.AsyncClient, auth: dict[str, str], session_id: int, iid: int | None
) -> None:
    r = await client.patch(
        f"{ADMIN}/sessions/{session_id}", headers=auth, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


async def _attachments(session: AsyncSession, session_id: int) -> list[dict[str, Any]]:
    """그 세션 첨부의 (id, kind, title, url, file_id, origin), (sort, id) 순."""
    rows = await session.execute(
        select(
            SessionAttachment.id,
            SessionAttachment.kind,
            SessionAttachment.title,
            SessionAttachment.url,
            SessionAttachment.file_id,
            SessionAttachment.origin,
        )
        .where(SessionAttachment.session_id == session_id)
        .order_by(SessionAttachment.sort, SessionAttachment.id)
    )
    return [dict(r._mapping) for r in rows]


async def _stored(session: AsyncSession, *where: Any) -> dict[str, Any]:
    row = (
        await session.execute(
            select(
                StoredFile.id,
                StoredFile.key,
                StoredFile.sha256,
                StoredFile.owner_kind,
                StoredFile.owner_id,
                StoredFile.content_type,
                StoredFile.size,
            ).where(*where)
        )
    ).one()
    return dict(row._mapping)


def _key(href: str) -> str:
    return href.rsplit("/", 1)[-1]


async def _assign_detail(session: AsyncSession) -> dict[str, Any]:
    """가장 최근 session.assign audit 의 detail."""
    detail = await session.scalar(
        select(AuditLog.detail)
        .where(AuditLog.action == "session.assign")
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    assert detail is not None
    return detail


async def test_default_material_row_copy_same_sha_new_key(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    _, auth = await admin_headers(db_session)
    x, x_auth = await approved(db_session, app.state.settings, email="x@example.com")
    ax = await make_pool_course(db_session, source="ax")
    pdf, link = await _capability(client, x_auth, ax.id, title="X 강의안", links=1)
    course, section = await course_with_section(db_session)
    row = await pool_session(
        db_session, section_id=section.id, pool_id=ax.id, day_no=1, slot=1
    )

    await _assign(client, auth, row.id, x)
    copies = await _attachments(db_session, row.id)
    assert [(a["kind"], a["title"], a["origin"]) for a in copies] == [
        ("pdf", pdf["title"], "capability_file"),
        ("link", link["title"], "capability_file"),
    ]
    assert (copies[0]["url"], copies[1]["url"], copies[1]["file_id"]) == (
        None,
        link["href"],
        None,
    )
    source = await _stored(db_session, StoredFile.key == _key(pdf["href"]))
    copy = await _stored(db_session, StoredFile.id == copies[0]["file_id"])
    assert copy["sha256"] == source["sha256"]
    assert copy["key"] != source["key"]
    assert (copy["owner_kind"], copy["owner_id"]) == (
        "session_attachment",
        copies[0]["id"],
    )
    assert (copy["content_type"], copy["size"]) == (
        source["content_type"],
        source["size"],
    )
    assert len([p for p in store_root.rglob("*") if p.is_file()]) == 1  # 바이트는 한 벌
    assert (await _assign_detail(db_session))["materials"] == 2

    copy_href = href_for(copy["key"])
    r = await client.get(copy_href, headers=auth)
    assert (r.status_code, r.content) == (200, PDF)
    r = await client.patch(
        f"{ADMIN}/sessions/{row.id}", headers=auth, json={"is_open": True}
    )
    assert r.status_code == 200, r.text
    learner = await learner_headers(db_session, course.id)
    assert (await client.get(copy_href, headers=learner)).status_code == 200

    # 원본 파일을 지워도 사본은 열린다(같은 sha 를 사본 행이 가리킨다)
    r = await client.delete(f"{ME}/capability-files/{pdf['id']}", headers=x_auth)
    assert r.status_code == 204, r.text
    assert (await client.get(pdf["href"], headers=auth)).status_code == 404
    r = await client.get(copy_href, headers=auth)
    assert (r.status_code, r.content) == (200, PDF)


async def test_default_material_only_empty_sessions(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    _, auth = await admin_headers(db_session)
    x, x_auth = await approved(db_session, app.state.settings, email="x@example.com")
    ax = await make_pool_course(db_session, source="ax")
    await _capability(client, x_auth, ax.id, title="X 강의안", links=1)
    course, section = await course_with_section(db_session)
    full = await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    r = await client.post(
        f"{ADMIN}/sessions/{full.id}/attachments",
        headers=auth,
        data={"kind": "link", "title": "관리자 자료", "url": "https://example.com/a"},
    )
    assert r.status_code == 201, r.text
    empty = await pool_session(db_session, section_id=section.id, pool_id=ax.id)
    plain = await add_session(
        client, auth, course.id, section_id=section.id
    )  # 풀 과정 없음

    r = await client.post(
        f"{ADMIN}/courses/{course.id}/sections/{section.id}:assign",
        headers=auth,
        json={"instructor_id": x},
    )
    assert r.status_code == 200, r.text
    assert r.json()["materials"] == 2
    assert [
        (a["title"], a["origin"]) for a in await _attachments(db_session, full.id)
    ] == [("관리자 자료", None)]
    assert [a["origin"] for a in await _attachments(db_session, empty.id)] == [
        "capability_file",
        "capability_file",
    ]
    assert await _attachments(db_session, plain) == []


async def test_default_material_reassign_keeps_previous_and_outbox(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    ax = await make_pool_course(db_session, source="ax")
    await _capability(client, x_auth, ax.id, title="X 강의안", links=1)
    await _capability(client, y_auth, ax.id, title="Y 강의안")
    _, section = await course_with_section(db_session)
    row = await pool_session(db_session, section_id=section.id, pool_id=ax.id)

    await _assign(client, auth, row.id, x)
    kept = await _attachments(db_session, row.id)
    assert [a["title"] for a in kept] == ["X 강의안", "X 강의안 링크 0"]
    await _assign(client, auth, row.id, y)
    assert await _attachments(db_session, row.id) == kept  # 이전 첨부 유지 · Y 것 없음
    outbox = (
        await db_session.scalars(
            select(MailOutbox.params)
            .where(MailOutbox.kind == "session_assigned")
            .order_by(MailOutbox.id)
        )
    ).all()
    assert [p["instructor_id"] for p in outbox] == [x, y]
    assert await count(db_session, AuditLog, AuditLog.action == "session.assign") == 2

    await _assign(client, auth, row.id, None)
    assert await _attachments(db_session, row.id) == kept
    assert (
        await count(db_session, MailOutbox, MailOutbox.kind == "session_assigned") == 2
    )


async def test_default_material_own_course_owner_only(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    o, o_auth = await approved(db_session, settings, email="o@example.com")
    z, _ = await approved(db_session, settings, email="z@example.com")
    w, w_auth = await approved(db_session, settings, email="w@example.com")
    own = await make_pool_course(db_session, source="own", owner_instructor_id=o)
    r = await add_pool_pdf(
        client, o_auth, f"{ME}/own-courses/{own.id}/files", title="고유 강의안"
    )
    assert r.status_code == 201, r.text
    await _capability(client, o_auth, own.id, title="O 역량")
    await _capability(client, w_auth, own.id, title="W 역량")
    _, section = await course_with_section(db_session)
    rows = [
        await pool_session(db_session, section_id=section.id, pool_id=own.id)
        for _ in range(3)
    ]

    for row, iid in zip(rows, (o, z, w), strict=True):
        await _assign(client, auth, row.id, iid)
    got = [
        [(a["title"], a["origin"]) for a in await _attachments(db_session, row.id)]
        for row in rows
    ]
    assert got == [
        [("고유 강의안", "pool_course_file"), ("O 역량", "capability_file")],
        [],  # 역량 없는 승인 강사 — 남의 고유 과정 파일은 붙지 않는다
        [("W 역량", "capability_file")],
    ]


async def test_default_material_clone_reattaches_not_copies(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    settings = app.state.settings
    _, auth = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    s, s_auth = await approved(db_session, settings, email="s@example.com")
    ax = await make_pool_course(db_session, source="ax")
    (x_pdf,) = await _capability(client, x_auth, ax.id, title="X 강의안")
    await _capability(client, s_auth, ax.id, title="S 강의안")
    source, section = await course_with_section(db_session)
    first = await pool_session(
        db_session, section_id=section.id, pool_id=ax.id, day_no=1, slot=1
    )
    second = await pool_session(
        db_session, section_id=section.id, pool_id=ax.id, day_no=1, slot=2
    )
    await _assign(client, auth, first.id, x)
    r = await add_pdf(client, auth, first.id, ADMIN_PDF, title="관리자 강의안")
    assert r.status_code == 201, r.text
    await _assign(client, auth, second.id, s)
    r = await client.post(f"{ADMIN}/instructors/{s}:suspend", headers=auth)
    assert r.status_code == 200, r.text
    before = await _attachments(db_session, first.id)
    assert [(a["title"], a["origin"]) for a in before] == [
        ("X 강의안", "capability_file"),
        ("관리자 강의안", None),
    ]
    earlier = await _stored(db_session, StoredFile.id == before[0]["file_id"])

    r = await client.post(
        f"{ADMIN}/courses",
        headers=auth,
        json={
            "start": "clone",
            "source_course_id": source.id,
            "title": "복제 강의",
            "client_name": "B사",
            "method": "집체",
            "hours_per_person": 8,
            "start_on": "2026-12-07",
            "day_count": 2,
            "day_start": "13:00",
            "day_end": "17:00",
        },
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["course"]["id"]
    rows = (
        await db_session.execute(
            select(CourseSession.id, CourseSession.slot, CourseSession.instructor_id)
            .join(Section, Section.id == CourseSession.section_id)
            .where(Section.course_id == new_id)
        )
    ).all()
    by_slot = {slot: (sid, iid) for sid, slot, iid in rows}
    new_first, new_second = by_slot[1], by_slot[2]
    assert (new_first[1], new_second[1]) == (x, None)
    copies = await _attachments(db_session, new_first[0])
    assert [(a["kind"], a["title"], a["origin"]) for a in copies] == [
        ("pdf", "X 강의안", "capability_file")
    ]
    copy = await _stored(db_session, StoredFile.id == copies[0]["file_id"])
    source_file = await _stored(db_session, StoredFile.key == _key(x_pdf["href"]))
    assert copy["sha256"] == source_file["sha256"]
    assert copy["key"] not in (source_file["key"], earlier["key"])
    assert await _attachments(db_session, new_second[0]) == []  # 정지 강사 세션


async def test_default_material_curriculum_files_each_session(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    _, auth = await admin_headers(db_session)
    _, o_auth = await approved(db_session, app.state.settings, email="o@example.com")
    r = await client.post(
        f"{ME}/curricula", headers=o_auth, json=curriculum_body(days=2)
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    slots = [
        {"day": 1, "slot": 1, "title": "차시 가"},
        {"day": 1, "slot": 2, "title": "차시 나"},
        {"day": 2, "slot": 1, "title": "차시 다"},
    ]
    r = await client.put(
        f"{ME}/curricula/{cid}/slots", headers=o_auth, json={"slots": slots}
    )
    assert r.status_code == 200, r.text
    path = f"{ME}/curricula/{cid}/files"
    pdf = await add_pool_pdf(client, o_auth, path, title="커리큘럼 자료")
    link = await add_pool_link(client, o_auth, path, title="커리큘럼 링크")
    assert (pdf.status_code, link.status_code) == (201, 201), (pdf.text, link.text)

    r = await client.post(
        f"{ADMIN}/courses",
        headers=auth,
        json={
            "start": "curriculum",
            "curriculum_id": cid,
            "title": "커리큘럼 강의",
            "client_name": "B사",
            "method": "집체",
            "hours_per_person": 8,
            "start_on": "2026-12-07",
            "day_count": 2,
            "day_start": "13:00",
            "day_end": "17:00",
        },
    )
    assert r.status_code == 201, r.text
    session_ids = (
        await db_session.scalars(
            select(CourseSession.id)
            .join(Section, Section.id == CourseSession.section_id)
            .where(Section.course_id == r.json()["course"]["id"])
        )
    ).all()
    assert len(session_ids) == 3
    file_ids = []
    for sid in session_ids:
        got = await _attachments(db_session, sid)
        assert [(a["kind"], a["title"], a["origin"]) for a in got] == [
            ("pdf", "커리큘럼 자료", "curriculum_file"),
            ("link", "커리큘럼 링크", "curriculum_file"),
        ]
        file_ids.append(got[0]["file_id"])
    source = await _stored(db_session, StoredFile.key == _key(pdf.json()["href"]))
    copies = [await _stored(db_session, StoredFile.id == fid) for fid in file_ids]
    assert {c["sha256"] for c in copies} == {source["sha256"]}
    keys = {c["key"] for c in copies}
    assert len(keys) == 3 and source["key"] not in keys
    assert (
        await count(db_session, CurriculumFile, CurriculumFile.curriculum_id == cid)
        == 2
    )
