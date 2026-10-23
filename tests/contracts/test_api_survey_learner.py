"""수강생 설문 조회·1회 제출 · 본문 상한 · 포털 배너 · 명단 응답 여부 · 강사 홈 알림 · 강사 I7 결과
(T8 계획 결정 i·ix·xii·xiv·xv·xvi·xxv · 증명 1·2·11~14·31).

수강생은 토큰의 강의만, 강사는 배정된 강의만 본다. 제출은 수강생이 본 설문판(survey_id · questions_hash)에 묶이고 등록
1건당 1회다. 포털 survey 칸은 강의 단위라 수강생·관리자·강사 미리 보기가 같다. 명단은 응답 여부만, 결과는 집계만 싣고
둘을 잇는 칸(응답 id · 제출 시각)이 없다. 강사 결과는 마감 뒤 + 최소 응답 수(survey_min_responses, 기본 5) 이상일 때만
보인다. 픽스처 강의는 2026-11-02(월)부터 평일 4일이고 오늘은 2026-11-03 이 기본이다.
"""

from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import AuditLog, SurveyResponse
from classfit.schemas.survey import SubmitIn
from tests.fixtures.assign import approved
from tests.fixtures.courses import admin_headers, open_test_course
from tests.fixtures.enter import (
    PERSONAL_KEYS,
    add_session,
    bearer,
    enter_learner,
    json_keys,
)
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.my_attachments import ROSTER_KEYS
from tests.fixtures.records import set_today
from tests.fixtures.surveys import (
    ANSWERS_OK,
    HEAD_KEYS,
    HOME_SURVEY_KEYS,
    LEARNER_SURVEY_BODY_KEYS,
    LEARNER_SURVEY_KEYS,
    MY_RESULTS_KEYS,
    MY_RESULTS_TOP_KEYS,
    PORTAL_SURVEY_KEYS,
    QUESTION_KEYS,
    RESULT_FORBIDDEN_KEYS,
    RESULTS_BODY_KEYS,
    TODAY_RUNNING,
)

ADMIN = "/v1/admin"
ME = "/v1/me"
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422
LIMIT = 256 * 1024  # 제출 본문 상한(app.endpoints.survey_learner.SURVEY_BODY_MAX_BYTES)
TOP_KEYS = {"course", "sections", "survey"}  # 포털 맨 위(T8 결정 xv)
ADMIN_ROSTER_KEYS = {"id", "name", "dept", "email", "enrolled_at", "survey_responded"}
LATER = date(2026, 11, 10)


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _default_id(client: httpx.AsyncClient, admin: dict[str, str]) -> int:
    items = _ok(await client.get(f"{ADMIN}/survey-templates", headers=admin))["items"]
    (tid,) = [t["id"] for t in items if t["is_default"]]
    return int(tid)


async def _deploy(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    course_id: int,
    template_id: int,
    **modes: Any,
) -> dict[str, Any]:
    body = _ok(
        await client.post(
            f"{ADMIN}/surveys",
            headers=admin,
            json={"course_ids": [course_id], "template_id": template_id, **modes},
        ),
        201,
    )
    item: dict[str, Any] = body["items"][0]
    return item


async def _close(client: httpx.AsyncClient, admin: dict[str, str], sid: int) -> None:
    _ok(await client.post(f"{ADMIN}/surveys/{sid}:close", headers=admin))


async def _learner(
    client: httpx.AsyncClient, code: str, email: str, name: str = "수강생", **extra: Any
) -> dict[str, str]:
    r = await enter_learner(client, code, email, name, **extra)
    assert r.status_code in (200, 201), r.text
    return bearer(r.json()["access_token"])


