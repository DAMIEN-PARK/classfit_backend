"""토큰 전체가 실리는 응답의 Cache-Control: no-store(T11 결정 ii).

여섯 연산: 관리자·강사 로그인(TokenOut) · 입장(EnterOut) · 회사 상세 GET·PATCH(CompanyDetailOut.links) · 진단 링크 발급
(LinkOut). app.deps.no_store 는 데코레이터 의존성이라 핸들러가 모델을 돌려줄 때만 헤더가 합쳐진다 — problem 응답
(없는 회사 404 · 로그인 실패 401)에는 없다. 토큰 경로 네임스페이스(/v1/ax · /v1/admin/links)는 미들웨어가 따로 단다.
"""

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.passwords import hash_password
from classfit.crud.admin import insert_admin
from tests.fixtures.courses import open_test_course
from tests.fixtures.diagnosis import COMPANY_BODY, TODAY, set_today
from tests.fixtures.enter import bearer, enter_learner
from tests.fixtures.instructors import PASSWORD, make_instructor, problem_of

ADMIN = "/v1/admin"
LARGEST = 2**63 - 1


def _no_store(r: httpx.Response, status: int) -> dict:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    assert r.headers.get_list("cache-control") == ["no-store"], r.headers
    return r.json()


async def test_no_store_token_responses(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    await insert_admin(
        db_session, login_id="admin-a", password_hash=hash_password("pw-a-123")
    )
    login = {"login_id": "admin-a", "password": "pw-a-123"}
    body = _no_store(await client.post("/v1/auth/admin/login", json=login), 200)
    auth = bearer(body["access_token"])
    # 로그인 실패는 problem 이라 없다
    wrong = await client.post(
        "/v1/auth/admin/login", json={**login, "password": "pw-a-wrong"}
    )
    problem_of(wrong, 401)
    assert "cache-control" not in wrong.headers

    await make_instructor(db_session, app.state.settings, email="kim@example.com")
    r = await client.post(
        "/v1/auth/instructor/login",
        json={"email": "kim@example.com", "password": PASSWORD},
    )
    _no_store(r, 200)

    _, code = await open_test_course(db_session)
    _no_store(await enter_learner(client, code.code, "lee@example.com", "이수강"), 201)
    _no_store(await enter_learner(client, code.code, "lee@example.com"), 200)  # 재입장

    r = await client.post(f"{ADMIN}/companies", headers=auth, json=COMPANY_BODY)
    assert r.status_code == 201, r.text
    co = r.json()["id"]
    link = _no_store(
        await client.post(
            f"{ADMIN}/companies/{co}/links", headers=auth, json={"phase": "pre"}
        ),
        201,
    )
    detail = _no_store(await client.get(f"{ADMIN}/companies/{co}", headers=auth), 200)
    assert [x["token"] for x in detail["links"]] == [link["token"]]
    r = await client.patch(
        f"{ADMIN}/companies/{co}", headers=auth, json={"contact": "담당자 나"}
    )
    _no_store(r, 200)

    missing = await client.get(f"{ADMIN}/companies/{LARGEST}", headers=auth)
    problem_of(missing, 404)
    assert "cache-control" not in missing.headers
