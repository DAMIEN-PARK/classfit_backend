"""진단 회차 목록 GET /v1/admin/diagnoses?status=…(관리자만, T9b 계획 결정 xxvii · 증명 29~31).

status 는 필수(draft·review·final)이고 첫 WHERE 는 company_scope 다. 새로 받은 것부터((created_at, id) 내림차순 — 한 시험의
행은 같은 트랜잭션 시각이라 id 내림차순) 키셋 쪽이다. 항목은 회사 이름 · 응답자 이름 · 링크 제출 시각 · 총점·레벨까지이고
응답자 직함·이메일, 답·증빙은 싣지 않는다. 링크 회차는 운영 경로(make_link → submit_via_service, 17지표 ANSWERS_MIXED →
450 · L3)로, 방문 회차는 insert_round 로 만든다(9지표 ANSWERS_9 → 220 · level null).
"""

import datetime as dt
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import DiagLink
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.diagnosis import (
    ANSWERS_9,
    ANSWERS_ALL_5,
    RESPONDENT,
    TODAY,
    insert_round,
    make_company,
    make_link,
    submit_via_service,
)
from tests.fixtures.enter import json_keys
from tests.fixtures.inquiry import DIAG_LIST_ITEM_KEYS
from tests.fixtures.instructors import instructor_headers, problem_of

URL = "/v1/admin/diagnoses"
PAGE_KEYS = {"items", "next_cursor", "has_more"}


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _ids(
    client: httpx.AsyncClient, headers: dict[str, str], status: str
) -> list[int]:
    page = _ok(await client.get(URL, headers=headers, params={"status": status}))
    return [item["id"] for item in page["items"]]


async def test_diagnosis_list_review_keys_and_order(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    _, admin = await admin_headers(db)
    a = await make_company(db)  # A사
    link = await make_link(db, a.id)
    a_review = await submit_via_service(
        db, link.token
    )  # 링크 제출 = review · 응답자 · 17지표
    a_draft = await insert_round(
        db, a.id, round_no=a_review.round_no + 1, answers=ANSWERS_9
    )
    b = await make_company(db, name="B사")
    b_review = await insert_round(
        db, b.id, round_no=1, status="review", answers=ANSWERS_9
    )
    b_final = await insert_round(
        db, b.id, round_no=2, status="final", answers=ANSWERS_ALL_5
    )

    body = _ok(await client.get(URL, headers=admin, params={"status": "review"}))
    assert set(body) == PAGE_KEYS
    assert (body["next_cursor"], body["has_more"]) == (None, False)
    items = body["items"]
    assert [item["id"] for item in items] == [
        b_review.id,
        a_review.id,
    ]  # 새로 받은 것부터
    assert all(set(item) == DIAG_LIST_ITEM_KEYS for item in items)
    visit, linked = items
    submitted_at = await db.scalar(
        select(DiagLink.submitted_at).where(DiagLink.id == link.id)
    )
    assert submitted_at is not None
    assert {k: v for k, v in linked.items() if k != "submitted_at"} == {
        "id": a_review.id,
        "company_id": a.id,
        "company_name": "A사",
        "round_no": a_review.round_no,
        "phase": "pre",
        "mode": "link",
        "status": "review",
        "diagnosed_on": TODAY.isoformat(),  # 링크 회차는 제출일
        "respondent_name": RESPONDENT["name"],
        "total": 450,  # golden dg-mixed-450-l3
        "level": 3,
    }
    assert dt.datetime.fromisoformat(linked["submitted_at"]) == submitted_at
    assert visit == {
        "id": b_review.id,
        "company_id": b.id,
        "company_name": "B사",
        "round_no": 1,
        "phase": "pre",
        "mode": "visit",
        "status": "review",
        "diagnosed_on": TODAY.isoformat(),
        "respondent_name": None,  # 방문 회차는 응답자 · 제출 시각이 없다
        "submitted_at": None,
        "total": 220,  # golden dg-partial-9
        "level": None,  # 17지표 전
    }
    # 응답자 직함·이메일 · 회사 연락처 · 답·증빙은 싣지 않는다
    assert not json_keys(body) & {"email", "phone", "answers", "evidence", "respondent"}

    # 상태 필터 — 그 상태의 회차만
    assert await _ids(client, admin, "draft") == [a_draft.id]
    assert await _ids(client, admin, "final") == [b_final.id]

    # limit=1 쪽을 넘긴 합집합 == 전부
    first = _ok(
        await client.get(URL, headers=admin, params={"status": "review", "limit": 1})
    )
    assert [item["id"] for item in first["items"]] == [b_review.id]
    assert first["has_more"] is True
    second = _ok(
        await client.get(
            URL,
            headers=admin,
            params={"status": "review", "limit": 1, "cursor": first["next_cursor"]},
        )
    )
    assert [item["id"] for item in second["items"]] == [a_review.id]
    assert (second["next_cursor"], second["has_more"]) == (None, False)


async def test_diagnosis_list_status_required_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    cases: list[tuple[dict[str, Any], str, str]] = [
        ({}, "status", "missing"),
        ({"status": "submitted"}, "status", "literal_error"),  # 시안 글자는 review 다
        ({"status": "review", "limit": 0}, "limit", "greater_than_equal"),
        ({"status": "review", "limit": 101}, "limit", "less_than_equal"),
        ({"status": "review", "cursor": "!!!"}, "cursor", "value_error"),
        # base64url("{}") — 칸이 없는 커서
        ({"status": "review", "cursor": "e30"}, "cursor", "value_error"),
    ]
    for params, key, type_ in cases:
        body = problem_of(await client.get(URL, headers=admin, params=params), 422)
        assert [(v["loc"], v["type"]) for v in body["violations"]] == [
            (["query", key], type_)
        ], params


async def test_diagnosis_list_admin_only(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    teacher = await instructor_headers(db, 1)
    course, _ = await open_test_course(db)
    learner = await learner_headers(db, course.id)
    # 권한 의존성이 질의 검증보다 먼저 — status 가 없어도 403 · 401
    for params in ({"status": "review"}, {}):
        problem_of(await client.get(URL, headers=teacher, params=params), 403)
        problem_of(await client.get(URL, headers=learner, params=params), 403)
        anonymous = await client.get(URL, params=params)
        problem_of(anonymous, 401)
        assert anonymous.headers["www-authenticate"] == "Bearer"
