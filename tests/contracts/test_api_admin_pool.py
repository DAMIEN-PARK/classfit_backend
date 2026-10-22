"""관리자 과정 풀·커리큘럼(/v1/admin/pool… · /v1/admin/curricula…), T4 계획 결정 i·v·vi·xviii · 증명 7·8·14.

AX 추가는 id ax-custom-<n> · reviewed 참 · pub 거짓. PATCH 는 AX 행에 내용 + active·pub, 고유 과정 행에 플래그 셋만이고
고칠 수 없는 칸은 422 type not_editable. 미검토 항목의 pub 켜기는 409 + reviewed: false, 검토 해제는 pub 도 끈다.
한 본문의 플래그는 reviewed → pub → active 순이다. 같은 값 PATCH 는 200 + audit 없음.
"""

import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import Capability, CapabilityFile, PoolCourse
from tests.fixtures.courses import admin_headers
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.pool import (
    ADMIN,
    ME,
    NAME_A,
    NAME_B,
    OWN_DEFAULTS,
    add_pool_pdf,
    audit_rows,
    curriculum_body,
    instructor_pair,
    make_curriculum,
    make_pool_course,
    own_body,
    set_flags,
)

POOL = f"{ADMIN}/pool"


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


async def _row(session: AsyncSession, pool_id: str) -> PoolCourse:
    row = await session.scalar(
        select(PoolCourse)
        .where(PoolCourse.id == pool_id)
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def test_pool_admin_ax_create_reviewed_true_and_patch_content(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    aid, admin = await admin_headers(db_session)
    r = await client.post(
        f"{POOL}/ax", headers=admin, json=own_body(title="새 AX 과정")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    pool_id = body["id"]
    assert re.fullmatch(r"ax-custom-[0-9]+", pool_id), pool_id
    assert (body["source"], body["owner"], body["capable_count"]) == ("ax", None, 0)
    assert (body["reviewed"], body["pub"], body["active"]) == (True, False, True)
    assert body["reviewed_at"] is not None
    r = await client.patch(
        f"{POOL}/{pool_id}",
        headers=admin,
        json={"title": "고친 AX 과정", "job_groups": ["사무·행정", "기획·전략"]},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["title"], r.json()["job_groups"]) == (
        "고친 AX 과정",
        ["사무·행정", "기획·전략"],
    )
    assert r.json()["reviewed"] is True  # AX 는 검토 개념이 없다
    audit = await audit_rows(db_session, "pool_course.")
    assert [a[:4] for a in audit] == [
        ("pool_course.create", f"admin:{aid}", "pool_course", pool_id),
        ("pool_course.update", f"admin:{aid}", "pool_course", pool_id),
    ]
    assert sorted(audit[1][4]["changed"]) == ["job_groups", "title"]


async def test_pool_admin_pub_requires_reviewed_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (iid, _), _ = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    row = await make_pool_course(db_session, owner_instructor_id=iid)
    path = f"{POOL}/{row.id}"

    async def flags() -> tuple[bool, bool, bool]:
        got = await _row(db_session, row.id)
        return got.reviewed, got.pub, got.reviewed_at is not None

    body = problem_of(
        await client.patch(path, headers=admin, json={"pub": True}),
        409,
        "/problems/conflict",
    )
    assert body["reviewed"] is False
    assert await flags() == (False, False, False)
    assert (
        await client.patch(path, headers=admin, json={"reviewed": True})
    ).status_code == 200
    r = await client.patch(path, headers=admin, json={"pub": True})
    assert (r.status_code, r.json()["pub"]) == (200, True)
    # 검토 해제는 pub 도 끄고 reviewed_at 을 비운다
    r = await client.patch(path, headers=admin, json={"reviewed": False})
    assert (r.json()["reviewed"], r.json()["pub"], r.json()["reviewed_at"]) == (
        False,
        False,
        None,
    )
    # 합친 본문: reviewed → pub 순
    r = await client.patch(path, headers=admin, json={"reviewed": True, "pub": True})
    assert (r.status_code, r.json()["reviewed"], r.json()["pub"]) == (200, True, True)
    problem_of(
        await client.patch(path, headers=admin, json={"reviewed": False, "pub": True}),
        409,
    )
    assert await flags() == (True, True, True)  # 아무것도 쓰지 않았다


async def test_pool_admin_patch_own_content_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (iid, _), _ = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    own = await make_pool_course(db_session, owner_instructor_id=iid)
    ax = await make_pool_course(db_session, source="ax")
    r = await client.patch(
        f"{POOL}/{own.id}", headers=admin, json={"title": "x", "reviewed": True}
    )
    body = problem_of(r, 422)
    assert [(v["loc"], v["type"]) for v in body["violations"]] == [
        (["body", "title"], "not_editable")
    ]
    r = await client.patch(f"{POOL}/{ax.id}", headers=admin, json={"reviewed": False})
    body = problem_of(r, 422)
    assert [(v["loc"], v["type"]) for v in body["violations"]] == [
        (["body", "reviewed"], "not_editable")
    ]
    assert (
        (await _row(db_session, own.id)).title,
        (await _row(db_session, own.id)).reviewed,
    ) == (
        OWN_DEFAULTS["title"],
        False,
    )
    assert (await _row(db_session, ax.id)).reviewed is True
    assert await audit_rows(db_session, "pool_course.update") == []


async def test_pool_admin_patch_same_value_no_audit(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    ax = await make_pool_course(db_session, source="ax")
    same = {
        "title": OWN_DEFAULTS["title"],
        "job_groups": OWN_DEFAULTS["job_groups"],
        "schedule": OWN_DEFAULTS["schedule"],
        "pub": False,
        "active": True,
    }
    r = await client.patch(f"{POOL}/{ax.id}", headers=admin, json=same)
    assert r.status_code == 200, r.text
    r = await client.patch(f"{POOL}/{ax.id}", headers=admin, json={})
    assert r.status_code == 200, r.text
    assert await audit_rows(db_session, "pool_course.update") == []


async def test_pool_admin_list_shows_owner_and_capable_count(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth_a), (bid, auth_b) = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    ax = await make_pool_course(db_session, source="ax", title="AX 과정")
    own = await make_pool_course(db_session, owner_instructor_id=bid, title="B 과정")
    stopped = await make_pool_course(db_session, source="ax", title="중지 과정")
    await set_flags(db_session, stopped, active=False)
    for auth in (auth_a, auth_b):
        r = await client.put(f"{ME}/capabilities/{ax.id}", headers=auth, json={})
        assert r.status_code == 201, r.text
    r = await client.get(POOL, headers=admin)
    assert r.status_code == 200, r.text
    items = {i["id"]: i for i in r.json()["items"]}
    assert set(items) == {ax.id, own.id, stopped.id}  # 비활성 포함
    assert (items[ax.id]["owner"], items[ax.id]["capable_count"]) == (None, 2)
    assert items[own.id]["owner"] == {"id": bid, "name": NAME_B}
    assert items[own.id]["capable_count"] == 0
    assert (items[stopped.id]["active"], r.json()["has_more"]) == (False, False)

    async def ids(**params: str) -> set[str]:
        got = await client.get(POOL, headers=admin, params=params)
        assert got.status_code == 200, got.text
        return {i["id"] for i in got.json()["items"]}

    assert await ids(active="false") == {stopped.id}
    assert await ids(reviewed="false") == {own.id}
    assert await ids(source="own") == {own.id}
    assert await ids(q="중지") == {stopped.id}


async def test_pool_admin_deactivate_hides_from_instructor_pool(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (_, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    ax = await make_pool_course(db_session, source="ax")
    r = await client.put(f"{ME}/capabilities/{ax.id}", headers=auth_a, json={})
    assert r.status_code == 201, r.text
    up = await add_pool_pdf(client, auth_a, f"{ME}/capabilities/{ax.id}/files")
    assert up.status_code == 201, up.text
    r = await client.patch(f"{POOL}/{ax.id}", headers=admin, json={"active": False})
    assert (r.status_code, r.json()["active"]) == (200, False)
    listed = (await client.get("/v1/pool", headers=auth_a)).json()["items"]
    assert ax.id not in [i["id"] for i in listed]
    problem_of(await client.get(f"/v1/pool/{ax.id}", headers=auth_a), 404)
    problem_of(
        await client.put(f"{ME}/capabilities/{ax.id}", headers=auth_b, json={}),
        409,
        "/problems/conflict",
    )
    assert await count(db_session, Capability) == 1
    assert await count(db_session, CapabilityFile) == 1
    # 본인의 역량 목록에는 남고 파일도 연다
    mine = (await client.get(f"{ME}/capabilities", headers=auth_a)).json()["items"]
    assert [i["pool_id"] for i in mine] == [ax.id]
    assert (await client.get(up.json()["href"], headers=auth_a)).status_code == 200


async def test_pool_admin_curricula_list_and_patch_flags(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (aid, auth_a), (bid, _) = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    r = await client.post(f"{ME}/curricula", headers=auth_a, json=curriculum_body())
    assert r.status_code == 201, r.text
    cur_a = r.json()["id"]
    cur_b = (
        await make_curriculum(db_session, instructor_id=bid, title="B 커리큘럼")
    ).id
    r = await client.get(f"{ADMIN}/curricula", headers=admin)
    assert r.status_code == 200, r.text
    items = {i["id"]: i for i in r.json()["items"]}
    assert items[cur_a]["owner"] == {"id": aid, "name": NAME_A}
    assert items[cur_b]["owner"] == {"id": bid, "name": NAME_B}
    problem_of(
        await client.patch(
            f"{ADMIN}/curricula/{cur_a}", headers=admin, json={"pub": True}
        ),
        409,
        "/problems/conflict",
    )
    r = await client.patch(
        f"{ADMIN}/curricula/{cur_a}",
        headers=admin,
        json={"reviewed": True, "pub": True},
    )
    assert (r.status_code, r.json()["reviewed"], r.json()["pub"]) == (200, True, True)
    r = await client.patch(
        f"{ADMIN}/curricula/{cur_b}", headers=admin, json={"active": False}
    )
    assert (r.status_code, r.json()["active"]) == (200, False)
    reviewed = await client.get(
        f"{ADMIN}/curricula", headers=admin, params={"reviewed": "true"}
    )
    assert [i["id"] for i in reviewed.json()["items"]] == [cur_a]
    inactive = await client.get(
        f"{ADMIN}/curricula", headers=admin, params={"active": "false"}
    )
    assert [i["id"] for i in inactive.json()["items"]] == [cur_b]
    got = await client.get(f"{ADMIN}/curricula/{cur_a}", headers=admin)
    assert (got.status_code, got.json()["owner"]["id"]) == (200, aid)
    # 409 는 아무것도 쓰지 않았다: 성공한 PATCH 둘만 audit
    updates = await audit_rows(db_session, "curriculum.update")
    assert len(updates) == 2


async def test_pool_admin_unknown_404(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    for path in (
        f"{POOL}/ax-none-1",
        f"{POOL}/BAD%20ID",
        f"{ADMIN}/curricula/cur-0-0",
    ):
        problem_of(await client.get(path, headers=admin), 404, "/problems/not_found")
        problem_of(
            await client.patch(path, headers=admin, json={"active": False}),
            404,
            "/problems/not_found",
        )
    problem_of(
        await client.patch(
            f"{ADMIN}/advanced-courses/adv-0", headers=admin, json={"active": False}
        ),
        404,
        "/problems/not_found",
    )
    assert locs(
        problem_of(
            await client.patch(f"{POOL}/ax-none-1", headers=admin, json={"pub": None}),
            422,
        )
    ) == [["body", "pub"]]


async def test_pool_admin_detail_has_capable_names_and_files(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (aid, auth_a), (bid, auth_b) = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    r = await client.post(f"{ME}/own-courses", headers=auth_a, json=own_body())
    pool_id = r.json()["id"]
    up = await add_pool_pdf(client, auth_a, f"{ME}/own-courses/{pool_id}/files")
    assert up.status_code == 201, up.text
    r = await client.put(f"{ME}/capabilities/{pool_id}", headers=auth_b, json={})
    assert r.status_code == 201, r.text
    got = await client.get(f"{POOL}/{pool_id}", headers=admin)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["owner"] == {"id": aid, "name": NAME_A}
    assert body["capable"] == [{"instructor_id": bid, "name": NAME_B}]
    assert body["capable_count"] == 1
    assert [(f["id"], f["href"]) for f in body["files"]] == [
        (up.json()["id"], up.json()["href"])
    ]
    for key in ("material", "theory", "practice", "schedule"):
        assert body[key] == OWN_DEFAULTS[key], key
    # 관리자는 기본 강의안을 바로 연다(기획안 :789)
    assert (await client.get(up.json()["href"], headers=admin)).status_code == 200
