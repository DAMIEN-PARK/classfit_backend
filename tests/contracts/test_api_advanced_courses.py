"""관리자 심화 과정(/v1/admin/advanced-courses…), T4 계획 결정 xiii·xvii · 증명 14·18.

추가는 id adv-<n> · pub 거짓 · active 참이다. id 번호는 시퀀스 pool_id_seq 에서 받고, import 가 넣은 adv-1… 과
겹치면 다음 번호로 넘어간다(존재 검사 루프). 삭제는 없고 active 로 사용 중지한다. 같은 값 PATCH 는 audit 없음.
"""

import re
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from classfit.database.session import make_session_factory
from classfit.models import AdvancedCourse
from scripts import import_ax_catalog
from tests.fixtures.courses import admin_headers
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.pool import ADMIN, audit_rows

ADV = f"{ADMIN}/advanced-courses"
SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "ax_catalog_sample.json"
BODY = {
    "title": "업무 자동화 심화",
    "audience": "실무자",
    "tool": "스프레드시트",
    "hours": 18,
    "goal": "반복 업무를 줄인다",
    "features": ["사례 실습", "결과물 발표"],
}


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


async def _create(
    client: httpx.AsyncClient, admin: dict[str, str], **over: object
) -> dict[str, object]:
    r = await client.post(ADV, headers=admin, json={**BODY, **over})
    assert r.status_code == 201, r.text
    body: dict[str, object] = r.json()
    return body


async def test_pool_advanced_create_patch_audit(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    aid, admin = await admin_headers(db_session)
    body = await _create(client, admin, title=" 업무 자동화 심화 ")
    adv_id = str(body["id"])
    assert re.fullmatch(r"adv-[0-9]+", adv_id), adv_id
    assert (body["title"], body["hours"], body["features"]) == (
        "업무 자동화 심화",
        18,
        ["사례 실습", "결과물 발표"],
    )
    assert (body["pub"], body["active"]) == (False, True)
    r = await client.patch(f"{ADV}/{adv_id}", headers=admin, json={"pub": True})
    assert (r.status_code, r.json()["pub"]) == (200, True), r.text
    audit = await audit_rows(db_session, "advanced_course.")
    assert [a[:4] for a in audit] == [
        ("advanced_course.create", f"admin:{aid}", "advanced_course", adv_id),
        ("advanced_course.update", f"admin:{aid}", "advanced_course", adv_id),
    ]
    assert audit[1][4] == {"changed": ["pub"]}


async def test_pool_advanced_create_after_import_201(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    # nextval 은 롤백돼도 소비된다. 앞 시험이 번호를 올려 두면 충돌이 안 나 시험이 헛돈다(계획 증명 18)
    await db_session.execute(text("ALTER SEQUENCE pool_id_seq RESTART WITH 1"))
    assert await import_ax_catalog.run([str(SAMPLE), "--apply"], factory) == 0
    imported = set(await db_session.scalars(select(AdvancedCourse.id)))
    assert imported == {"adv-1", "adv-2"}
    _, admin = await admin_headers(db_session)
    first = await _create(client, admin)
    second = await _create(client, admin, title="두 번째 심화")
    made = {str(first["id"]), str(second["id"])}
    assert len(made) == 2 and not made & imported, made
    assert await count(db_session, AdvancedCourse) == 4


async def test_pool_advanced_features_limit_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    for over, field in (
        ({"features": [f"특징 {n}" for n in range(6)]}, "features"),
        ({"hours": 0}, "hours"),
        ({"hours": 201}, "hours"),
        ({"title": ""}, "title"),
        ({"audience": "가" * 101}, "audience"),
    ):
        r = await client.post(ADV, headers=admin, json={**BODY, **over})
        assert locs(problem_of(r, 422)) == [["body", field]], over
    assert await count(db_session, AdvancedCourse) == 0
    adv_id = (await _create(client, admin))["id"]
    r = await client.patch(
        f"{ADV}/{adv_id}", headers=admin, json={"features": ["a"] * 6}
    )
    assert locs(problem_of(r, 422)) == [["body", "features"]]


async def test_pool_advanced_same_value_no_audit(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    adv_id = (await _create(client, admin))["id"]
    r = await client.patch(
        f"{ADV}/{adv_id}",
        headers=admin,
        json={"title": BODY["title"], "features": BODY["features"], "pub": False},
    )
    assert r.status_code == 200, r.text
    assert await audit_rows(db_session, "advanced_course.update") == []


async def test_pool_advanced_list_includes_inactive_for_admin(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    kept = str((await _create(client, admin))["id"])
    stopped = str((await _create(client, admin, title="중지할 심화"))["id"])
    r = await client.patch(f"{ADV}/{stopped}", headers=admin, json={"active": False})
    assert (r.status_code, r.json()["active"]) == (200, False)
    listed = await client.get(ADV, headers=admin)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert (body["has_more"], body["next_cursor"]) == (False, None)
    assert {i["id"]: i["active"] for i in body["items"]} == {kept: True, stopped: False}
    only = await client.get(ADV, headers=admin, params={"active": "false"})
    assert [i["id"] for i in only.json()["items"]] == [stopped]
