"""강사 고유 과정(/v1/me/own-courses…) · 고유 과정 파일, T4 계획 결정 i·vi·xi·xiii·xvi · 증명 5·6·10·12.

판정 순서는 404 → 403(AX · 남의 것) → 409(비활성)다. 본인 것은 비활성도 목록·GET 에 active 거짓으로 보이고,
PATCH·파일 넣기는 409, DELETE 는 204 멱등이다. 검토 뒤 고치면 reviewed 만 거짓으로 돌아가고 pub·active 는 그대로다.
DELETE 는 지우지 않고 active 를 끈다(행·역량·파일 유지).
"""

import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import Capability, PoolCourse, PoolCourseFile, StoredFile
from tests.fixtures.courses import _bearer, admin_headers, open_test_course
from tests.fixtures.instructors import (
    count,
    instructor_headers,
    locs,
    make_instructor,
    problem_of,
)
from tests.fixtures.pool import (
    ADMIN,
    ME,
    OWN_DEFAULTS,
    add_pool_pdf,
    audit_rows,
    instructor_pair,
    make_pool_course,
    own_body,
    set_flags,
)

OWN = f"{ME}/own-courses"


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


async def _create(
    client: httpx.AsyncClient, headers: dict[str, str], **over: object
) -> str:
    r = await client.post(OWN, headers=headers, json=own_body(**over))
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _row(session: AsyncSession, pool_id: str) -> PoolCourse:
    row = await session.scalar(
        select(PoolCourse)
        .where(PoolCourse.id == pool_id)
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def test_pool_own_course_inactive_visible_to_owner_patch_409(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    pool_id = await _create(client, auth)
    assert (await client.delete(f"{OWN}/{pool_id}", headers=auth)).status_code == 204
    listed = (await client.get(OWN, headers=auth)).json()["items"]
    assert [(i["id"], i["active"]) for i in listed] == [(pool_id, False)]
    got = await client.get(f"{OWN}/{pool_id}", headers=auth)
    assert (got.status_code, got.json()["active"]) == (200, False)
    problem_of(
        await client.patch(f"{OWN}/{pool_id}", headers=auth, json={"title": "새 제목"}),
        409,
        "/problems/conflict",
    )
    problem_of(await add_pool_pdf(client, auth, f"{OWN}/{pool_id}/files"), 409)
    assert (await client.delete(f"{OWN}/{pool_id}", headers=auth)).status_code == 204
    problem_of(await client.get(f"/v1/pool/{pool_id}", headers=auth), 404)
    # 관리자가 되살린 뒤에는 고친다
    r = await client.patch(
        f"{ADMIN}/pool/{pool_id}", headers=admin, json={"active": True}
    )
    assert r.status_code == 200, r.text
    r = await client.patch(f"{OWN}/{pool_id}", headers=auth, json={"title": "새 제목"})
    assert (r.status_code, r.json()["title"]) == (200, "새 제목")
    assert await count(db_session, PoolCourseFile) == 0


async def test_pool_own_course_create_pending_instructor_201(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email="instructor-a@example.com"
    )
    auth = await instructor_headers(db_session, iid)
    r = await client.post(OWN, headers=auth, json=own_body(title=" 현장 문서 자동화 "))
    assert r.status_code == 201, r.text
    body = r.json()
    assert re.fullmatch(rf"own-{iid}-[0-9]+", body["id"]), body["id"]
    assert (body["source"], body["title"], body["mine"]) == (
        "own",
        "현장 문서 자동화",
        True,
    )
    assert (body["reviewed"], body["reviewed_at"], body["pub"], body["active"]) == (
        False,
        None,
        False,
        True,
    )
    for key in (
        "job_groups",
        "difficulty",
        "minutes",
        "theory",
        "practice",
        "schedule",
    ):
        assert body[key] == OWN_DEFAULTS[key], key
    row = await _row(db_session, body["id"])
    assert (row.source, row.owner_instructor_id) == ("own", iid)
    assert [a[:4] for a in await audit_rows(db_session, "pool_course.")] == [
        ("pool_course.create", f"instructor:{iid}", "pool_course", body["id"])
    ]


async def test_pool_own_course_zero_job_groups_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    for groups in ([], ["없는 직무"], ["사무·행정", "사무·행정"]):
        r = await client.post(OWN, headers=auth, json=own_body(job_groups=groups))
        assert locs(problem_of(r, 422)) == [["body", "job_groups"]], groups
    for over, field in (
        ({"difficulty": "최상"}, "difficulty"),
        ({"minutes": 0}, "minutes"),
        ({"title": "  "}, "title"),
    ):
        r = await client.post(OWN, headers=auth, json=own_body(**over))
        assert locs(problem_of(r, 422)) == [["body", field]], over
    assert await count(db_session, PoolCourse) == 0
    pool_id = await _create(client, auth)
    for body in ({"job_groups": []}, {"job_groups": None}, {"title": None}):
        r = await client.patch(f"{OWN}/{pool_id}", headers=auth, json=body)
        assert locs(problem_of(r, 422))[0][:2] == ["body", next(iter(body))], body


async def test_pool_own_course_patch_resets_reviewed_keeps_pub_active(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (aid, auth), _ = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    pool_id = await _create(client, auth)
    for flags in ({"reviewed": True}, {"pub": True}):
        r = await client.patch(f"{ADMIN}/pool/{pool_id}", headers=admin, json=flags)
        assert r.status_code == 200, r.text
    reviewed_at = r.json()["reviewed_at"]
    assert reviewed_at is not None
    r = await client.patch(
        f"{OWN}/{pool_id}", headers=auth, json={"title": "고친 제목"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["reviewed"], body["reviewed_at"], body["pub"], body["active"]) == (
        False,
        reviewed_at,
        True,
        True,
    )
    updates = [
        a
        for a in await audit_rows(db_session, "pool_course.update")
        if a[1] == f"instructor:{aid}"
    ]
    assert [(a[3], a[4]) for a in updates] == [(pool_id, {"changed": ["title"]})]


async def test_pool_own_course_edit_ax_403(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    ax = await make_pool_course(db_session, source="ax", title="AX 원본")
    path = f"{OWN}/{ax.id}"
    responses = {
        "PATCH": await client.patch(path, headers=auth, json={"title": "x"}),
        "DELETE": await client.delete(path, headers=auth),
        "POST files": await add_pool_pdf(client, auth, f"{path}/files"),
        "GET": await client.get(path, headers=auth),
    }
    statuses = {name: r.status_code for name, r in responses.items()}
    assert statuses == dict.fromkeys(responses, 403)
    for r in responses.values():
        problem_of(r, 403, "/problems/forbidden")
    row = await _row(db_session, ax.id)
    assert (row.title, row.active, row.source) == ("AX 원본", True, "ax")
    assert await count(db_session, PoolCourseFile) == 0
    assert await count(db_session, StoredFile) == 0


async def test_pool_own_course_other_instructor_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    pool_id = await _create(client, auth_b, title="B 과정")
    path = f"{OWN}/{pool_id}"
    for r in (
        await client.patch(path, headers=auth_a, json={"title": "x"}),
        await client.delete(path, headers=auth_a),
        await client.get(path, headers=auth_a),
    ):
        problem_of(r, 403, "/problems/forbidden")
    row = await _row(db_session, pool_id)
    assert (row.title, row.active) == ("B 과정", True)
    # 없는 id 는 404(판정 순서 404 → 403)
    problem_of(
        await client.patch(f"{OWN}/own-0-0", headers=auth_a, json={"title": "x"}), 404
    )
    problem_of(await client.get(f"{OWN}/own-0-0", headers=auth_a), 404)


async def test_pool_own_course_delete_deactivates_keeps_row_and_files(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (aid, auth), _ = await instructor_pair(db_session, app.state.settings)
    pool_id = await _create(client, auth)
    up = await add_pool_pdf(client, auth, f"{OWN}/{pool_id}/files")
    assert up.status_code == 201, up.text
    r = await client.put(f"{ME}/capabilities/{pool_id}", headers=auth, json={})
    assert r.status_code == 201, r.text
    assert (await client.delete(f"{OWN}/{pool_id}", headers=auth)).status_code == 204
    row = await _row(db_session, pool_id)
    assert row.active is False
    assert await count(db_session, PoolCourseFile) == 1
    assert await count(db_session, StoredFile) == 1
    assert await count(db_session, Capability) == 1
    listed = (await client.get("/v1/pool", headers=auth)).json()["items"]
    assert pool_id not in [i["id"] for i in listed]
    # 다시 지워도 204, audit 은 한 번
    assert (await client.delete(f"{OWN}/{pool_id}", headers=auth)).status_code == 204
    deactivated = await audit_rows(db_session, "pool_course.deactivate")
    assert [a[:4] for a in deactivated] == [
        ("pool_course.deactivate", f"instructor:{aid}", "pool_course", pool_id)
    ]
    # 파일은 본인이 계속 연다
    assert (await client.get(up.json()["href"], headers=auth)).status_code == 200


async def test_pool_own_course_file_pdf_and_delete(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (aid, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    pool_id = await _create(client, auth_a)
    up = await add_pool_pdf(client, auth_a, f"{OWN}/{pool_id}/files")
    assert up.status_code == 201, up.text
    href, file_id = up.json()["href"], up.json()["id"]
    stored = await db_session.scalar(select(StoredFile))
    assert stored is not None
    assert (stored.owner_kind, stored.owner_id) == ("pool_course_file", file_id)
    course, _ = await open_test_course(db_session)
    same_id_learner = await _bearer(
        db_session, "same-id-learner", "learner", aid, course.id
    )
    statuses = {
        "본인": (await client.get(href, headers=auth_a)).status_code,
        "관리자": (await client.get(href, headers=admin)).status_code,
        "B 강사": (await client.get(href, headers=auth_b)).status_code,
        "같은 id 수강생": (await client.get(href, headers=same_id_learner)).status_code,
    }
    assert statuses == {
        "본인": 200,
        "관리자": 200,
        "B 강사": 403,
        "같은 id 수강생": 403,
    }
    problem_of(await client.delete(f"{ME}/pool-files/{file_id}", headers=auth_b), 403)
    r = await client.delete(f"{ME}/pool-files/{file_id}", headers=auth_a)
    assert r.status_code == 204, r.text
    assert await count(db_session, PoolCourseFile) == 0
    assert await count(db_session, StoredFile) == 0
    problem_of(await client.get(href, headers=auth_a), 404)
    problem_of(await client.delete(f"{ME}/pool-files/{file_id}", headers=auth_a), 404)
    assert [a[0] for a in await audit_rows(db_session, "pool_course_file.")] == [
        "pool_course_file.create",
        "pool_course_file.delete",
    ]


async def test_pool_own_course_same_value_patch_no_audit(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    pool_id = await _create(client, auth)
    row = await _row(db_session, pool_id)
    await set_flags(db_session, row, reviewed=True)
    same = {
        "title": OWN_DEFAULTS["title"],
        "job_groups": OWN_DEFAULTS["job_groups"],
        "difficulty": OWN_DEFAULTS["difficulty"],
        "minutes": OWN_DEFAULTS["minutes"],
        "goal": OWN_DEFAULTS["goal"],
        "theory": OWN_DEFAULTS["theory"],
        "schedule": OWN_DEFAULTS["schedule"],
        "material": None,
    }
    r = await client.patch(f"{OWN}/{pool_id}", headers=auth, json=same)
    assert r.status_code == 200, r.text
    assert r.json()["reviewed"] is True
    assert await audit_rows(db_session, "pool_course.update") == []
    # 빈 본문도 200 · audit 없음
    r = await client.patch(f"{OWN}/{pool_id}", headers=auth, json={})
    assert (r.status_code, r.json()["reviewed"]) == (200, True)
    assert await audit_rows(db_session, "pool_course.update") == []
