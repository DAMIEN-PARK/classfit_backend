"""강사 과정 풀(GET /v1/pool · /v1/pool/{pool_id}) · 본인 목록 셋, T4 계획 결정 i·vii·ix·xii·xvi · 증명 7·9.

풀은 활성 과정만이다(비활성은 404). 남의 고유 과정에도 작성자 키가 없고 mine 만 있다. 목록은 한 쪽 500 이고
넘으면 has_more 참·next_cursor null 이다. 본인 목록(역량·고유 과정·커리큘럼)은 비활성도 active 칸으로 보인다.
"""

import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.main import create_app
from classfit.models import PoolCourse
from classfit.schemas.curriculum import CurriculumOut
from classfit.schemas.pool import CapabilityOut, OwnCourseOut, PoolItemOut
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.enter import json_keys
from tests.fixtures.instructors import problem_of
from tests.fixtures.pool import (
    ME,
    NAME_B,
    PERSONAL_POOL_KEYS,
    add_pool_pdf,
    curriculum_body,
    instructor_pair,
    make_pool_course,
    own_body,
    set_flags,
)

POOL = "/v1/pool"
METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _pool_operations() -> list[tuple[str, str]]:
    spec = create_app(Settings()).openapi()
    return sorted(
        (method.upper(), re.sub(r"\{[^}]+\}", "1", path))
        for path, item in spec["paths"].items()
        if path == POOL or path.startswith(POOL + "/")
        for method in item
        if method in METHODS
    )


