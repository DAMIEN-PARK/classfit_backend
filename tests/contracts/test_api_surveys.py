"""배포 설문(관리자): 배포 모드·알림 · 충돌·밀어내기 · 오늘 기준 상태 · 마감·다시 열기·PATCH · 문항 잠금 · 목록 ·
입력 범위 · A5 결과에 개인 키 없음(T8 계획 결정 iii·vi·vii·x·xi·xiii·xvii·xviii·xxv·xxvi · 증명 3~10).

상태는 저장값이 아니라 오늘(Today) 기준 계산값이라 set_today 로 날짜를 옮겨 잰다. 응답은 허용 키 집합을 정확히 잰다.
픽스처 강의는 2026-11-02(월)부터 평일 4일(끝 2026-11-05)이고 오늘은 진행 중인 2026-11-03 이 기본이다. 닫힘 기본은 종료일 +
survey_close_days(14)다. 응답자 이름·이메일은 결과 어디에도 없어야 한다.
"""

from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import AuditLog, MailOutbox, Survey
from classfit.service.rules.survey import normalize_answers
from classfit.service.rules.survey_stats import ScaleStat, aggregate
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
from tests.fixtures.records import set_today
from tests.fixtures.surveys import (
    ANSWERS_OK,
    HEAD_KEYS,
    RESULT_FORBIDDEN_KEYS,
    RESULTS_KEYS,
    RESULTS_TOP_KEYS,
    SURVEY_KEYS,
    TODAY_RUNNING,
)

ADMIN = "/v1/admin"
SURVEYS = f"{ADMIN}/surveys"
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422
PAGE_KEYS = {"items", "next_cursor", "has_more"}
NEXT_DAY = TODAY_RUNNING + timedelta(days=1)
OWN_QUESTIONS: list[dict[str, Any]] = [
    {"key": "q1", "type": "scale", "text": "만족도", "is_overall": True},
    {"key": "q2", "type": "text", "text": "의견", "required": False},
]


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
    course_ids: list[int],
    template_id: int,
    **modes: Any,
) -> httpx.Response:
    """modes 는 open={mode, date?} · close={mode, date?}(없으면 기본 now · end_plus_14)."""
    return await client.post(
        SURVEYS,
        headers=admin,
        json={"course_ids": course_ids, "template_id": template_id, **modes},
    )


