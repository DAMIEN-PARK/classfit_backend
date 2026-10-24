"""진단 링크: 발급·회수(관리자) · 공개 조회·제출(토큰이 주체) · 토큰 비노출(T9a 계획 결정 i·vi·x·xii·xiii·xxv · 증명 5~11).

전이(결정 iv): 발급 open · 회사당 open 하나(L1·L2) · 만료가 지난 open 은 발급이 먼저 회수(L3, reason expired) · 회수
open → revoked · revoked 그대로 · submitted 409(L4~L6) · 공개 GET 은 open ∧ 만료일 ≥ 오늘(L7 — 당일 유효) · 만료·회수·제출 410
이유 코드(L8) · 제출은 검토 대기 회차 + 링크 닫힘(L9) · 없는·모양 밖 토큰 404 같은 본문(L10). 공개 응답에 담당자·연락처·받는
분·이메일·토큰·점수·회차 번호가 없다. 토큰 네임스페이스(/v1/ax/<토큰> · /v1/admin/links/<토큰>)의 응답은 전부
Cache-Control: no-store 하나이고 로그·instance 는 {token} 이다. audit 에는 토큰 앞 8자만 남는다. 오늘은 TODAY(2026-11-03)다.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.app.errors import TokenRedactFilter
from classfit.core.config import Settings
from classfit.main import create_app
from classfit.models import AuditLog, DiagLink, Diagnosis
from tests.fixtures.assign import approved
from tests.fixtures.courses import admin_headers
from tests.fixtures.diagnosis import (
    ANSWERS_MIXED,
    AX_AREA_KEYS,
    AX_ITEM_KEYS,
    AX_KEYS,
    AX_OPTION_KEYS,
    COMPANY_BODY,
    FIELD_SAMPLE,
    LINK_KEYS,
    MATRIX_SAMPLE,
    PUBLIC_FORBIDDEN,
    RESPONDENT,
    RESPONDENT_EMAIL,
    SUBMITTED_KEYS,
    TODAY,
    set_today,
)
from tests.fixtures.enter import json_keys
from tests.fixtures.instructors import count, locs, problem_of

ADMIN = "/v1/admin"
AX = "/v1/ax"
LARGEST = 2**63 - 1
# 모양은 맞지만 발급한 적 없는 토큰(만든 글자)
NEVER = "never-issued-token-made-up-00000"


def _instant(value: str) -> datetime:
    """시각 글자의 순간(응답마다 시간대 표기가 달라도 같은 순간이면 같다)."""
    return datetime.fromisoformat(value)


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _company(client: httpx.AsyncClient, auth: dict[str, str], **over: Any) -> int:
    r = await client.post(
        f"{ADMIN}/companies", headers=auth, json={**COMPANY_BODY, **over}
    )
    return int(_ok(r, 201)["id"])


async def _issue(
    client: httpx.AsyncClient, auth: dict[str, str], company_id: int, **body: Any
) -> httpx.Response:
    return await client.post(
        f"{ADMIN}/companies/{company_id}/links",
        headers=auth,
        json={"phase": "pre", **body},
    )


async def _link(
    client: httpx.AsyncClient, auth: dict[str, str], company_id: int, **body: Any
) -> dict[str, Any]:
    return dict(_ok(await _issue(client, auth, company_id, **body), 201))


async def _revoke(
    client: httpx.AsyncClient, auth: dict[str, str], token: str
) -> httpx.Response:
    return await client.post(f"{ADMIN}/links/{token}:revoke", headers=auth)


async def _submit(client: httpx.AsyncClient, token: str, **over: Any) -> httpx.Response:
    body = {"answers": ANSWERS_MIXED, "respondent": RESPONDENT, **over}
    return await client.post(f"{AX}/{token}", json=body)


async def _links(
    client: httpx.AsyncClient, auth: dict[str, str], company_id: int
) -> dict[str, dict[str, Any]]:
    detail = _ok(await client.get(f"{ADMIN}/companies/{company_id}", headers=auth))
    return {x["token"]: x for x in detail["links"]}


async def _audits(session: AsyncSession, action: str) -> list[tuple[str, str, Any]]:
    rows = await session.execute(
        select(AuditLog.actor, AuditLog.target_id, AuditLog.detail)
        .where(AuditLog.action == action)
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows.all()]


async def _token_in_audit(session: AsyncSession, token: str) -> int:
    text = func.concat(
        AuditLog.actor, " ", AuditLog.target_id, " ", cast(AuditLog.detail, Text)
    )
    return await count(session, AuditLog, text.contains(token))


async def test_diag_link_issue_one_open_per_company(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)

    first = await _link(client, auth, co)
    assert set(first) == LINK_KEYS
    token = first["token"]
    assert len(token) == 32 and set(token) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    )
    assert (first["issued_on"], first["expires_on"]) == (
        TODAY.isoformat(),
        (TODAY + timedelta(days=14)).isoformat(),
    )
    assert (first["recipient"], first["state"], first["phase"]) == (
        "담당자 가",
        "open",
        "pre",
    )
    assert (first["submitted_at"], first["revoked_at"], first["diagnosis_id"]) == (
        None,
        None,
        None,
    )
    problem_of(await _issue(client, auth, co), 409, "/problems/conflict")
    _ok(await _revoke(client, auth, token))
    second = await _link(client, auth, co, phase="post", recipient="받는 분 나")
    assert (second["phase"], second["recipient"]) == ("post", "받는 분 나")

    # 만료가 지난 open 은 발급이 먼저 회수한다(reason expired)
    later = date.fromisoformat(second["expires_on"]) + timedelta(days=1)
    set_today(app, later)
    assert (await _links(client, auth, co))[second["token"]]["state"] == "expired"
    third = await _link(client, auth, co)
    links = await _links(client, auth, co)
    assert links[second["token"]]["state"] == "revoked"
    assert links[second["token"]]["revoked_at"] is not None
    assert (links[third["token"]]["state"], third["issued_on"]) == (
        "open",
        later.isoformat(),
    )
    revokes = await _audits(db_session, "diag_link.revoke")
    assert [(t, d.get("reason")) for _, t, d in revokes] == [
        (str(first["id"]), None),
        (str(second["id"]), "expired"),
    ]
    other = await _company(client, auth, name="B사")
    await _link(client, auth, other)  # 회사마다 따로

    # 만료일 범위: 오늘 ~ 오늘 + 365
    set_today(app, TODAY)
    edge = await _company(client, auth, name="C사")
    for bad in (TODAY - timedelta(days=1), TODAY + timedelta(days=366)):
        got = problem_of(
            await _issue(client, auth, edge, expires_on=bad.isoformat()), 422
        )
        assert locs(got) == [["body", "expires_on"]]
    assert await count(db_session, DiagLink, DiagLink.company_id == edge) == 0
    same_day = await _link(client, auth, edge, expires_on=TODAY.isoformat())
    assert same_day["expires_on"] == TODAY.isoformat()
    for bad_body in (
        {"phase": "mid"},
        {"phase": "pre", "extra": 1},
        {"phase": "pre", "recipient": ""},
    ):
        problem_of(
            await client.post(
                f"{ADMIN}/companies/{edge}/links", headers=auth, json=bad_body
            ),
            422,
        )
    problem_of(await _issue(client, auth, LARGEST), 404, "/problems/not_found")

    issued = await _audits(db_session, "diag_link.issue")
    tokens = [first["token"], second["token"], third["token"]]
    assert [d["token_prefix"] for _, _, d in issued[:3]] == [t[:8] for t in tokens]
    assert issued[0][2]["expires_on"] == first["expires_on"]
    for t in [*tokens, same_day["token"]]:
        assert await _token_in_audit(db_session, t) == 0


async def test_diag_link_revoke_rules(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    _, x_auth = await approved(db_session, app.state.settings, email="x@example.com")
    co = await _company(client, auth)

    link = await _link(client, auth, co)
    got = _ok(await _revoke(client, auth, link["token"]))
    assert set(got) == LINK_KEYS
    assert (got["state"], got["id"]) == ("revoked", link["id"])
    again = _ok(await _revoke(client, auth, link["token"]))
    assert _instant(again["revoked_at"]) == _instant(
        got["revoked_at"]
    )  # 멱등 — audit 도 늘지 않는다
    assert len(await _audits(db_session, "diag_link.revoke")) == 1

    stale = await _link(client, auth, co)
    set_today(app, date.fromisoformat(stale["expires_on"]) + timedelta(days=1))
    assert _ok(await _revoke(client, auth, stale["token"]))["state"] == "revoked"
    set_today(app, TODAY)

    done = await _link(client, auth, co)
    _ok(await _submit(client, done["token"]), 201)
    problem_of(await _revoke(client, auth, done["token"]), 409, "/problems/conflict")
    assert (await _links(client, auth, co))[done["token"]]["state"] == "submitted"
    assert len(await _audits(db_session, "diag_link.revoke")) == 2

    missing = problem_of(await _revoke(client, auth, NEVER), 404, "/problems/not_found")
    for shape in ("abc", "a" * 64, "a" * 31):
        assert problem_of(await _revoke(client, auth, shape), 404) == missing
    problem_of(await _revoke(client, x_auth, link["token"]), 403)


async def test_diag_link_public_get_states(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth, phone="02-000-0000", memo="메모")
    link = await _link(client, auth, co, recipient="받는 분 가")
    url = f"{AX}/{link['token']}"
    audited = await count(db_session, AuditLog)

    body = _ok(await client.get(url))
    assert set(body) == AX_KEYS
    assert (body["company_name"], body["phase"], body["expires_on"]) == (
        "A사",
        "pre",
        link["expires_on"],
    )
    assert [a["no"] for a in body["areas"]] == ["01", "02", "03", "04"]
    assert all(set(a) == AX_AREA_KEYS for a in body["areas"])
    items = [i for a in body["areas"] for i in a["items"]]
    assert len(items) == 17
    assert all(set(i) == AX_ITEM_KEYS and len(i["levels"]) == 5 for i in items)
    assert set(body["options"]) == AX_OPTION_KEYS
    assert json_keys(body) & PUBLIC_FORBIDDEN == set()
    for word in ("담당자 가", "받는 분 가", "02-000-0000", "메모", link["token"]):
        assert word not in str(body)
    assert _ok(await client.get(url, headers=auth)) == body  # Bearer 는 보지 않는다

    set_today(app, date.fromisoformat(link["expires_on"]))  # 만료일 당일은 유효
    assert _ok(await client.get(url)) == body
    set_today(app, date.fromisoformat(link["expires_on"]) + timedelta(days=1))
    expired = problem_of(await client.get(url), 410, "/problems/diag-link-expired")
    set_today(app, TODAY)
    assert await count(db_session, AuditLog) == audited  # 공개 GET 은 audit 하지 않는다

    revoked_co = await _company(client, auth, name="B사")
    revoked = await _link(client, auth, revoked_co)
    _ok(await _revoke(client, auth, revoked["token"]))
    gone = problem_of(
        await client.get(f"{AX}/{revoked['token']}"), 410, "/problems/diag-link-revoked"
    )
    submitted_co = await _company(client, auth, name="C사")
    submitted = await _link(client, auth, submitted_co)
    _ok(await _submit(client, submitted["token"]), 201)
    used = problem_of(
        await client.get(f"{AX}/{submitted['token']}"),
        410,
        "/problems/diag-link-submitted",
    )
    for refused in (expired, gone, used):
        assert set(refused) == {"type", "title", "status", "detail", "instance"}
        assert json_keys(refused) & PUBLIC_FORBIDDEN == set()
        assert not any(
            w in str(refused) for w in ("A사", "B사", "C사", "담당자 가", "받는 분 가")
        )

    missing = problem_of(await client.get(f"{AX}/{NEVER}"), 404, "/problems/not_found")
    for shape in ("abc", "a" * 64, "a" * 31, "%00" * 3):
        assert problem_of(await client.get(f"{AX}/{shape}"), 404) == missing
    assert problem_of(await client.get(f"{AX}/{NEVER}", headers=auth), 404) == missing


async def test_diag_link_submit_creates_review_round(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)
    link = await _link(client, auth, co)
    token = link["token"]

    r = await _submit(client, token, field=FIELD_SAMPLE, matrix=MATRIX_SAMPLE)
    got = _ok(r, 201)
    assert set(got) == SUBMITTED_KEYS
    assert got["phase"] == "pre"
    detail = _ok(await client.get(f"{ADMIN}/companies/{co}", headers=auth))
    (row,) = detail["rounds"]
    assert (row["round_no"], row["status"], row["mode"], row["phase"]) == (
        1,
        "review",
        "link",
        "pre",
    )
    (closed,) = detail["links"]
    assert (closed["state"], closed["diagnosis_id"]) == ("submitted", row["id"])
    assert _instant(closed["submitted_at"]) == _instant(got["submitted_at"])
    one = _ok(await client.get(f"{ADMIN}/diagnoses/{row['id']}", headers=auth))
    assert one["respondent"] == {**RESPONDENT, "email": RESPONDENT_EMAIL}
    assert (one["answers"], one["evidence"], one["matrix"]) == (
        ANSWERS_MIXED,
        {},
        MATRIX_SAMPLE,
    )
    assert {k: one["field"][k] for k in FIELD_SAMPLE} == FIELD_SAMPLE
    assert (one["diagnosed_on"], one["created_by"], one["reco"]) == (
        TODAY.isoformat(),
        "link",
        None,
    )

    problem_of(await _submit(client, token), 410, "/problems/diag-link-submitted")
    problem_of(await client.get(f"{AX}/{token}"), 410, "/problems/diag-link-submitted")
    assert await count(db_session, Diagnosis, Diagnosis.company_id == co) == 1

    stale_co = await _company(client, auth, name="B사")
    stale = await _link(client, auth, stale_co)
    set_today(app, date.fromisoformat(stale["expires_on"]) + timedelta(days=1))
    problem_of(
        await _submit(client, stale["token"]), 410, "/problems/diag-link-expired"
    )
    set_today(app, TODAY)
    revoked_co = await _company(client, auth, name="C사")
    revoked = await _link(client, auth, revoked_co)
    _ok(await _revoke(client, auth, revoked["token"]))
    problem_of(
        await _submit(client, revoked["token"]), 410, "/problems/diag-link-revoked"
    )
    problem_of(await _submit(client, NEVER), 404, "/problems/not_found")
    assert (
        await count(
            db_session, Diagnosis, Diagnosis.company_id.in_([stale_co, revoked_co])
        )
        == 0
    )

    ((actor, target, audit),) = await _audits(db_session, "diag_link.submit")
    assert (actor, target) == (f"link:{token[:8]}", str(link["id"]))
    assert audit["token_prefix"] == token[:8]
    assert (audit["company_id"], audit["diagnosis_id"], audit["round_no"]) == (
        co,
        row["id"],
        1,
    )
    for word in (
        RESPONDENT["name"],
        RESPONDENT["email"],
        RESPONDENT_EMAIL,
        RESPONDENT["title"],
    ):
        assert word not in str(audit)
    assert await _token_in_audit(db_session, token) == 0

    # 관리자가 증빙을 채우고 확정한다(자가 응답 검토)
    _ok(
        await client.patch(
            f"{ADMIN}/diagnoses/{row['id']}",
            headers=auth,
            json={"evidence": {"0-0": [True, False]}},
        )
    )
    final = _ok(
        await client.post(f"{ADMIN}/diagnoses/{row['id']}:finalize", headers=auth)
    )
    assert (final["status"], final["evidence"]) == ("final", {"0-0": [True, False]})


async def test_diag_link_submit_validation_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)
    token = (await _link(client, auth, co))["token"]
    sixteen = {k: v for k, v in ANSWERS_MIXED.items() if k != "3-3"}

    async def rejected(body: dict[str, Any]) -> dict[str, Any]:
        got = problem_of(await client.post(f"{AX}/{token}", json=body), 422)
        assert got["violations"], got
        return got

    base = {"answers": ANSWERS_MIXED, "respondent": RESPONDENT}
    got = await rejected({**base, "answers": sixteen})
    assert locs(got) == [["body", "answers"]]
    assert "3-3" in got["violations"][0]["msg"]
    for body in (
        {**base, "answers": {**ANSWERS_MIXED, "0-0": 6}},
        {**base, "answers": {**ANSWERS_MIXED, "4-0": 3}},
        {"answers": ANSWERS_MIXED},
        {**base, "respondent": {"name": "   "}},
        {**base, "respondent": {**RESPONDENT, "email": "not-mail"}},
        {**base, "respondent": {**RESPONDENT, "email": "a\x01@example.com"}},
        {**base, "evidence": {"0-0": [True, True]}},
        {**base, "extra": 1},
        {**base, "field": {"work": "가" * 201}},
        {**base, "matrix": {"9-9": 3}},
    ):
        await rejected(body)
    # 입력 키가 토큰이어도 422 위치·안내로 되돌아가지 않는다(토큰 네임스페이스는 violations 를 가린다)
    for body, where in (
        ({**base, token: 1}, ["body", "{token}"]),
        (
            {**base, "answers": {**ANSWERS_MIXED, token: 3}},
            ["body", "answers", "{token}", "[key]"],
        ),
    ):
        r = await client.post(f"{AX}/{token}", json=body)
        assert locs(problem_of(r, 422)) == [where]
        assert token not in r.text
    assert await count(db_session, Diagnosis) == 0
    assert (await _links(client, auth, co))[token]["state"] == "open"
    assert await count(db_session, AuditLog, AuditLog.action == "diag_link.submit") == 0

    _ok(await _submit(client, token), 201)
    await rejected({**base, "answers": sixteen})  # 제출된 링크에도 본문 422 가 먼저
    assert await count(db_session, Diagnosis) == 1


async def test_diag_link_public_token_not_logged(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    caplog: Any,
) -> None:
    caplog.set_level(logging.INFO)
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)
    token = (await _link(client, auth, co))["token"]
    t, n = token, NEVER
    assert len(n) == 32

    def check(r: httpx.Response, status: int, instance: str | None) -> None:
        assert r.status_code == status, (r.request.url, r.text)
        assert r.headers.get_list("cache-control") == ["no-store"], r.headers
        assert t not in r.text and n not in r.text and "short" not in r.text
        if instance is not None:
            assert r.json()["instance"] == instance

    check(await client.get(f"{AX}/{t}"), 200, None)
    check(await client.get(f"{AX}/{n}"), 404, "/v1/ax/{token}")
    check(await client.get(f"{AX}/{t}/extra"), 404, "/v1/ax/{token}/extra")
    check(await client.get(f"{AX}/{t})/extra"), 404, "/v1/ax/{token}/extra")
    check(await client.get(f"/api{AX}/{t}/extra"), 404, "/api/v1/ax/{token}/extra")
    check(
        await client.get(f"{AX}/{t}/"), 307, None
    )  # Location 은 요청한 쪽에 돌려주는 같은 주소라 단언 밖
    check(await client.get(f"{AX}/short"), 404, "/v1/ax/{token}")
    check(await _submit(client, t), 201, None)
    check(await client.get(f"{AX}/{t}"), 410, "/v1/ax/{token}")
    check(await client.post(f"{AX}/{t}", json={"answers": {}}), 422, "/v1/ax/{token}")
    check(await client.put(f"{AX}/{t}", json={}), 405, "/v1/ax/{token}")
    check(await _revoke(client, auth, n), 404, "/v1/admin/links/{token}:revoke")
    # 기형 토큰 경로 — 네임스페이스 판정은 접두만 본다(겹 슬래시 · %2F · 빈 세그먼트), 나머지 경로의 토큰도 가린다
    check(await client.get(f"{AX}//{t}"), 404, "/v1/ax/{token}")
    check(await client.get(f"{AX}/%2F{t}"), 404, "/v1/ax/{token}")
    check(await client.get(f"/v1//ax/{t}"), 404, "/v1/ax/{token}")
    check(await client.get(f"{AX}/x/{t}"), 404, "/v1/ax/{token}/{token}")
    check(await client.get(f"{AX}/x:{t}"), 404, "/v1/ax/{token}:{token}")
    check(await client.get(f"{AX}/{t}/v1/ax/{n}"), 404, "/v1/ax/{token}/v1/ax/{token}")
    check(
        await client.post(f"{ADMIN}/links//{n}:revoke", headers=auth),
        404,
        "/v1/admin/links/{token}:revoke",
    )
    check(
        await client.post(f"{ADMIN}/links/:revoke", headers=auth),
        404,
        "/v1/admin/links/{token}:revoke",
    )

    # 토큰 네임스페이스 밖은 지금과 같다 — 실제 경로 · 캐시 헤더 없음
    plain = await client.get(f"{ADMIN}/companies/{LARGEST}", headers=auth)
    assert plain.json()["instance"] == f"{ADMIN}/companies/{LARGEST}"
    assert "cache-control" not in plain.headers
    nope = await client.get("/v1/nope")
    assert (nope.json()["instance"], "cache-control" in nope.headers) == (
        "/v1/nope",
        False,
    )

    # httpx 가 요청 URL 을 INFO 로 찍으므로 classfit 로거 기록만 본다
    lines = [r.getMessage() for r in caplog.records if r.name.startswith("classfit")]
    joined = "\n".join(lines)
    assert t not in joined and n not in joined and "short" not in joined
    for template in (
        "GET /v1/ax/{token} -> 200",
        "GET /v1/ax/{token}/extra -> 404",
        "GET /api/v1/ax/{token}/extra -> 404",
        "GET /v1/ax/{token}/ -> 307",
        "PUT /v1/ax/{token} -> 405",
        "POST /v1/admin/links/{token}:revoke -> 404",
        "GET /v1/ax/{token}/{token} -> 404",
        f"GET {ADMIN}/companies/{LARGEST} -> 404",
    ):
        assert template in joined, template


async def test_diag_link_public_500_redacted(
    app: FastAPI,
    client_noraise: httpx.AsyncClient,
    db_session: AsyncSession,
    caplog: Any,
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client_noraise, auth)
    token = (await _link(client_noraise, auth, co))["token"]

    def boom() -> date:
        # DB 예외 DETAIL·SQLAlchemy parameters 꼴로 토큰을 싣는다
        raise RuntimeError(
            f"dup key (token)=({token}) [parameters: {{'token': '{token}'}}]"
        )

    app.dependency_overrides[today] = boom
    caplog.set_level(logging.INFO)
    r = await client_noraise.get(f"{AX}/{token}")
    assert r.status_code == 500, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.headers.get_list("cache-control") == ["no-store"]
    assert r.json()["instance"] == "/v1/ax/{token}"
    assert token not in r.text

    records = [x for x in caplog.records if x.name.startswith("classfit")]
    fmt = logging.Formatter("%(levelname)s %(name)s %(message)s")
    written = "\n".join(
        part
        for x in records
        for part in (x.getMessage(), x.exc_text or "", fmt.format(x))
    )
    assert token not in written
    assert "{token}" in written and "RuntimeError" in written  # 지우지 않고 가렸다
    (crash,) = [x for x in records if x.name == "classfit.errors"]
    assert crash.exc_info is None and crash.exc_text and "{token}" in crash.exc_text

    # 필터 경계: 32자 값만 가린다 · 치환이 없으면 args 를 그대로 둔다(uvicorn 시작 줄)
    f = TokenRedactFilter()
    for n in (31, 33):
        rec = logging.LogRecord(
            "t", logging.INFO, __file__, 1, "v=%s", ("a" * n,), None
        )
        assert f.filter(rec) and rec.getMessage() == "v=" + "a" * n
    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "Started server process [%d]", (7,), None
    )
    assert (
        f.filter(rec)
        and rec.args == (7,)
        and rec.getMessage() == "Started server process [7]"
    )
    rec = logging.LogRecord(
        "t",
        logging.ERROR,
        __file__,
        1,
        "Failing row contains (1, %s, open)",
        (token,),
        None,
    )
    assert (
        f.filter(rec) and rec.getMessage() == "Failing row contains (1, {token}, open)"
    )
    # 형식 오류 레코드는 막지 않고 그대로 넘긴다(logging 의 handleError 몫)
    rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "bad %d", ("x",), None)
    assert f.filter(rec) and (rec.msg, rec.args) == ("bad %d", ("x",))

    def installed() -> int:
        return sum(
            isinstance(x, TokenRedactFilter)
            for x in logging.getLogger("uvicorn.error").filters
        )

    assert installed() == 1
    create_app(Settings())
    assert installed() == 1