async def test_pool_me_lists_bodies(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    ax = await make_pool_course(db_session, source="ax", title="AX 과정 가")
    ids = []
    for title in ("내 과정 가", "내 과정 나"):
        r = await client.post(
            f"{ME}/own-courses", headers=auth, json=own_body(title=title)
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    assert (
        await client.delete(f"{ME}/own-courses/{ids[0]}", headers=auth)
    ).status_code == 204
    for pool_id in (ax.id, ids[1]):
        r = await client.put(f"{ME}/capabilities/{pool_id}", headers=auth, json={})
        assert r.status_code == 201, r.text
    cur_ids = []
    for title in ("내 커리큘럼 가", "내 커리큘럼 나"):
        r = await client.post(
            f"{ME}/curricula", headers=auth, json=curriculum_body(title=title)
        )
        assert r.status_code == 201, r.text
        cur_ids.append(r.json()["id"])
    assert (
        await client.delete(f"{ME}/curricula/{cur_ids[1]}", headers=auth)
    ).status_code == 204

    expected = {
        "own-courses": (OwnCourseOut, sorted(ids), "id"),
        "capabilities": (CapabilityOut, sorted([ax.id, ids[1]]), "pool_id"),
        "curricula": (CurriculumOut, sorted(cur_ids), "id"),
    }
    for name, (schema, order, key) in expected.items():
        r = await client.get(f"{ME}/{name}", headers=auth)
        assert r.status_code == 200, (name, r.text)
        body = r.json()
        assert set(body) == {"items", "next_cursor", "has_more"}, name
        assert (body["has_more"], body["next_cursor"]) == (False, None), name
        assert [i[key] for i in body["items"]] == order, name
        for item in body["items"]:
            assert set(item) == set(schema.model_fields), (name, set(item))
    own = (await client.get(f"{ME}/own-courses", headers=auth)).json()["items"]
    assert {i["id"]: i["active"] for i in own} == {ids[0]: False, ids[1]: True}
    curs = (await client.get(f"{ME}/curricula", headers=auth)).json()["items"]
    assert {i["id"]: i["active"] for i in curs} == {cur_ids[0]: True, cur_ids[1]: False}


async def test_pool_list_active_only_and_filters(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (aid, auth), _ = await instructor_pair(db_session, app.state.settings)
    common = await make_pool_course(
        db_session, source="ax", title="문서 요약 실습", difficulty="하"
    )
    office = await make_pool_course(
        db_session,
        source="ax",
        title="엑셀 함수",
        job_groups=["사무·행정"],
        difficulty="상",
    )
    hidden = await make_pool_course(db_session, source="ax", title="문서 숨김")
    await set_flags(db_session, hidden, active=False)
    mine = await make_pool_course(
        db_session, owner_instructor_id=aid, title="내 문서 과정", goal="보고서 초안"
    )

    async def ids(**params: str) -> list[str]:
        r = await client.get(POOL, headers=auth, params=params)
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["has_more"], body["next_cursor"]) == (False, None)
        for item in body["items"]:
            assert set(item) == set(PoolItemOut.model_fields)
        return [i["id"] for i in body["items"]]

    everything = await ids()
    assert hidden.id not in everything
    assert set(everything) == {common.id, office.id, mine.id}
    assert set(await ids(source="ax")) == {common.id, office.id}
    assert await ids(source="own") == [mine.id]
    assert await ids(job="사무·행정") == [office.id]
    assert set(await ids(job="공통(전 직원)")) == {common.id, mine.id}
    assert await ids(difficulty="상") == [office.id]
    assert set(await ids(q="문서")) == {common.id, mine.id}
    assert await ids(q="보고서") == [mine.id]  # 목표도 찾는다
    assert await ids(q="숨김") == []
    # 값 집합 밖은 422
    for params, field in (
        ({"job": "없는 직무"}, "job"),
        ({"difficulty": "최상"}, "difficulty"),
    ):
        body = problem_of(await client.get(POOL, headers=auth, params=params), 422)
        assert [v["loc"] for v in body["violations"]] == [["query", field]]

    # 한 쪽 500: 활성 501개를 더 넣으면 500개만 오고 has_more 참, 커서는 없다
    await db_session.execute(
        insert(PoolCourse),
        [
            {
                "id": f"ax-bulk-{n:04d}",
                "source": "ax",
                "title": f"대량 {n}",
                "job_groups": ["공통(전 직원)"],
                "difficulty": "중",
                "minutes": 60,
                "active": True,
            }
            for n in range(501)
        ],
    )
    body = (await client.get(POOL, headers=auth)).json()
    assert len(body["items"]) == 500
    assert (body["has_more"], body["next_cursor"]) == (True, None)


async def test_pool_list_other_own_course_has_no_author_keys(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    r = await client.post(
        f"{ME}/own-courses", headers=auth_b, json=own_body(title="B 과정")
    )
    assert r.status_code == 201, r.text
    pool_id = r.json()["id"]
    listed = await client.get(POOL, headers=auth_a)
    item = next(i for i in listed.json()["items"] if i["id"] == pool_id)
    assert (item["source"], item["mine"]) == ("own", False)
    detail = await client.get(f"{POOL}/{pool_id}", headers=auth_a)
    assert detail.status_code == 200, detail.text
    assert (detail.json()["mine"], detail.json()["files"]) == (False, [])
    for r in (listed, detail):
        assert json_keys(r.json()) & PERSONAL_POOL_KEYS == set()
        assert NAME_B not in r.text
        assert "instructor-b@example.com" not in r.text
    # 작성자 본인에게는 mine 참
    mine = await client.get(f"{POOL}/{pool_id}", headers=auth_b)
    assert mine.json()["mine"] is True


async def test_pool_detail_mine_has_files_other_has_none(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (_, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    r = await client.post(f"{ME}/own-courses", headers=auth_a, json=own_body())
    pool_id = r.json()["id"]
    up = await add_pool_pdf(client, auth_a, f"{ME}/own-courses/{pool_id}/files")
    assert up.status_code == 201, up.text
    mine = (await client.get(f"{POOL}/{pool_id}", headers=auth_a)).json()
    assert mine["mine"] is True
    assert [(f["id"], f["kind"], f["href"]) for f in mine["files"]] == [
        (up.json()["id"], "pdf", up.json()["href"])
    ]
    other = (await client.get(f"{POOL}/{pool_id}", headers=auth_b)).json()
    assert (other["mine"], other["files"]) == (False, [])
    assert up.json()["href"] not in str(other)


async def test_pool_detail_inactive_404_for_instructor_200_for_admin(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    row = await make_pool_course(db_session, source="ax")
    assert (await client.get(f"{POOL}/{row.id}", headers=auth)).status_code == 200
    await set_flags(db_session, row, active=False)
    problem_of(
        await client.get(f"{POOL}/{row.id}", headers=auth), 404, "/problems/not_found"
    )
    listed = (await client.get(POOL, headers=auth)).json()["items"]
    assert row.id not in [i["id"] for i in listed]
    r = await client.get(f"/v1/admin/pool/{row.id}", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    # 없는 id · 모양 밖 id 도 같은 404
    for pool_id in ("ax-none-1", "AX%201", "a" * 200):
        problem_of(await client.get(f"{POOL}/{pool_id}", headers=auth), 404)


async def test_pool_list_capable_flag_follows_capability(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax")

    async def capable(headers: dict[str, str]) -> tuple[bool, bool]:
        items = (await client.get(POOL, headers=headers)).json()["items"]
        listed = next(i["capable"] for i in items if i["id"] == row.id)
        detail = (await client.get(f"{POOL}/{row.id}", headers=headers)).json()
        return listed, detail["capable"]

    assert await capable(auth) == (False, False)
    assert (
        await client.put(f"{ME}/capabilities/{row.id}", headers=auth)
    ).status_code == 201
    assert await capable(auth) == (True, True)
    assert await capable(auth_b) == (False, False)  # 남의 표시는 내 capable 이 아니다
    assert (
        await client.delete(f"{ME}/capabilities/{row.id}", headers=auth)
    ).status_code == 204
    assert await capable(auth) == (False, False)


async def test_pool_paths_admin_403_and_no_token_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operations = _pool_operations()
    assert operations == [("GET", POOL), ("GET", f"{POOL}/1")], operations
    _, admin = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    learner = await learner_headers(db_session, course.id)
    wrong = []
    for method, path in operations:
        as_admin = await client.request(method, path, headers=admin)
        as_learner = await client.request(method, path, headers=learner)
        anonymous = await client.request(method, path)
        if (
            as_admin.status_code != 403
            or as_learner.status_code != 403
            or anonymous.status_code != 401
            or anonymous.headers.get("www-authenticate") != "Bearer"
        ):
            wrong.append(
                (
                    method,
                    path,
                    as_admin.status_code,
                    as_learner.status_code,
                    anonymous.status_code,
                )
            )
    assert wrong == []