async def _assign_to(
    client: httpx.AsyncClient, admin: dict[str, str], course_id: int, iid: int
) -> None:
    sid = await add_session(client, admin, course_id)
    r = await client.patch(
        f"{ADMIN}/sessions/{sid}", headers=admin, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


def _both(flags: dict[str, bool | None]) -> dict[str, dict[str, bool | None]]:
    """강사 명단 · 관리자 명단이 같은 응답 여부."""
    return {"instructor": dict(flags), "admin": dict(flags)}


def _url(course_id: int) -> str:
    return f"/v1/learner/courses/{course_id}/survey"


async def _view(
    client: httpx.AsyncClient, headers: dict[str, str], course_id: int
) -> dict[str, Any]:
    body: dict[str, Any] = _ok(await client.get(_url(course_id), headers=headers))
    return body


async def _post(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    course_id: int,
    survey_id: int,
    questions_hash: str,
    answers: dict[str, Any] | None = None,
) -> httpx.Response:
    return await client.post(
        _url(course_id) + "/responses",
        headers=headers,
        json={
            "survey_id": survey_id,
            "questions_hash": questions_hash,
            "answers": ANSWERS_OK if answers is None else answers,
        },
    )


async def _submit(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    course_id: int,
    answers: dict[str, Any] | None = None,
) -> httpx.Response:
    """지금 보이는 설문판(id·해시)으로 낸다."""
    survey = (await _view(client, headers, course_id))["survey"]
    assert survey is not None
    return await _post(
        client, headers, course_id, survey["id"], survey["questions_hash"], answers
    )


async def test_survey_submit_version_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    learner = await _learner(client, code.code, "kim@example.com")
    s1 = await _deploy(client, admin, course.id, tid)
    seen = (await _view(client, learner, course.id))["survey"]
    assert seen["id"] == s1["id"]

    # 보고 있는 사이 재배포 — 옛 설문판으로 낸 답은 새 설문에 들어가지 않는다
    await _close(client, admin, s1["id"])
    s2 = await _deploy(client, admin, course.id, tid)
    body = problem_of(
        await _post(client, learner, course.id, seen["id"], seen["questions_hash"]),
        409,
        "/problems/conflict",
    )
    assert body["reason"] == "survey_changed"
    assert await count(db_session, SurveyResponse) == 0

    # 첫 응답 전 문항 수정 — 키가 같아도 옛 해시는 409
    now = (await _view(client, learner, course.id))["survey"]
    assert now["id"] == s2["id"]
    questions = [
        {**q, "text": q["text"] + " (개정)"} if q["key"] == "b01" else q
        for q in now["questions"]
    ]
    _ok(
        await client.patch(
            f"{ADMIN}/surveys/{s2['id']}", headers=admin, json={"questions": questions}
        )
    )
    body = problem_of(
        await _post(client, learner, course.id, now["id"], now["questions_hash"]),
        409,
        "/problems/conflict",
    )
    assert body["reason"] == "survey_changed"
    fresh = (await _view(client, learner, course.id))["survey"]
    assert fresh["questions_hash"] != now["questions_hash"]
    r = await _post(client, learner, course.id, fresh["id"], fresh["questions_hash"])
    assert _ok(r, 201) == {"survey_id": s2["id"], "responded": True}
    assert await count(db_session, SurveyResponse) == 1


async def test_survey_submit_body_limits(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    learner = await _learner(client, code.code, "kim@example.com")
    await _deploy(client, admin, course.id, tid)
    url = _url(course.id) + "/responses"
    json_type = {"content-type": "application/json"}

    # Content-Length 가 상한을 넘으면 읽기 전에 413
    big = b" " * (LIMIT + 1)
    body = problem_of(
        await client.post(url, headers={**learner, **json_type}, content=big),
        413,
        "/problems/content-too-large",
    )
    assert "262144바이트" in body["detail"]

    # Content-Length 없는 chunked 도 스트림 누적으로 413
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(5):
            yield b" " * (64 * 1024)

    chunked = await client.post(url, headers={**learner, **json_type}, content=chunks())
    assert "content-length" not in chunked.request.headers
    problem_of(chunked, 413, "/problems/content-too-large")

    # 기형 JSON · 깊은 중첩(상한 안 ≈195KiB) 둘 다 422 json_invalid(500 아님)
    for raw in (b"{", b"", b"[" * 200_000):
        body = problem_of(
            await client.post(url, headers={**learner, **json_type}, content=raw), 422
        )
        assert locs(body) == [["body"]], raw[:10]
        assert [v["type"] for v in body["violations"]] == ["json_invalid"]
    # 모양 밖은 loc body 접두
    view = (await _view(client, learner, course.id))["survey"]
    body = problem_of(
        await client.post(
            url,
            headers=learner,
            json={
                "survey_id": view["id"],
                "questions_hash": view["questions_hash"],
                "answers": [],
            },
        ),
        422,
    )
    assert locs(body) == [["body", "answers"]]
    body = problem_of(
        await client.post(
            url,
            headers=learner,
            json={"survey_id": view["id"], "questions_hash": "짧음", "answers": {}},
        ),
        422,
    )
    assert sorted(v[1] for v in locs(body)) == ["answers", "questions_hash"]
    assert await count(db_session, SurveyResponse) == 0

    # 인증이 본문보다 먼저 — 토큰 없음 401 · 관리자 403(상한을 넘는 본문이어도)
    anonymous = await client.post(url, headers=json_type, content=big)
    problem_of(anonymous, 401)
    assert anonymous.headers["www-authenticate"] == "Bearer"
    problem_of(await client.post(url, headers={**admin, **json_type}, content=big), 403)

    r = await _post(client, learner, course.id, view["id"], view["questions_hash"])
    assert r.status_code == 201, r.text

    # OpenAPI 에 requestBody 가 남는다(본문 매개변수가 아니라 의존성으로 읽어도)
    spec = _ok(await client.get("/v1/openapi.json"))
    op = spec["paths"]["/v1/learner/courses/{course_id}/survey/responses"]["post"]
    assert op["requestBody"]["required"] is True
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert schema == SubmitIn.model_json_schema()
    assert schema["required"] == ["survey_id", "questions_hash", "answers"]


async def test_survey_learner_view_states(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    other, other_code = await open_test_course(db_session, title="다른 강의")
    learner = await _learner(client, code.code, "kim@example.com", dept="교육팀")

    view = await _view(client, learner, course.id)
    assert set(view) == LEARNER_SURVEY_KEYS
    assert view == {
        "status": "none",
        "survey": None,
        "responded": False,
        "prefill_dept": "교육팀",
    }
    survey = await _deploy(
        client,
        admin,
        course.id,
        tid,
        open={"mode": "date", "date": "2026-11-04"},
        close={"mode": "date", "date": "2026-11-06"},
    )
    view = await _view(client, learner, course.id)
    assert (view["status"], view["survey"], view["responded"]) == (
        "scheduled",
        None,
        False,
    )

    set_today(app, date(2026, 11, 4))
    view = await _view(client, learner, course.id)
    assert view["status"] == "open"
    opened = view["survey"]
    assert set(opened) == LEARNER_SURVEY_BODY_KEYS
    assert (opened["id"], opened["open_on"], opened["close_on"]) == (
        survey["id"],
        "2026-11-04",
        "2026-11-06",
    )
    assert len(opened["questions_hash"]) == 16
    assert len(opened["questions"]) == 24
    for q in opened["questions"]:
        assert set(q) == QUESTION_KEYS, q

    r = await _submit(client, learner, course.id)
    assert r.status_code == 201, r.text
    view = await _view(client, learner, course.id)
    assert (view["status"], view["responded"], view["survey"]) == ("open", True, opened)

    set_today(app, date(2026, 11, 7))
    view = await _view(client, learner, course.id)
    assert (view["status"], view["survey"], view["responded"]) == ("closed", None, True)

    # 다른 강의 경로는 403(토큰은 강의 하나에 묶인다) · 범위 밖 422
    for path in (_url(other.id), _url(other.id) + "/responses"):
        method = "GET" if path.endswith("/survey") else "POST"
        problem_of(
            await client.request(
                method,
                path,
                headers=learner,
                json={
                    "survey_id": survey["id"],
                    "questions_hash": opened["questions_hash"],
                    "answers": ANSWERS_OK,
                },
            ),
            403,
            "/problems/forbidden",
        )
    body = problem_of(await client.get(_url(OVERFLOW), headers=learner), 422)
    assert locs(body) == [["path", "course_id"]]
    assert other_code.code  # 다른 강의에는 아무도 들어가지 않았다


async def test_survey_submit_once_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    learner = await _learner(client, code.code, "kim@example.com", "김가명")
    survey = await _deploy(client, admin, course.id, tid)
    view = (await _view(client, learner, course.id))["survey"]
    audits_before = await count(db_session, AuditLog)

    r = await _post(client, learner, course.id, view["id"], view["questions_hash"])
    assert _ok(r, 201) == {"survey_id": survey["id"], "responded": True}
    body = problem_of(
        await _post(client, learner, course.id, view["id"], view["questions_hash"]),
        409,
        "/problems/conflict",
    )
    assert body.get("reason") != "survey_changed"
    # 재입장해 토큰이 바뀌어도 같은 등록이다
    again = await _learner(client, code.code, "kim@example.com", "김가명")
    assert again != learner
    problem_of(
        await _post(client, again, course.id, view["id"], view["questions_hash"]),
        409,
        "/problems/conflict",
    )
    # 다시 열어도 기존 응답자는 1회
    await _close(client, admin, survey["id"])
    _ok(await client.post(f"{ADMIN}/surveys/{survey['id']}:reopen", headers=admin))
    problem_of(
        await _post(client, again, course.id, view["id"], view["questions_hash"]),
        409,
        "/problems/conflict",
    )
    assert await count(db_session, SurveyResponse) == 1
    assert await count(db_session, AuditLog) == audits_before + 2  # 닫기·다시 열기만

    # 열리지 않은 설문(예약·닫힘) 409 · 현재 설문이 없는 강의 404
    planned, planned_code = await open_test_course(db_session, title="예약 강의")
    p_learner = await _learner(client, planned_code.code, "lee@example.com")
    await _deploy(
        client, admin, planned.id, tid, open={"mode": "date", "date": "2026-11-05"}
    )
    set_today(app, date(2026, 11, 5))
    p_view = (await _view(client, p_learner, planned.id))["survey"]  # 열린 날의 설문판
    set_today(app, TODAY_RUNNING)
    body = problem_of(
        await _post(
            client, p_learner, planned.id, p_view["id"], p_view["questions_hash"]
        ),
        409,
        "/problems/conflict",
    )
    assert body.get("reason") != "survey_changed"
    await _close(client, admin, p_view["id"])
    problem_of(
        await _post(
            client, p_learner, planned.id, p_view["id"], p_view["questions_hash"]
        ),
        409,
        "/problems/conflict",
    )
    bare, bare_code = await open_test_course(db_session, title="설문 없는 강의")
    b_learner = await _learner(client, bare_code.code, "park@example.com")
    problem_of(
        await _post(client, b_learner, bare.id, view["id"], view["questions_hash"]),
        404,
        "/problems/not_found",
    )
    assert await count(db_session, SurveyResponse) == 1


async def test_survey_submit_validation_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    learner = await _learner(client, code.code, "kim@example.com")
    await _deploy(client, admin, course.id, tid)
    view = (await _view(client, learner, course.id))["survey"]
    by_key = {q["key"]: q for q in view["questions"]}
    assert by_key["exp"]["custom"] is False and by_key["dept"]["custom"] is True
    pick = by_key["next_type"]["options"][0]
    without_overall = {k: v for k, v in ANSWERS_OK.items() if k != "overall"}
    cases: list[tuple[dict[str, Any], str, str]] = [
        (without_overall, "overall", "missing"),
        ({**ANSWERS_OK, "zzz": 1}, "zzz", "unknown"),
        ({**ANSWERS_OK, "b01": 6}, "b01", "invalid"),
        ({**ANSWERS_OK, "b01": 0}, "b01", "invalid"),
        ({**ANSWERS_OK, "b01": "4"}, "b01", "invalid"),
        ({**ANSWERS_OK, "exp": "목록 밖 값"}, "exp", "invalid"),
        ({**ANSWERS_OK, "dept": "   "}, "dept", "invalid"),
        ({**ANSWERS_OK, "next_type": [pick, pick]}, "next_type", "invalid"),
        ({**ANSWERS_OK, "c1": "가" * 2001}, "c1", "invalid"),
        ({**ANSWERS_OK, "info": "값"}, "info", "invalid"),
    ]
    for answers, key, kind in cases:
        body = problem_of(
            await _post(
                client, learner, course.id, view["id"], view["questions_hash"], answers
            ),
            422,
        )
        assert [(v["loc"], v["type"]) for v in body["violations"]] == [
            (["body", "answers", key], kind)
        ], (key, body["violations"])
    r = await client.post(
        _url(course.id) + "/responses",
        headers=learner,
        json={
            "survey_id": view["id"],
            "questions_hash": view["questions_hash"],
            "answers": ANSWERS_OK,
            "submitted_at": "2026-11-03T00:00:00Z",
        },
    )
    body = problem_of(r, 422)
    assert [(v["loc"], v["type"]) for v in body["violations"]] == [
        (["body", "submitted_at"], "extra_forbidden")
    ]
    assert await count(db_session, SurveyResponse) == 0
    # 필수만 채운 답은 받는다(선택 문항은 비워도 된다)
    required = {
        q["key"]: ANSWERS_OK[q["key"]] for q in view["questions"] if q["required"]
    }
    r = await _post(
        client, learner, course.id, view["id"], view["questions_hash"], required
    )
    assert r.status_code == 201, r.text


async def test_survey_portal_banner(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    course, code = await open_test_course(db_session)
    await _assign_to(client, admin, course.id, x)
    learner = await _learner(
        client, code.code, "kim@example.com", "김가명", dept="교육팀"
    )
    urls = {
        "learner": (f"/v1/learner/courses/{course.id}/portal", learner),
        "admin": (f"{ADMIN}/courses/{course.id}/portal", admin),
        "instructor": (f"{ME}/courses/{course.id}/portal", x_auth),
    }

    async def portals() -> dict[str, dict[str, Any]]:
        out = {}
        for who, (url, headers) in urls.items():
            body = _ok(await client.get(url, headers=headers))
            assert set(body) == TOP_KEYS, who
            assert json_keys(body) & PERSONAL_KEYS == set(), who
            out[who] = body
        assert out["instructor"] == out["learner"]  # 미리 보기 == 수강생 포털
        return out

    assert {who: p["survey"] for who, p in (await portals()).items()} == dict.fromkeys(
        urls, None
    )
    first = await _deploy(client, admin, course.id, tid)
    banner = {
        "id": first["id"],
        "status": "open",
        "open_on": "2026-11-03",
        "close_on": "2026-11-19",
    }
    got = await portals()
    for who, body in got.items():
        assert set(body["survey"]) == PORTAL_SURVEY_KEYS, who
        assert body["survey"] == banner, who
    # 응답 뒤에도 같다 — 응답 여부는 포털에 없다(숨김은 설문 GET 의 responded)
    r = await _submit(client, learner, course.id)
    assert r.status_code == 201, r.text
    assert {who: p["survey"] for who, p in (await portals()).items()} == dict.fromkeys(
        urls, banner
    )
    # 닫으면 상태만 바뀌고, 재배포하면 셋 다 새 설문(밀려난 설문이 아니다)
    await _close(client, admin, first["id"])
    assert {p["survey"]["status"] for p in (await portals()).values()} == {"closed"}
    second = await _deploy(client, admin, course.id, tid)
    assert {p["survey"]["id"] for p in (await portals()).values()} == {second["id"]}
    for who, body in (await portals()).items():
        for secret in ("김가명", "kim@example.com", "교육팀"):
            assert secret not in str(body), (who, secret)


async def test_survey_roster_responded(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    course, code = await open_test_course(db_session)
    await _assign_to(client, admin, course.id, x)
    kim = await _learner(client, code.code, "kim@example.com", "김가명")
    await _learner(client, code.code, "lee@example.com", "이가명")
    mine = f"{ME}/courses/{course.id}/enrollments"
    admins = f"{ADMIN}/courses/{course.id}/enrollments"

    async def flags() -> dict[str, dict[str, bool | None]]:
        out: dict[str, dict[str, bool | None]] = {}
        for who, url, headers, keys in (
            ("instructor", mine, x_auth, ROSTER_KEYS),
            ("admin", admins, admin, ADMIN_ROSTER_KEYS),
        ):
            body = _ok(await client.get(url, headers=headers))
            for item in body["items"]:
                assert set(item) == keys, (who, item)
            assert json_keys(body) & {"answers", "submitted_at", "survey_id"} == set()
            out[who] = {i["name"]: i["survey_responded"] for i in body["items"]}
        return out

    assert await flags() == _both({"김가명": None, "이가명": None})  # 배포 전
    survey = await _deploy(client, admin, course.id, tid)
    assert await flags() == _both({"김가명": False, "이가명": False})
    r = await _submit(client, kim, course.id)
    assert r.status_code == 201, r.text
    assert await flags() == _both({"김가명": True, "이가명": False})
    # 재배포하면 새 현재 설문 기준이다(옛 응답은 여부에 남지 않는다)
    await _close(client, admin, survey["id"])
    await _deploy(client, admin, course.id, tid)
    assert await flags() == _both({"김가명": False, "이가명": False})


async def test_survey_home_notice(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    mine, code = await open_test_course(db_session, title="내 강의")
    archived, _ = await open_test_course(db_session, title="보관 강의")
    theirs, _ = await open_test_course(db_session, title="남의 강의")
    await _assign_to(client, admin, mine.id, x)
    await _assign_to(client, admin, archived.id, x)
    await _assign_to(client, admin, theirs.id, y)
    kim = await _learner(client, code.code, "kim@example.com")
    await _learner(client, code.code, "lee@example.com")

    async def home() -> dict[str, Any]:
        body: dict[str, Any] = _ok(await client.get(f"{ME}/home", headers=x_auth))
        assert {"surveys", "surveys_more"} <= set(body)
        assert body["surveys_more"] is False
        return body

    assert (await home())["surveys"] == []
    survey = await _deploy(client, admin, mine.id, tid)
    await _deploy(client, admin, archived.id, tid)
    await _deploy(client, admin, theirs.id, tid)
    _ok(await client.post(f"{ADMIN}/courses/{archived.id}:archive", headers=admin))
    (item,) = (await home())["surveys"]
    assert set(item) == HOME_SURVEY_KEYS
    assert item == {
        "course_id": mine.id,
        "course_title": "내 강의",
        "survey_id": survey["id"],
        "status": "open",
        "open_on": "2026-11-03",
        "close_on": "2026-11-19",
        "reopened_at": None,
        "responses": 0,
        "total": 2,
    }
    r = await _submit(client, kim, mine.id)
    assert r.status_code == 201, r.text
    (item,) = (await home())["surveys"]
    assert (item["responses"], item["total"]) == (1, 2)
    await _close(client, admin, survey["id"])
    (item,) = (await home())["surveys"]
    assert item["status"] == "closed"
    body = await home()
    assert json_keys(body) & RESULT_FORBIDDEN_KEYS == set()


async def test_survey_cross_course_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    _, p_auth = await approved(db_session, settings, email="p@example.com")
    a, a_code = await open_test_course(db_session, title="가 강의")
    _, b_code = await open_test_course(db_session, title="나 강의")
    await _assign_to(client, admin, a.id, x)
    a_learner = await _learner(client, a_code.code, "kim@example.com")
    b_learner = await _learner(client, b_code.code, "lee@example.com")
    survey = await _deploy(client, admin, a.id, tid)
    view = (await _view(client, a_learner, a.id))["survey"]

    problem_of(
        await client.get(_url(a.id), headers=b_learner), 403, "/problems/forbidden"
    )
    problem_of(
        await _post(client, b_learner, a.id, view["id"], view["questions_hash"]),
        403,
        "/problems/forbidden",
    )
    assert await count(db_session, SurveyResponse) == 0

    results = f"{ME}/courses/{a.id}/survey-results"
    got = _ok(await client.get(results, headers=x_auth))
    assert got["head"]["survey_id"] == survey["id"]
    problem_of(await client.get(results, headers=p_auth), 403, "/problems/forbidden")
    problem_of(await client.get(results, headers=a_learner), 403, "/problems/forbidden")
    problem_of(
        await client.get(f"{ME}/courses/{LARGEST}/survey-results", headers=x_auth),
        404,
        "/problems/not_found",
    )
    body = problem_of(
        await client.get(f"{ME}/courses/{OVERFLOW}/survey-results", headers=x_auth),
        422,
    )
    assert locs(body) == [["path", "course_id"]]
    # 배정된 강의라도 현재 설문이 없으면 404
    c, _ = await open_test_course(db_session, title="다 강의")
    await _assign_to(client, admin, c.id, x)
    problem_of(
        await client.get(f"{ME}/courses/{c.id}/survey-results", headers=x_auth),
        404,
        "/problems/not_found",
    )
    for path in (_url(OVERFLOW), _url(OVERFLOW) + "/responses"):
        method = "GET" if path.endswith("/survey") else "POST"
        body = problem_of(
            await client.request(
                method,
                path,
                headers=a_learner,
                json={
                    "survey_id": view["id"],
                    "questions_hash": view["questions_hash"],
                    "answers": ANSWERS_OK,
                },
            ),
            422,
        )
        assert locs(body) == [["path", "course_id"]]


async def test_no_personal_keys_i7(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    course, code = await open_test_course(db_session)
    planned, _ = await open_test_course(db_session, title="예약 강의")
    await _assign_to(client, admin, course.id, x)
    await _assign_to(client, admin, planned.id, x)
    people = [
        await _learner(client, code.code, f"s{n}@example.com", f"가명{n}")
        for n in range(1, 6)
    ]
    survey = await _deploy(client, admin, course.id, tid)
    await _deploy(
        client, admin, planned.id, tid, open={"mode": "date", "date": "2026-11-10"}
    )
    url = f"{ME}/courses/{course.id}/survey-results"

    async def mine(path: str = url) -> dict[str, Any]:
        body: dict[str, Any] = _ok(await client.get(path, headers=x_auth))
        assert json_keys(body) & RESULT_FORBIDDEN_KEYS == set()
        assert json_keys(body) & PERSONAL_KEYS == set()
        return body

    # 닫히지 않았으면(열림·예약) 숨김 — 응답률은 준다
    for path in (url, f"{ME}/courses/{planned.id}/survey-results"):
        body = await mine(path)
        assert (body["visible"], body["reason"], body["results"]) == (
            False,
            "not_closed",
            None,
        )
        assert body["min_responses"] == 5
    for headers in people[:4]:
        r = await _submit(client, headers, course.id)
        assert r.status_code == 201, r.text
    body = await mine()
    assert body["response_rate"] == {"responses": 4, "total": 5, "percent": 80}

    await _close(client, admin, survey["id"])
    body = await mine()
    assert (body["visible"], body["reason"], body["results"]) == (
        False,
        "below_minimum",
        None,
    )
    assert body["head"]["status"] == "closed"

    # 다시 열어 5번째 응답을 받고 닫으면 공개
    _ok(await client.post(f"{ADMIN}/surveys/{survey['id']}:reopen", headers=admin))
    r = await _submit(client, people[4], course.id)
    assert r.status_code == 201, r.text
    await _close(client, admin, survey["id"])
    r = await client.get(url, headers=x_auth)
    body = await mine()
    assert (body["visible"], body["reason"], body["min_responses"]) == (True, None, 5)
    assert set(body) == MY_RESULTS_TOP_KEYS
    assert set(body["head"]) == HEAD_KEYS
    assert json_keys(body) == MY_RESULTS_KEYS
    assert set(body["results"]) == RESULTS_BODY_KEYS
    assert body["results"]["overall"]["n"] == 5
    assert {"created_at", "closed_at"} & set(body["head"]) == set()
    admin_view = _ok(
        await client.get(f"{ADMIN}/surveys/{survey['id']}/results", headers=admin)
    )
    for key in ("overall", "areas", "questions", "texts"):
        assert body["results"][key] == admin_view[key], key  # 관리자와 같은 집계
    for n in range(1, 6):
        assert f"s{n}@example.com" not in r.text and f"가명{n}" not in r.text

    # 임계는 설정 칸이다 — 2 로 낮추면 2건에 공개
    app.state.settings = Settings(survey_min_responses=2)
    small, small_code = await open_test_course(db_session, title="작은 강의")
    await _assign_to(client, admin, small.id, x)
    two = [
        await _learner(client, small_code.code, f"t{n}@example.com") for n in range(2)
    ]
    s2 = await _deploy(client, admin, small.id, tid)
    for headers in two:
        r = await _submit(client, headers, small.id)
        assert r.status_code == 201, r.text
    await _close(client, admin, s2["id"])
    body = await mine(f"{ME}/courses/{small.id}/survey-results")
    assert (body["visible"], body["min_responses"]) == (True, 2)
