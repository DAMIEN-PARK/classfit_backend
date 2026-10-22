"""태그(GET /v1/tags · GET·POST /v1/admin/tags · PATCH /v1/admin/tags/{tag_id}), T3 계획 결정 xi.

공개 검색은 인증 없이 사용 중 태그만 최대 20개, 관리자 목록은 중지 포함 최대 500개다. 둘 다 커서가 없고
잘리면 has_more 만 참이다. 이름은 정규화(앞뒤 공백 · 연속 공백)해 (kind, name) 하나다. 바뀐 칸이 없으면 audit 도 없다.
"""

from typing import get_args

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.tag import create_missing_field_tags
from classfit.models import AuditLog, Tag
from classfit.schemas.tag import TagGroup
from classfit.service.rules.instructor import TAG_GROUPS
from tests.fixtures.courses import admin_headers
from tests.fixtures.instructors import (
    count,
    instructor_headers,
    locs,
    make_instructor,
    problem_of,
)

TAGS = "/v1/tags"
ADMIN_TAGS = "/v1/admin/tags"


async def _create(
    client: httpx.AsyncClient, admin: dict[str, str], name: str, **extra: object
) -> dict:
    r = await client.post(
        ADMIN_TAGS, headers=admin, json={"kind": "field", "name": name, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _tag_audit(session: AsyncSession, action: str) -> list[tuple]:
    rows = await session.execute(
        select(AuditLog.target_id, AuditLog.detail)
        .where(AuditLog.action == action)
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def test_tags_public_search_active_only(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    for n in range(1, 22):
        await _create(client, admin, f"분야 {n:02d}")
    stopped = await _create(client, admin, "분야 중지")
    r = await client.patch(
        f"{ADMIN_TAGS}/{stopped['id']}", headers=admin, json={"active": False}
    )
    assert r.status_code == 200, r.text
    await _create(client, admin, "다른 것")

    r = await client.get(TAGS, params={"q": "분야"})  # 인증 없음
    assert r.status_code == 200, r.text
    page = r.json()
    assert (len(page["items"]), page["has_more"], page["next_cursor"]) == (
        20,
        True,
        None,
    )
    names = [t["name"] for t in page["items"]]
    assert "분야 중지" not in names and "다른 것" not in names
    assert all(t["active"] and t["kind"] == "field" for t in page["items"])
    narrowed = (await client.get(TAGS, params={"q": "분야 0"})).json()
    assert [t["name"] for t in narrowed["items"]] == [
        f"분야 0{n}" for n in range(1, 10)
    ]
    assert narrowed["has_more"] is False
    middle = (await client.get(TAGS, params={"q": "야 2"})).json()
    assert [t["name"] for t in middle["items"]] == ["분야 20", "분야 21"]
    assert (await client.get(TAGS, params={"q": "중지"})).json()["items"] == []
    # % _ 는 글자 그대로다(전부 맞지 않는다)
    assert (await client.get(TAGS, params={"q": "%"})).json()["items"] == []
    problem_of(await client.get(TAGS, params={"q": "a\x00"}), 422)


async def test_admin_tags_post_and_patch_rename_reflects_in_profiles(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email="a@example.com")
    auth = await instructor_headers(db_session, iid)
    _, admin = await admin_headers(db_session)
    tag = (await client.get("/v1/me", headers=auth)).json()["tags"][0]
    assert (tag["name"], tag["group"]) == ("프롬프트", "기타")
    r = await client.patch(
        f"{ADMIN_TAGS}/{tag['id']}",
        headers=admin,
        json={"name": " 프롬프트   엔지니어링 ", "group": "AI 활용·업무자동화"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["group"], r.json()["used_by"]) == (
        "프롬프트 엔지니어링",
        "AI 활용·업무자동화",
        1,
    )
    me = (await client.get("/v1/me", headers=auth)).json()
    assert me["tags"] == [
        {"id": tag["id"], "name": "프롬프트 엔지니어링", "group": "AI 활용·업무자동화"}
    ]
    updates = await _tag_audit(db_session, "tag.update")
    assert len(updates) == 1 and updates[0][0] == str(tag["id"])
    assert sorted(updates[0][1]["fields"]) == ["group_name", "name"]

    created = await _create(client, admin, "데이터 분석")
    assert (created["group"], created["source"], created["used_by"]) == (
        "기타",
        "admin",
        0,
    )
    assert await _tag_audit(db_session, "tag.create") == [
        (str(created["id"]), {"kind": "field", "name": "데이터 분석"})
    ]
    listed = (await client.get(ADMIN_TAGS, headers=admin)).json()
    used = {t["name"]: t["used_by"] for t in listed["items"]}
    assert used == {"프롬프트 엔지니어링": 1, "데이터 분석": 0}
    assert listed["has_more"] is False

    # 관리자 목록 상한 500: 사용 중 태그를 501개로 채우면 500개 + has_more
    await create_missing_field_tags(
        db_session, [f"채움 {n:03d}" for n in range(499)], source="admin", group="기타"
    )
    assert await count(db_session, Tag) == 501
    full = (
        await client.get(ADMIN_TAGS, headers=admin, params={"kind": "field"})
    ).json()
    assert (len(full["items"]), full["has_more"], full["next_cursor"]) == (
        500,
        True,
        None,
    )


async def test_admin_tags_duplicate_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    first = await _create(client, admin, "데이터 분석")
    for name in ("데이터 분석", "  데이터   분석 "):
        r = await client.post(
            ADMIN_TAGS, headers=admin, json={"kind": "field", "name": name}
        )
        problem_of(r, 409, "/problems/conflict")
    other = await _create(client, admin, "엑셀")
    r = await client.patch(
        f"{ADMIN_TAGS}/{other['id']}", headers=admin, json={"name": "데이터 분석"}
    )
    problem_of(r, 409, "/problems/conflict")
    # 다른 종류에는 같은 이름이 있어도 된다
    r = await client.post(
        ADMIN_TAGS, headers=admin, json={"kind": "session", "name": "데이터 분석"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["group"] is None
    assert await count(db_session, Tag) == 3
    assert await count(db_session, Tag, Tag.id == first["id"]) == 1
    problem_of(
        await client.patch(
            f"{ADMIN_TAGS}/999999999", headers=admin, json={"active": True}
        ),
        404,
    )


async def test_admin_tags_bad_group_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 스키마의 대분류 사본은 rules 원본과 같다
    assert set(get_args(TagGroup)) == set(TAG_GROUPS)
    _, admin = await admin_headers(db_session)
    for body in (
        {"kind": "field", "name": "x", "group": "없는 분류"},
        {"kind": "session", "name": "x", "group": "기타"},  # field 만 대분류가 있다
    ):
        r = await client.post(ADMIN_TAGS, headers=admin, json=body)
        assert locs(problem_of(r, 422)) == [["body", "group"]], body
    tag = await _create(client, admin, "엑셀")
    session_tag = (
        await client.post(
            ADMIN_TAGS, headers=admin, json={"kind": "session", "name": "1교시"}
        )
    ).json()
    for tag_id, body in (
        (tag["id"], {"group": "없는 분류"}),
        (tag["id"], {"group": None}),
        (session_tag["id"], {"group": "기타"}),
    ):
        r = await client.patch(f"{ADMIN_TAGS}/{tag_id}", headers=admin, json=body)
        assert locs(problem_of(r, 422)) == [["body", "group"]], body
    group = await db_session.scalar(select(Tag.group_name).where(Tag.id == tag["id"]))
    assert group == "기타"
    assert await _tag_audit(db_session, "tag.update") == []


async def test_admin_tags_patch_same_value_no_audit(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    tag = await _create(client, admin, "엑셀", group="개발·데이터")
    url = f"{ADMIN_TAGS}/{tag['id']}"
    for body in ({"name": " 엑셀 "}, {"active": True}, {"group": "개발·데이터"}, {}):
        r = await client.patch(url, headers=admin, json=body)
        assert r.status_code == 200, (body, r.text)
    assert await _tag_audit(db_session, "tag.update") == []
    for _ in range(2):
        r = await client.patch(url, headers=admin, json={"active": False})
        assert r.status_code == 200 and r.json()["active"] is False
    assert await _tag_audit(db_session, "tag.update") == [
        (str(tag["id"]), {"fields": ["active"]})
    ]