async def _deployed(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    course_ids: list[int],
    template_id: int,
    **modes: Any,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = _ok(
        await _deploy(client, admin, course_ids, template_id, **modes), 201
    )["items"]
    return items


async def _listed(
    client: httpx.AsyncClient, admin: dict[str, str], **params: Any
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = _ok(
        await client.get(SURVEYS, headers=admin, params=params)
    )["items"]
    return items


async def _learner(
    client: httpx.AsyncClient, code: str, email: str, name: str = "수강생", **extra: Any
) -> dict[str, str]:
    r = await enter_learner(client, code, email, name, **extra)
    assert r.status_code == 201, r.text
    return bearer(r.json()["access_token"])


async def _assign_to(
    client: httpx.AsyncClient, admin: dict[str, str], course_id: int, iid: int
) -> None:
    """그 강의에 세션 하나를 만들어 iid 강사에게 배정한다(배정 강사 = 설문 알림 수신자)."""
    sid = await add_session(client, admin, course_id)
    r = await client.patch(
        f"{ADMIN}/sessions/{sid}", headers=admin, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


async def _view(
    client: httpx.AsyncClient, headers: dict[str, str], course_id: int
) -> dict[str, Any]:
    body: dict[str, Any] = _ok(
        await client.get(f"/v1/learner/courses/{course_id}/survey", headers=headers)
    )
    return body


async def _submit(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    course_id: int,
    answers: dict[str, Any],
) -> httpx.Response:
    """지금 보이는 설문판(id·해시)으로 낸다."""
    survey = (await _view(client, headers, course_id))["survey"]
    assert survey is not None
    return await client.post(
        f"/v1/learner/courses/{course_id}/survey/responses",
        headers=headers,
        json={
            "survey_id": survey["id"],
            "questions_hash": survey["questions_hash"],
            "answers": answers,
        },
    )


async def _audits(session: AsyncSession, action: str) -> list[tuple[Any, ...]]:
    """그 action 의 (target_type, target_id, detail), id 순."""
    rows = await session.execute(
        select(AuditLog.target_type, AuditLog.target_id, AuditLog.detail)
        .where(AuditLog.action == action)
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _outbox(session: AsyncSession, kind: str) -> dict[str, list[dict[str, Any]]]:
    """그 kind 의 수신 주소 → params 목록."""
    rows = await session.execute(
        select(MailOutbox.to, MailOutbox.params)
        .where(MailOutbox.kind == kind)
        .order_by(MailOutbox.id)
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for to, params in rows:
        out.setdefault(to, []).append(params)
    return out


async def test_survey_deploy_defaults_and_keys(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    aid, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    first, first_code = await open_test_course(db_session, title="가 강의")
    second, second_code = await open_test_course(
        db_session, title="나 강의", start_on=date(2026, 11, 9), day_count=2
    )  # 끝 11-10
    x, _ = await approved(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    await _assign_to(client, admin, first.id, x)
    await _assign_to(client, admin, second.id, y)
    for code, email in (
        (first_code.code, "a1@example.com"),
        (first_code.code, "a2@example.com"),
        (second_code.code, "b1@example.com"),
    ):
        await _learner(client, code, email)

    # 종료일이 다른 강의 둘을 한 요청으로 — 강의마다 제 종료일 + 14
    body = _ok(await _deploy(client, admin, [second.id, first.id, first.id], tid), 201)
    assert set(body) == {"items"}
    items = body["items"]
    for item in items:
        assert set(item) == SURVEY_KEYS, item
    assert [
        (
            i["course_id"],
            i["course_title"],
            i["client_name"],
            i["template_id"],
            i["template_name"],
            i["status"],
            i["open_on"],
            i["close_on"],
            i["closed_at"],
            i["reopened_at"],
            i["current"],
            i["responses"],
            i["total"],
            i["locked"],
        )
        for i in items
    ] == [
        (
            first.id,
            "가 강의",
            "A사",
            tid,
            "기본 양식",
            "open",
            "2026-11-03",
            "2026-11-19",
            None,
            None,
            True,
            0,
            2,
            False,
        ),
        (
            second.id,
            "나 강의",
            "A사",
            tid,
            "기본 양식",
            "open",
            "2026-11-03",
            "2026-11-24",
            None,
            None,
            True,
            0,
            1,
            False,
        ),
    ]
    a_id, b_id = items[0]["id"], items[1]["id"]

    # 알림: 강의마다 등록 수강생 전원 + 배정 강사, 본문에 쓸 값은 params 스냅샷
    opened = await _outbox(db_session, "survey_opened")
    assert sorted(opened) == sorted(
        [
            "a1@example.com",
            "a2@example.com",
            "x@example.com",
            "b1@example.com",
            "y@example.com",
        ]
    )
    assert all(len(v) == 1 for v in opened.values())
    a_params = {
        "survey_id": a_id,
        "course_title": "가 강의",
        "open_on": "2026-11-03",
        "close_on": "2026-11-19",
    }
    for to in ("a1@example.com", "a2@example.com", "x@example.com"):
        assert opened[to] == [a_params], to
    assert opened["y@example.com"] == [
        {
            "survey_id": b_id,
            "course_title": "나 강의",
            "open_on": "2026-11-03",
            "close_on": "2026-11-24",
        }
    ]
    deploys = await _audits(db_session, "survey.deploy")
    assert [(d[0], d[1]) for d in deploys] == [
        ("course", str(first.id)),
        ("course", str(second.id)),
    ]
    assert (deploys[0][2]["survey_id"], deploys[0][2]["template_id"]) == (a_id, tid)
    assert deploys[0][2]["superseded_id"] is None
    actors = await db_session.scalars(
        select(AuditLog.actor).where(AuditLog.action == "survey.deploy")
    )
    assert set(actors) == {f"admin:{aid}"}

    # 열기 모드 course_end: 지난 종료일이면 오늘, 앞이면 그 날(예약)
    ended, _ = await open_test_course(
        db_session, title="끝난 강의", start_on=date(2026, 10, 19), day_count=2
    )  # 끝 10-20 → + 14 = 11-03(열림일과 같은 날)
    later, _ = await open_test_course(
        db_session, title="뒤 강의", start_on=date(2026, 11, 16), day_count=2
    )  # 끝 11-17
    got = await _deployed(
        client, admin, [ended.id, later.id], tid, open={"mode": "course_end"}
    )
    assert [(i["status"], i["open_on"], i["close_on"]) for i in got] == [
        ("open", "2026-11-03", "2026-11-03"),
        ("scheduled", "2026-11-17", "2026-12-01"),
    ]
    # 열기 date(종료 + 20): 종료 + 14 가 열림일보다 앞이라 닫힘은 열림 + 7
    third, _ = await open_test_course(db_session, title="다 강의")
    (got,) = await _deployed(
        client, admin, [third.id], tid, open={"mode": "date", "date": "2026-11-25"}
    )
    assert (got["status"], got["open_on"], got["close_on"]) == (
        "scheduled",
        "2026-11-25",
        "2026-12-02",
    )
    fourth, _ = await open_test_course(db_session, title="라 강의")
    (got,) = await _deployed(
        client, admin, [fourth.id], tid, close={"mode": "open_plus_7"}
    )
    assert (got["open_on"], got["close_on"]) == ("2026-11-03", "2026-11-10")
    fifth, _ = await open_test_course(db_session, title="마 강의")
    (got,) = await _deployed(
        client, admin, [fifth.id], tid, close={"mode": "date", "date": "2026-11-30"}
    )
    assert (got["open_on"], got["close_on"]) == ("2026-11-03", "2026-11-30")
    assert len(await _audits(db_session, "survey.deploy")) == 7


async def test_survey_deploy_conflicts(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    opened, opened_code = await open_test_course(db_session, title="열린 강의")
    planned, _ = await open_test_course(db_session, title="예약 강의")
    archived, _ = await open_test_course(db_session, title="보관 강의")
    clean, _ = await open_test_course(db_session, title="빈 강의")
    learner = await _learner(client, opened_code.code, "kim@example.com")

    (first,) = await _deployed(client, admin, [opened.id], tid)
    problem_of(
        await _deploy(client, admin, [opened.id], tid), 409, "/problems/conflict"
    )
    await _deployed(
        client, admin, [planned.id], tid, open={"mode": "date", "date": "2026-11-10"}
    )
    problem_of(
        await _deploy(client, admin, [planned.id], tid), 409, "/problems/conflict"
    )
    _ok(await client.post(f"{ADMIN}/courses/{archived.id}:archive", headers=admin))
    problem_of(
        await _deploy(client, admin, [archived.id], tid), 409, "/problems/conflict"
    )
    # 한 강의라도 409 면 전부 0행(부분 성공 없음)
    problem_of(
        await _deploy(client, admin, [clean.id, opened.id], tid),
        409,
        "/problems/conflict",
    )
    assert await count(db_session, Survey, Survey.course_id == clean.id) == 0
    assert await count(db_session, Survey) == 2

    # 관리자가 닫은 뒤 재배포 — 옛 행은 밀려나고(current false) 수강생은 새 설문을 본다
    _ok(await client.post(f"{SURVEYS}/{first['id']}:close", headers=admin))
    (second,) = await _deployed(client, admin, [opened.id], tid)
    assert [
        (i["id"], i["current"], i["status"])
        for i in await _listed(client, admin, course_id=opened.id)
    ] == [(second["id"], True, "open"), (first["id"], False, "closed")]
    deploys = await _audits(db_session, "survey.deploy")
    assert deploys[-1][2]["superseded_id"] == first["id"]
    view = await _view(client, learner, opened.id)
    assert (view["status"], view["survey"]["id"]) == ("open", second["id"])

    # 날짜로 닫힌(closed_at 없음) 현재 설문을 재배포하면 밀려난 행의 closed_at 이 채워진다
    dated, _ = await open_test_course(db_session, title="날짜 강의")
    (old,) = await _deployed(
        client,
        admin,
        [dated.id],
        tid,
        close={"mode": "date", "date": TODAY_RUNNING.isoformat()},
    )
    set_today(app, NEXT_DAY)
    (listed,) = await _listed(client, admin, course_id=dated.id)
    assert (listed["status"], listed["closed_at"], listed["current"]) == (
        "closed",
        None,
        True,
    )
    (new,) = await _deployed(client, admin, [dated.id], tid)
    rows = await _listed(client, admin, course_id=dated.id)
    assert [(i["id"], i["current"]) for i in rows] == [
        (new["id"], True),
        (old["id"], False),
    ]
    assert rows[1]["closed_at"] is not None
    assert rows[0]["status"] == "open"


async def test_survey_status_follows_today(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    learner = await _learner(client, code.code, "kim@example.com")
    (survey,) = await _deployed(
        client,
        admin,
        [course.id],
        tid,
        open={"mode": "date", "date": "2026-11-04"},
        close={"mode": "date", "date": "2026-11-06"},
    )
    assert survey["status"] == "scheduled"
    for today, expected in (
        (date(2026, 11, 3), "scheduled"),
        (date(2026, 11, 4), "open"),  # 열림일 당일
        (date(2026, 11, 6), "open"),  # 닫힘일 당일까지 열림
        (date(2026, 11, 7), "closed"),
    ):
        set_today(app, today)
        (item,) = await _listed(client, admin, course_id=course.id)
        assert item["status"] == expected, today
        view = await _view(client, learner, course.id)
        assert view["status"] == expected, today
        assert (view["survey"] is not None) == (expected == "open"), today
        assert [i["id"] for i in await _listed(client, admin, status=expected)] == [
            survey["id"]
        ], today


async def test_survey_close_reopen_patch(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    x, _ = await approved(db_session, settings, email="x@example.com")
    course, code = await open_test_course(db_session, title="가 강의")
    await _assign_to(client, admin, course.id, x)
    await _learner(client, code.code, "kim@example.com")
    (survey,) = await _deployed(client, admin, [course.id], tid)  # 11-03 ~ 11-19
    sid = survey["id"]

    closed = _ok(await client.post(f"{SURVEYS}/{sid}:close", headers=admin))
    assert set(closed) == SURVEY_KEYS
    assert (closed["status"], closed["close_on"], closed["current"]) == (
        "closed",
        "2026-11-19",
        True,
    )
    assert closed["closed_at"] is not None
    assert [(a[0], a[1]) for a in await _audits(db_session, "survey.close")] == [
        ("survey", str(sid))
    ]
    # 닫힘 알림은 배정 강사에게만(수강생 아님)
    assert await _outbox(db_session, "survey_closed") == {
        "x@example.com": [
            {"survey_id": sid, "course_title": "가 강의", "closed_on": "2026-11-03"}
        ]
    }
    problem_of(
        await client.post(f"{SURVEYS}/{sid}:close", headers=admin),
        409,
        "/problems/conflict",
    )

    # 다시 열기: 닫힘일은 max(닫힘일, 오늘 + 7) — 여기선 11-19 그대로
    reopened = _ok(await client.post(f"{SURVEYS}/{sid}:reopen", headers=admin))
    assert (reopened["status"], reopened["close_on"], reopened["closed_at"]) == (
        "open",
        "2026-11-19",
        None,
    )
    assert reopened["reopened_at"] is not None
    problem_of(
        await client.post(f"{SURVEYS}/{sid}:reopen", headers=admin),
        409,
        "/problems/conflict",
    )
    assert len(await _audits(db_session, "survey.reopen")) == 1

    short, _ = await open_test_course(db_session, title="짧은 강의")
    (s2,) = await _deployed(
        client,
        admin,
        [short.id],
        tid,
        close={"mode": "date", "date": TODAY_RUNNING.isoformat()},
    )
    _ok(await client.post(f"{SURVEYS}/{s2['id']}:close", headers=admin))
    got = _ok(await client.post(f"{SURVEYS}/{s2['id']}:reopen", headers=admin))
    assert (got["status"], got["close_on"]) == ("open", "2026-11-10")  # 오늘 + 7

    # 열리기 전에 닫은 예약 설문을 다시 열면 열림일을 오늘로 당겨 바로 연다
    planned, _ = await open_test_course(db_session, title="예약 강의")
    (s3,) = await _deployed(
        client, admin, [planned.id], tid, open={"mode": "date", "date": "2026-11-10"}
    )
    assert s3["status"] == "scheduled"
    got = _ok(await client.post(f"{SURVEYS}/{s3['id']}:close", headers=admin))
    assert got["status"] == "closed"
    got = _ok(await client.post(f"{SURVEYS}/{s3['id']}:reopen", headers=admin))
    assert (got["status"], got["open_on"]) == ("open", "2026-11-03")

    # PATCH: 닫힘일 연장은 예약·열림일 때 · 열림일은 예약일 때만 · 같은 값은 audit 없음
    got = _ok(
        await client.patch(
            f"{SURVEYS}/{sid}", headers=admin, json={"close_on": "2026-11-26"}
        )
    )
    assert (got["status"], got["close_on"]) == ("open", "2026-11-26")
    _ok(
        await client.patch(
            f"{SURVEYS}/{sid}", headers=admin, json={"close_on": "2026-11-26"}
        )
    )
    updates = await _audits(db_session, "survey.update")
    assert [(u[1], u[2]["fields"]) for u in updates] == [(str(sid), ["close_on"])]
    problem_of(
        await client.patch(
            f"{SURVEYS}/{sid}", headers=admin, json={"open_on": "2026-11-04"}
        ),
        409,
        "/problems/conflict",
    )
    later, _ = await open_test_course(db_session, title="뒤 강의")
    (s4,) = await _deployed(
        client, admin, [later.id], tid, open={"mode": "date", "date": "2026-11-10"}
    )
    got = _ok(
        await client.patch(
            f"{SURVEYS}/{s4['id']}", headers=admin, json={"open_on": "2026-11-12"}
        )
    )
    assert (got["status"], got["open_on"]) == ("scheduled", "2026-11-12")
    # 열림일만 저장된 닫힘일(11-19) 뒤로 — 오류 위치는 보낸 칸 open_on(리뷰 Nit)
    body = problem_of(
        await client.patch(
            f"{SURVEYS}/{s4['id']}", headers=admin, json={"open_on": "2026-11-25"}
        ),
        422,
    )
    assert [(v["loc"], v["type"]) for v in body["violations"]] == [
        (["body", "open_on"], "close_before_open")
    ]
    for empty in ({}, {"close_on": None}, {"current": False}):
        problem_of(
            await client.patch(f"{SURVEYS}/{sid}", headers=admin, json=empty), 422
        )

    # 밀려난 설문은 PATCH·다시 열기·닫기 전부 409
    _ok(await client.post(f"{SURVEYS}/{sid}:close", headers=admin))
    await _deployed(client, admin, [course.id], tid)
    for method, path, body in (
        ("PATCH", f"{SURVEYS}/{sid}", {"close_on": "2026-12-01"}),
        ("POST", f"{SURVEYS}/{sid}:reopen", None),
        ("POST", f"{SURVEYS}/{sid}:close", None),
    ):
        problem_of(
            await client.request(method, path, headers=admin, json=body),
            409,
            "/problems/conflict",
        )

    # 열린 설문의 닫힘일을 오늘보다 앞(열림일 이상)으로 PATCH → 422 · 행 그대로(리뷰 Nit)
    set_today(app, date(2026, 11, 5))
    body = problem_of(
        await client.patch(
            f"{SURVEYS}/{s2['id']}", headers=admin, json={"close_on": "2026-11-04"}
        ),
        422,
    )
    assert [(v["loc"], v["type"]) for v in body["violations"]] == [
        (["body", "close_on"], "close_before_today")
    ]
    (item,) = await _listed(client, admin, course_id=short.id)
    assert (item["status"], item["open_on"], item["close_on"]) == (
        "open",
        "2026-11-03",
        "2026-11-10",
    )


async def test_survey_questions_locked_after_response(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    learner = await _learner(client, code.code, "kim@example.com")
    (survey,) = await _deployed(client, admin, [course.id], tid)
    sid = survey["id"]

    # 응답 0건이면 문항을 고칠 수 있다(배포본만 — 양식은 그대로)
    got = _ok(
        await client.patch(
            f"{SURVEYS}/{sid}", headers=admin, json={"questions": OWN_QUESTIONS}
        )
    )
    assert (got["locked"], got["responses"]) == (False, 0)
    view = await _view(client, learner, course.id)
    assert [q["key"] for q in view["survey"]["questions"]] == ["q1", "q2"]
    seed = _ok(await client.get(f"{ADMIN}/survey-templates/{tid}", headers=admin))
    assert len(seed["questions"]) == 24

    r = await _submit(client, learner, course.id, {"q1": 4})
    assert r.status_code == 201, r.text
    (item,) = await _listed(client, admin, course_id=course.id)
    assert (item["locked"], item["responses"]) == (True, 1)

    # 응답 1건 뒤에는 문항이 잠긴다 — 409, 문항·해시 그대로
    body = problem_of(
        await client.patch(
            f"{SURVEYS}/{sid}",
            headers=admin,
            json={"questions": [{**OWN_QUESTIONS[0], "text": "바꿈"}]},
        ),
        409,
        "/problems/conflict",
    )
    assert body["status"] == 409
    after = await _view(client, learner, course.id)
    assert after["survey"] == view["survey"]
    # 닫힘일 연장은 응답이 있어도 된다
    _ok(
        await client.patch(
            f"{SURVEYS}/{sid}", headers=admin, json={"close_on": "2026-11-27"}
        )
    )

    # 교차 규칙은 422(잠기지 않은 설문)
    other, _ = await open_test_course(db_session, title="다른 강의")
    (s2,) = await _deployed(client, admin, [other.id], tid)
    twice = [
        {**OWN_QUESTIONS[0]},
        {**OWN_QUESTIONS[0], "key": "q3"},
    ]  # is_overall 둘
    body = problem_of(
        await client.patch(
            f"{SURVEYS}/{s2['id']}", headers=admin, json={"questions": twice}
        ),
        422,
    )
    assert all(v[:2] == ["body", "questions"] for v in locs(body)), locs(body)
    (item,) = await _listed(client, admin, course_id=other.id)
    assert item["locked"] is False


async def test_survey_admin_list_filters(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    a, _ = await open_test_course(db_session, title="가")
    b, _ = await open_test_course(db_session, title="나")
    c, _ = await open_test_course(db_session, title="다")
    (sa,) = await _deployed(client, admin, [a.id], tid)
    (sb,) = await _deployed(
        client, admin, [b.id], tid, open={"mode": "date", "date": "2026-11-10"}
    )
    (sc,) = await _deployed(client, admin, [c.id], tid)
    _ok(await client.post(f"{SURVEYS}/{sc['id']}:close", headers=admin))

    body = _ok(await client.get(SURVEYS, headers=admin))
    assert set(body) == PAGE_KEYS
    assert (body["has_more"], body["next_cursor"]) == (False, None)
    for item in body["items"]:
        assert set(item) == SURVEY_KEYS, item
    # (created_at, id) 내림차순
    assert [i["id"] for i in body["items"]] == [sc["id"], sb["id"], sa["id"]]
    assert [i["id"] for i in await _listed(client, admin, course_id=a.id)] == [sa["id"]]
    for status, expected in (("open", sa), ("scheduled", sb), ("closed", sc)):
        assert [i["id"] for i in await _listed(client, admin, status=status)] == [
            expected["id"]
        ], status
    assert await _listed(client, admin, course_id=b.id, status="open") == []

    seen: list[int] = []
    cursor = None
    for _ in range(3):
        params: dict[str, Any] = {"limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        page = _ok(await client.get(SURVEYS, headers=admin, params=params))
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
    assert seen == [sc["id"], sb["id"], sa["id"]]  # 쪽이 겹치지 않는다
    assert cursor is None

    bad = problem_of(
        await client.get(SURVEYS, headers=admin, params={"cursor": "깨진커서"}), 422
    )
    assert locs(bad) == [["query", "cursor"]]
    for params in (
        {"status": "reopened"},
        {"course_id": 0},
        {"course_id": OVERFLOW},
        {"limit": 101},
    ):
        problem_of(await client.get(SURVEYS, headers=admin, params=params), 422)
    _, x_auth = await approved(db_session, settings, email="x@example.com")
    problem_of(await client.get(SURVEYS, headers=x_auth), 403, "/problems/forbidden")


async def test_survey_admin_validation_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, _ = await open_test_course(db_session)
    cid = course.id
    many = list(range(cid, cid + 51))
    cases: list[tuple[dict[str, Any], list[Any]]] = [
        ({"course_ids": []}, ["body", "course_ids"]),
        ({"course_ids": many}, ["body", "course_ids"]),
        ({"course_ids": [OVERFLOW]}, ["body", "course_ids", 0]),
        ({"course_ids": [0]}, ["body", "course_ids", 0]),
        ({"template_id": OVERFLOW}, ["body", "template_id"]),
        ({"open": {"mode": "date"}}, ["body", "open"]),
        ({"open": {"mode": "now", "date": "2026-11-04"}}, ["body", "open"]),
        ({"open": {"mode": "later"}}, ["body", "open", "mode"]),
        ({"close": {"mode": "date"}}, ["body", "close"]),
        ({"close": {"mode": "end_plus_30"}}, ["body", "close", "mode"]),
        ({"foo": 1}, ["body", "foo"]),
    ]
    for over, loc in cases:
        body = {"course_ids": [cid], "template_id": tid, **over}
        problem = problem_of(await client.post(SURVEYS, headers=admin, json=body), 422)
        assert all(v[: len(loc)] == loc for v in locs(problem)), (over, locs(problem))
    # 강의마다 푼 날짜 판정(오늘 이상 · 열림일 이상 · 날짜 범위 넘침)도 422 이고 그 강의 id 가 msg 에 있다.
    # loc 은 그 쪽이 지정일 모드면 date 칸, 아니면 모드 객체(넘침은 500 이 아니다 — codex 1차)
    last = {"mode": "date", "date": "9999-12-31"}
    for modes, expected in (
        (
            {"open": {"mode": "date", "date": "2026-11-02"}},
            (["body", "open", "date"], "open_before_today"),
        ),
        (
            {
                "open": {"mode": "date", "date": "2026-11-10"},
                "close": {"mode": "date", "date": "2026-11-09"},
            },
            (["body", "close", "date"], "close_before_open"),
        ),
        (
            {"open": last, "close": {"mode": "open_plus_7"}},
            (["body", "close"], "close_out_of_range"),
        ),
        ({"open": last}, (["body", "close"], "close_out_of_range")),  # end_plus_14 → 열림 + 7
    ):
        problem = problem_of(await _deploy(client, admin, [cid], tid, **modes), 422)
        assert [(v["loc"], v["type"]) for v in problem["violations"]] == [expected], (
            modes,
            problem,
        )
        assert str(cid) in problem["violations"][0]["msg"], problem
    problem_of(await _deploy(client, admin, [cid], LARGEST), 404, "/problems/not_found")
    problem_of(await _deploy(client, admin, [LARGEST], tid), 404, "/problems/not_found")
    assert await count(db_session, Survey) == 0

    for method, path in (
        ("PATCH", f"{SURVEYS}/{{id}}"),
        ("POST", f"{SURVEYS}/{{id}}:close"),
        ("POST", f"{SURVEYS}/{{id}}:reopen"),
        ("GET", f"{SURVEYS}/{{id}}/results"),
    ):
        body = {"close_on": "2026-11-30"} if method == "PATCH" else None
        problem_of(
            await client.request(
                method, path.format(id=LARGEST), headers=admin, json=body
            ),
            404,
            "/problems/not_found",
        )
        problem = problem_of(
            await client.request(
                method, path.format(id=OVERFLOW), headers=admin, json=body
            ),
            422,
        )
        assert locs(problem) == [["path", "survey_id"]], (method, path)


def _scale(stat: ScaleStat | None) -> dict[str, Any] | None:
    """단위 집계를 응답 모양으로(값 대조용)."""
    if stat is None:
        return None
    return {
        "n": stat.n,
        "avg": None if stat.avg is None else float(stat.avg),
        "hundred": stat.hundred,
        "positive_pct": stat.positive_pct,
        "distribution": {str(k): v for k, v in stat.distribution.items()},
    }


async def test_no_personal_keys_a5(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    tid = await _default_id(client, admin)
    course, code = await open_test_course(db_session)
    people = (
        ("kim@example.com", "김가명", "교육팀"),
        ("lee@example.com", "이가명", "인사팀"),
        ("park@example.com", "박가명", None),
    )
    learners = []
    for email, name, dept in people:
        extra = {} if dept is None else {"dept": dept}
        learners.append(await _learner(client, code.code, email, name, **extra))
    (survey,) = await _deployed(client, admin, [course.id], tid)
    questions = (await _view(client, learners[0], course.id))["survey"]["questions"]
    answers = [
        {
            **ANSWERS_OK,
            "b01": 5,
            "overall": 5,
            "c1": "보안 마스킹 기준",
            "dept": "직접 쓴 부서",
        },
        {**ANSWERS_OK, "b01": 5, "overall": 4, "c1": "가상 실습을 더"},
        {**ANSWERS_OK, "b01": 4, "overall": 4, "c1": "  "},  # 빈 주관식은 결측
    ]
    for headers, given in zip(learners, answers, strict=True):
        r = await _submit(client, headers, course.id, given)
        assert r.status_code == 201, r.text

    r = await client.get(f"{SURVEYS}/{survey['id']}/results", headers=admin)
    body = _ok(r)
    keys = json_keys(body)
    assert keys == RESULTS_KEYS
    assert keys & RESULT_FORBIDDEN_KEYS == set()
    assert keys & PERSONAL_KEYS == set()
    assert set(body) == RESULTS_TOP_KEYS
    assert set(body["head"]) == HEAD_KEYS
    assert {"created_at", "closed_at"} & set(body["head"]) == set()
    assert (body["head"]["survey_id"], body["head"]["status"]) == (survey["id"], "open")
    assert body["response_rate"] == {"responses": 3, "total": 3, "percent": 100}
    for secret in ("김가명", "이가명", "kim@example.com", "lee@example.com"):
        assert secret not in r.text, secret

    # 값은 단위 집계(rules.survey_stats.aggregate) 와 같다 — 산식은 한 곳
    unit = aggregate(questions, [normalize_answers(questions, a) for a in answers])
    assert body["overall"] == _scale(unit.overall)
    stats = {q["key"]: q["stat"] for q in body["questions"]}
    for key in ("b01", "b12", "overall"):
        expected = unit.questions[key]
        assert isinstance(expected, ScaleStat)
        assert stats[key] == _scale(expected), key
    # 고정값: b01 = 5·5·4 → 평균 4.67 · 100점 환산 평균 × 20 = 93 · 긍정률 100
    assert (
        stats["b01"]["avg"],
        stats["b01"]["hundred"],
        stats["b01"]["positive_pct"],
    ) == (
        4.67,
        93,
        100,
    )
    assert body["overall"]["n"] == 3
    assert [a["area"] for a in body["areas"]] == [a.area for a in unit.areas]
    dept = stats["dept"]
    assert dept["n"] == 3
    assert {"value": "직접 쓴 부서", "count": 1} in dept["values"]
    (c1,) = [t for t in body["texts"] if t["key"] == "c1"]
    assert c1["items"] == ["가상 실습을 더", "보안 마스킹 기준"]  # 글자 순, 빈 값 없음

    # 응답 0건이면 척도 지표는 null(0점처럼 보이지 않게)
    empty, _ = await open_test_course(db_session, title="빈 강의")
    (s2,) = await _deployed(client, admin, [empty.id], tid)
    body = _ok(await client.get(f"{SURVEYS}/{s2['id']}/results", headers=admin))
    assert body["overall"] is None
    assert body["response_rate"] == {"responses": 0, "total": 0, "percent": None}
    assert json_keys(body) & RESULT_FORBIDDEN_KEYS == set()
