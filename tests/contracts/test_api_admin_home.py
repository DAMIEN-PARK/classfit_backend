"""관리자 홈 GET /v1/admin/home(AdminCaller, T9b 계획 결정 xiii·xiv·xv·xvii·xxvii · 증명 9~11·32).

셈 여덟은 이동한 상세 목록과 같은 조건이다(요구정의서 COM-004). 이 파일은 끝점 모양 · 권한 · 픽스처 기대값 · 이력 순서와 진단
검토 대기 셈 == 회차 목록을 끝까지 넘긴 수를 잰다(셈 == crud 목록 문장 · 주체별 자기 범위는 통합 test_db_home_admin.py).
홈 픽스처(tests/fixtures/inquiry.py home_fixtures)의 오늘은 HOME_TODAY(2026-11-03)이고, + LATER_DAYS 면 진행 강의가 끝난다.
"""

import datetime as dt
import itertools
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import Diagnosis
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.diagnosis import ANSWERS_9, insert_round, make_company
from tests.fixtures.enter import json_keys
from tests.fixtures.inquiry import (
    AUDIT_ITEM_KEYS,
    COUNT_KEYS,
    HOME_KEYS,
    HOME_TODAY,
    LATER_DAYS,
    ZERO_COUNTS,
    home_fixtures,
    seed_audit,
)
from tests.fixtures.instructors import instructor_headers, problem_of
from tests.fixtures.records import set_today

HOME = "/v1/admin/home"
DIAGNOSES = "/v1/admin/diagnoses"


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _all_ids(
    client: httpx.AsyncClient, headers: dict[str, str], status: str
) -> list[int]:
    """GET /v1/admin/diagnoses?status=…&limit=1 을 next_cursor 로 끝까지 넘긴 항목 id."""
    ids: list[int] = []
    params: dict[str, Any] = {"status": status, "limit": 1}
    while True:
        page = _ok(await client.get(DIAGNOSES, headers=headers, params=params))
        ids += [item["id"] for item in page["items"]]
        if not page["has_more"]:
            assert page["next_cursor"] is None
            return ids
        params = {**params, "cursor": page["next_cursor"]}


async def test_admin_home_keys_and_zero_counts(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    _, admin = await admin_headers(db)
    body = _ok(await client.get(HOME, headers=admin))
    assert set(body) == HOME_KEYS
    assert set(body["counts"]) == set(COUNT_KEYS)
    assert body["counts"] == ZERO_COUNTS  # 빈 DB
    assert body["recent_audit"] == []

    # 관리자만 — 강사·수강생 403 · 토큰 없음 401
    teacher = await instructor_headers(db, 1)
    problem_of(await client.get(HOME, headers=teacher), 403)
    course, _ = await open_test_course(db)
    learner = await learner_headers(db, course.id)
    problem_of(await client.get(HOME, headers=learner), 403)
    anonymous = await client.get(HOME)
    problem_of(anonymous, 401)
    assert anonymous.headers["www-authenticate"] == "Bearer"


async def test_admin_home_counts_match_fixtures(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    expected = await home_fixtures(db, Settings(), today=HOME_TODAY)
    set_today(app, HOME_TODAY)
    _, admin = await admin_headers(db)
    body = _ok(await client.get(HOME, headers=admin))
    counts = body["counts"]
    assert counts == expected.admin
    # T8 열린 설문 · T9a 진단 검토 대기는 1건씩(자리표시 0 이 아니다 — 결정 xvii) · X 범위 밖 진행 강의 B 포함
    assert (counts["open_surveys"], counts["diagnoses_in_review"]) == (1, 1)
    assert (counts["running_courses"], counts["new_photos"]) == (2, 2)

    audit = body["recent_audit"]
    assert [
        item["id"] for item in audit
    ] == expected.audit_ids  # 10건 · (at, id) 내림차순
    assert all(set(item) == AUDIT_ITEM_KEYS for item in audit)
    keys = json_keys(body)
    assert "detail" not in keys  # 반려 사유 · 강의 제목 같은 자유 글은 싣지 않는다
    assert not keys & {"email", "phone", "name"}

    # 오늘을 뒤로 밀면 진행 강의 A·B 가 끝나 진행·미기록이 0 이고, 미배정은 준비 강의 몫만 남는다(결정 xv)
    set_today(app, HOME_TODAY + dt.timedelta(days=LATER_DAYS))
    later = _ok(await client.get(HOME, headers=admin))["counts"]
    assert later == expected.admin_later
    assert (later["running_courses"], later["records_missing"]) == (0, 0)
    assert later["unassigned_sessions"] == 1


async def test_admin_home_recent_audit_limit_and_order(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    _, admin = await admin_headers(db)
    # at 을 명시한 12행 — 서로 다른 시각 10 + 가장 늦은 같은 시각 둘(트랜잭션 안 now() 가 고정이라 기본값으로는 순서가 안 갈린다)
    expected = await seed_audit(db)
    audit = _ok(await client.get(HOME, headers=admin))["recent_audit"]
    assert [item["id"] for item in audit] == expected  # 10건 — 11번째 없음
    assert all(set(item) == AUDIT_ITEM_KEYS for item in audit)
    at = [dt.datetime.fromisoformat(item["at"]) for item in audit]
    assert at[0] == at[1] and audit[0]["id"] > audit[1]["id"]  # 같은 at 은 id 내림차순
    assert all(a > b for a, b in itertools.pairwise(at[1:]))  # 그 뒤는 at 내림차순
    first = audit[0]
    assert (first["actor"], first["action"], first["target_type"]) == (
        "admin:1",
        "home.seed",
        "course",
    )


async def test_admin_home_review_count_matches_diagnosis_list(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db = db_session
    expected = await home_fixtures(db, Settings(), today=HOME_TODAY)
    other = await make_company(db, name="B사")
    for no in (1, 2):
        await insert_round(
            db, other.id, round_no=no, status="review", answers=ANSWERS_9
        )
    set_today(app, HOME_TODAY)
    _, admin = await admin_headers(db)

    counts = _ok(await client.get(HOME, headers=admin))["counts"]
    assert (
        counts["diagnoses_in_review"] == expected.admin["diagnoses_in_review"] + 2 == 3
    )
    review = await _all_ids(client, admin, "review")
    assert len(review) == len(set(review)) == counts["diagnoses_in_review"]  # COM-004
    statuses = select(Diagnosis.status).where(Diagnosis.id.in_(review))
    assert set((await db.scalars(statuses)).all()) == {"review"}
    # 픽스처의 음성 draft·final 은 어느 쪽에도 없다
    others = await _all_ids(client, admin, "draft") + await _all_ids(
        client, admin, "final"
    )
    assert len(others) == 2
    assert not set(others) & set(review)
