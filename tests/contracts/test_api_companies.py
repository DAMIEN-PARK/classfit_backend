"""회사 관리: 등록·조회·수정·목록·삭제 규칙(T9a 계획 결정 iii·xi·xii·xiii·xxiv · 증명 12·13).

회사명·담당자 필수, 부서 ≤ 20(중복 422), 규모 5구간 코드. 목록·상세는 회차 요약 둘(last_round = round_no 최대 · latest_final_round
= final 가운데 최대)을 싣고 17지표 전 회차의 level 은 null 이다. 활성(보관하지 않은) 연결 강의가 있으면 삭제 409, 보관 강의의
연결은 풀리고(course.company_id null), 회차·링크는 같이 지워진다. 응답은 허용 키 집합을 정확히 잰다.
"""

from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import AuditLog, Company, Course, DiagLink, Diagnosis
from tests.fixtures.assign import approved
from tests.fixtures.courses import admin_headers
from tests.fixtures.diagnosis import (
    ANSWERS_ALL_1,
    ANSWERS_ALL_5,
    COMPANY_BODY,
    COMPANY_KEYS,
    DETAIL_KEYS,
    ROUND_BRIEF_KEYS,
    TODAY,
    UNDATED_BODY,
    set_today,
)
from tests.fixtures.instructors import count, locs, problem_of

ADMIN = "/v1/admin"
URL = f"{ADMIN}/companies"
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _company(
    client: httpx.AsyncClient, auth: dict[str, str], **over: Any
) -> dict[str, Any]:
    return _ok(await client.post(URL, headers=auth, json={**COMPANY_BODY, **over}), 201)


async def _round(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    company_id: int,
    answers: dict[str, int] | None = None,
    *,
    finalize: bool = False,
) -> int:
    rid: int = _ok(
        await client.post(
            f"{URL}/{company_id}/diagnoses", headers=auth, json={"phase": "pre"}
        ),
        201,
    )["id"]
    if answers is not None:
        _ok(
            await client.patch(
                f"{ADMIN}/diagnoses/{rid}", headers=auth, json={"answers": answers}
            )
        )
    if finalize:
        _ok(await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth))
    return rid


async def _audits(session: AsyncSession, action: str, company_id: int) -> list[Any]:
    rows = await session.scalars(
        select(AuditLog.detail).where(
            AuditLog.action == action,
            AuditLog.target_type == "company",
            AuditLog.target_id == str(company_id),
        )
    )
    return list(rows)


async def test_company_crud_and_keys(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    _, x_auth = await approved(db_session, app.state.settings, email="x@example.com")

    made = await _company(client, auth)
    assert set(made) == COMPANY_KEYS
    assert (made["name"], made["contact"], made["size"], made["depts"]) == (
        "A사",
        "담당자 가",
        "s10_49",
        ["영업", "생산"],
    )
    assert (made["last_round"], made["latest_final_round"]) == (None, None)
    a = made["id"]
    detail = _ok(await client.get(f"{URL}/{a}", headers=auth))
    assert set(detail) == DETAIL_KEYS
    assert (detail["rounds"], detail["links"], detail["courses"]) == ([], [], [])
    assert len(await _audits(db_session, "company.create", a)) == 1

    got = _ok(
        await client.patch(
            f"{URL}/{a}", headers=auth, json={"memo": "메모", "phone": "02-000-0000"}
        )
    )
    assert set(got) == DETAIL_KEYS
    assert (got["memo"], got["phone"]) == ("메모", "02-000-0000")
    _ok(await client.patch(f"{URL}/{a}", headers=auth, json={"memo": "메모"}))
    (updated,) = await _audits(db_session, "company.update", a)  # 같은 값은 audit 없음
    assert sorted(updated["fields"]) == ["memo", "phone"]
    got = _ok(await client.patch(f"{URL}/{a}", headers=auth, json={"phone": None}))
    assert got["phone"] is None

    # final r1(전부 1 → 160 · L2) + draft r2(9개 답) — 목록은 r2, 개설 ③ 고르기는 r1
    await _round(client, auth, a, ANSWERS_ALL_1, finalize=True)
    nine = dict(list(ANSWERS_ALL_5.items())[:9])
    await _round(client, auth, a, nine)
    page = _ok(await client.get(URL, headers=auth))
    assert set(page) == {"items", "next_cursor", "has_more"}
    (item,) = page["items"]
    detail = _ok(await client.get(f"{URL}/{a}", headers=auth))
    for body in (item, detail):
        last, final = body["last_round"], body["latest_final_round"]
        assert set(last) == ROUND_BRIEF_KEYS and set(final) == ROUND_BRIEF_KEYS
        assert (last["round_no"], last["status"], last["level"]) == (2, "draft", None)
        assert (final["round_no"], final["status"], final["total"], final["level"]) == (
            1,
            "final",
            160,
            2,
        )
    assert [(r["round_no"], r["level"]) for r in detail["rounds"]] == [
        (1, 2),
        (2, None),
    ]

    # 검색 q(이름·담당자·업종 · % 는 글자) · 커서
    b = (await _company(client, auth, name="B사", contact="담당%자 나"))["id"]
    c = (await _company(client, auth, name="C사", contact="담당 다", industry="제조"))[
        "id"
    ]

    async def ids(**params: Any) -> list[int]:
        r = await client.get(URL, headers=auth, params=params)
        return sorted(i["id"] for i in _ok(r)["items"])

    assert await ids(q="%자") == [b]
    assert await ids(q="담당") == sorted([a, b, c])
    assert await ids(q="제조") == [c]
    assert await ids(q="B사") == [b]
    first = _ok(await client.get(URL, headers=auth, params={"limit": 1}))
    assert first["has_more"] is True and first["next_cursor"]
    second = _ok(
        await client.get(
            URL, headers=auth, params={"limit": 1, "cursor": first["next_cursor"]}
        )
    )
    assert len(first["items"]) == len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    got = problem_of(await client.get(URL, headers=auth, params={"cursor": "x"}), 422)
    assert locs(got) == [["query", "cursor"]]
    got = problem_of(await client.get(URL, headers=auth, params={"q": "a\x01"}), 422)
    assert locs(got) == [["query", "q"]]

    # 모양 밖은 422 · 행 그대로
    before = await count(db_session, Company)
    for over in (
        {"name": "   "},
        {"contact": ""},
        {"size": "big"},
        {"depts": [f"부서 {i}" for i in range(21)]},
        {"depts": ["영업", "영업"]},
        {"phone": "0" * 51},
        {"name": "A\x01사"},
        {"memo": "메\x00모"},
        {"extra": 1},
    ):
        problem_of(
            await client.post(URL, headers=auth, json={**COMPANY_BODY, **over}), 422
        )
    assert await count(db_session, Company) == before
    twenty = await _company(client, auth, depts=[f"부서 {i}" for i in range(20)])
    assert len(twenty["depts"]) == 20
    for patch in ({"name": None}, {"depts": None}, {}, {"size": "big"}):
        problem_of(await client.patch(f"{URL}/{a}", headers=auth, json=patch), 422)
    got = problem_of(await client.get(f"{URL}/{OVERFLOW}", headers=auth), 422)
    assert locs(got) == [["path", "company_id"]]
    problem_of(
        await client.get(f"{URL}/{LARGEST}", headers=auth), 404, "/problems/not_found"
    )
    problem_of(
        await client.patch(f"{URL}/{LARGEST}", headers=auth, json={"memo": "x"}),
        404,
        "/problems/not_found",
    )
    problem_of(await client.get(URL, headers=x_auth), 403)
    problem_of(await client.get(f"{URL}/{a}", headers=x_auth), 403)


async def test_company_delete_409_with_course(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)

    # 활성 연결 강의 → 409, 보관하면 204 · 연결이 풀린다
    a = (await _company(client, auth))["id"]
    opened = _ok(
        await client.post(
            f"{ADMIN}/courses",
            headers=auth,
            json={**UNDATED_BODY, "start": "blank", "company_id": a},
        ),
        201,
    )
    kept = opened["course"]["id"]
    assert opened["course"]["company_id"] == a
    detail = _ok(await client.get(f"{URL}/{a}", headers=auth))
    assert detail["courses"] == [{"id": kept, "title": UNDATED_BODY["title"]}]
    problem_of(
        await client.delete(f"{URL}/{a}", headers=auth), 409, "/problems/conflict"
    )
    _ok(await client.get(f"{URL}/{a}", headers=auth))
    _ok(await client.post(f"{ADMIN}/courses/{kept}:archive", headers=auth))
    r = await client.delete(f"{URL}/{a}", headers=auth)
    assert r.status_code == 204, r.text
    assert (
        _ok(await client.get(f"{ADMIN}/courses/{kept}", headers=auth))["company_id"]
        is None
    )
    (deleted,) = await _audits(db_session, "company.delete", a)
    assert deleted == {"rounds": 0, "links": 0, "unlinked_courses": 1}

    # 활성 강의를 지운 회사는 지워지고 회차·링크도 같이 없어진다
    b = (await _company(client, auth, name="B사"))["id"]
    await _round(client, auth, b, ANSWERS_ALL_1)
    _ok(await client.post(f"{URL}/{b}/links", headers=auth, json={"phase": "pre"}), 201)
    gone = _ok(
        await client.post(
            f"{ADMIN}/courses",
            headers=auth,
            json={**UNDATED_BODY, "start": "blank", "company_id": b},
        ),
        201,
    )["course"]["id"]
    problem_of(
        await client.delete(f"{URL}/{b}", headers=auth), 409, "/problems/conflict"
    )
    assert (
        await client.delete(f"{ADMIN}/courses/{gone}", headers=auth)
    ).status_code == 204
    assert (await client.delete(f"{URL}/{b}", headers=auth)).status_code == 204
    assert await count(db_session, Diagnosis, Diagnosis.company_id == b) == 0
    assert await count(db_session, DiagLink, DiagLink.company_id == b) == 0
    (deleted,) = await _audits(db_session, "company.delete", b)
    assert deleted == {"rounds": 1, "links": 1, "unlinked_courses": 0}
    problem_of(await client.get(f"{URL}/{b}", headers=auth), 404)
    problem_of(await client.delete(f"{URL}/{b}", headers=auth), 404)

    # 개설 ③ 으로 연결된 활성 강의도 막는다
    c = (await _company(client, auth, name="C사"))["id"]
    rid = await _round(client, auth, c, ANSWERS_ALL_5, finalize=True)
    course = _ok(
        await client.post(
            f"{ADMIN}/courses",
            headers=auth,
            json={**UNDATED_BODY, "start": "diagnosis", "diagnosis_id": rid},
        ),
        201,
    )["course"]
    assert course["company_id"] == c
    problem_of(
        await client.delete(f"{URL}/{c}", headers=auth), 409, "/problems/conflict"
    )
    assert await count(db_session, Company, Company.id == c) == 1
    assert await count(db_session, Course, Course.company_id == c) == 1
