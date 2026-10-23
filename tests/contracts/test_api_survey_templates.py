"""설문 양식: 목록·만들기·고치기 · 기본 지정·삭제 · 복제 · 모양 422 · 원본 수정·삭제 뒤 배포 설문 유지
(T8 계획 결정 v·viii·xviii·xxv·xxvi · 증명 15·16·30).

응답은 허용 키 집합을 정확히 잰다. 문항은 늘 아홉 키다(빠진 칸은 기본값). 0009 가 기본 양식("기본 양식", 24문항) 1행을
시드한다. 배포는 관리자 API 로 하고, 픽스처 강의는 2026-11-02(월)부터 평일 4일이다.
"""

from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import AuditLog, SurveyTemplate
from tests.fixtures.courses import admin_headers, open_test_course
from tests.fixtures.enter import bearer, enter_learner
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.records import set_today
from tests.fixtures.surveys import QUESTION_KEYS, TEMPLATE_KEYS, TODAY_RUNNING

ADMIN = "/v1/admin"
TEMPLATES = f"{ADMIN}/survey-templates"
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422
QUESTIONS: list[dict[str, Any]] = [
    {
        "key": "q1",
        "type": "scale",
        "text": " 강의에 만족하셨습니까? ",
        "area": "종합",
        "star": True,
        "is_overall": True,
    },
    {
        "key": "q2",
        "type": "single",
        "text": "참여 형태",
        "options": ["전체 참여", "부분 참여"],
        "required": False,
        "custom": True,
    },
    {"key": "q3", "type": "text", "text": "바라는 점", "required": False},
]
# 저장·응답은 아홉 키로 정규화된다(앞뒤 공백도 지운다)
NORMALIZED: list[dict[str, Any]] = [
    {
        "key": "q1",
        "type": "scale",
        "text": "강의에 만족하셨습니까?",
        "area": "종합",
        "required": True,
        "star": True,
        "is_overall": True,
        "options": None,
        "custom": False,
    },
    {
        "key": "q2",
        "type": "single",
        "text": "참여 형태",
        "area": None,
        "required": False,
        "star": False,
        "is_overall": False,
        "options": ["전체 참여", "부분 참여"],
        "custom": True,
    },
    {
        "key": "q3",
        "type": "text",
        "text": "바라는 점",
        "area": None,
        "required": False,
        "star": False,
        "is_overall": False,
        "options": None,
        "custom": False,
    },
]
TEMPLATE_ACTIONS = (
    "survey_template.create",
    "survey_template.update",
    "survey_template.delete",
    "survey_template.set_default",
    "survey_template.duplicate",
)


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _audits(session: AsyncSession, action: str) -> list[tuple[Any, ...]]:
    """그 action 의 (actor, target_type, target_id, detail), id 순."""
    rows = await session.execute(
        select(
            AuditLog.actor, AuditLog.target_type, AuditLog.target_id, AuditLog.detail
        )
        .where(AuditLog.action == action)
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _create(
    client: httpx.AsyncClient, admin: dict[str, str], name: str, **over: Any
) -> dict[str, Any]:
    body: dict[str, Any] = _ok(
        await client.post(
            TEMPLATES,
            headers=admin,
            json={"name": name, "questions": QUESTIONS, **over},
        ),
        201,
    )
    return body


async def _items(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = _ok(await client.get(TEMPLATES, headers=admin))[
        "items"
    ]
    return items


async def _defaults(client: httpx.AsyncClient, admin: dict[str, str]) -> list[int]:
    return [t["id"] for t in await _items(client, admin) if t["is_default"]]


async def _deploy(
    client: httpx.AsyncClient, admin: dict[str, str], course_id: int, template_id: int
) -> dict[str, Any]:
    body = _ok(
        await client.post(
            f"{ADMIN}/surveys",
            headers=admin,
            json={"course_ids": [course_id], "template_id": template_id},
        ),
        201,
    )
    item: dict[str, Any] = body["items"][0]
    return item


async def test_survey_template_crud_keys(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    aid, admin = await admin_headers(db_session)
    body = _ok(await client.get(TEMPLATES, headers=admin))
    assert set(body) == {"items"}
    assert [(t["name"], t["is_default"], t["deployed"]) for t in body["items"]] == [
        ("기본 양식", True, 0)
    ]
    seed = body["items"][0]
    assert set(seed) == TEMPLATE_KEYS
    assert len(seed["questions"]) == 24
    for q in seed["questions"]:
        assert set(q) == QUESTION_KEYS, q

    created = _ok(
        await client.post(
            TEMPLATES,
            headers=admin,
            json={"name": " 사업주훈련용 ", "note": "A사 요청", "questions": QUESTIONS},
        ),
        201,
    )
    assert set(created) == TEMPLATE_KEYS
    assert (
        created["name"],
        created["note"],
        created["is_default"],
        created["deployed"],
    ) == ("사업주훈련용", "A사 요청", False, 0)
    assert created["questions"] == NORMALIZED
    tid = created["id"]
    assert _ok(await client.get(f"{TEMPLATES}/{tid}", headers=admin)) == created
    assert {t["id"] for t in await _items(client, admin)} == {seed["id"], tid}
    assert [a[:3] for a in await _audits(db_session, "survey_template.create")] == [
        (f"admin:{aid}", "survey_template", str(tid))
    ]

    patched = _ok(
        await client.patch(
            f"{TEMPLATES}/{tid}", headers=admin, json={"name": "새 이름"}
        )
    )
    assert set(patched) == TEMPLATE_KEYS
    assert (patched["name"], patched["note"], patched["questions"]) == (
        "새 이름",
        "A사 요청",
        NORMALIZED,
    )
    # 같은 값은 바뀐 칸이 아니다 — 200 · audit 없음
    _ok(
        await client.patch(
            f"{TEMPLATES}/{tid}", headers=admin, json={"name": "새 이름"}
        )
    )
    _ok(await client.patch(f"{TEMPLATES}/{tid}", headers=admin, json={}))
    updates = await _audits(db_session, "survey_template.update")
    assert [u[:3] for u in updates] == [(f"admin:{aid}", "survey_template", str(tid))]
    assert updates[0][3]["fields"] == ["name"]
    cleared = _ok(
        await client.patch(f"{TEMPLATES}/{tid}", headers=admin, json={"note": None})
    )
    assert cleared["note"] is None

    body = problem_of(
        await client.patch(f"{TEMPLATES}/{tid}", headers=admin, json={"name": None}),
        422,
    )
    assert locs(body) == [["body"]]
    problem_of(
        await client.patch(
            f"{TEMPLATES}/{LARGEST}", headers=admin, json={"name": "없음"}
        ),
        404,
        "/problems/not_found",
    )
    problem_of(
        await client.get(f"{TEMPLATES}/{LARGEST}", headers=admin),
        404,
        "/problems/not_found",
    )


async def test_survey_template_default_and_delete(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    (seed_id,) = await _defaults(client, admin)
    problem_of(
        await client.delete(f"{TEMPLATES}/{seed_id}", headers=admin),
        409,
        "/problems/conflict",
    )
    assert await count(db_session, SurveyTemplate) == 1

    first = await _create(client, admin, "양식 1")
    out = _ok(
        await client.post(f"{TEMPLATES}/{first['id']}:set-default", headers=admin)
    )
    assert set(out) == TEMPLATE_KEYS
    assert (out["id"], out["is_default"]) == (first["id"], True)
    assert await _defaults(client, admin) == [first["id"]]
    # 이미 기본이면 그대로 200(멱등) · audit 은 처음 한 번
    again = _ok(
        await client.post(f"{TEMPLATES}/{first['id']}:set-default", headers=admin)
    )
    assert again["is_default"] is True
    assert await _defaults(client, admin) == [first["id"]]
    assert len(await _audits(db_session, "survey_template.set_default")) == 1

    r = await client.delete(f"{TEMPLATES}/{seed_id}", headers=admin)
    assert (r.status_code, r.content) == (204, b""), r.text
    problem_of(
        await client.get(f"{TEMPLATES}/{seed_id}", headers=admin),
        404,
        "/problems/not_found",
    )

    # 배포된 양식을 지우면 배포 설문의 template_id 만 끊기고 이름 스냅샷은 남는다
    course, _ = await open_test_course(db_session)
    survey = await _deploy(client, admin, course.id, first["id"])
    assert (
        _ok(await client.get(f"{TEMPLATES}/{first['id']}", headers=admin))["deployed"]
        == 1
    )
    problem_of(
        await client.delete(f"{TEMPLATES}/{first['id']}", headers=admin),
        409,
        "/problems/conflict",
    )  # 아직 기본
    second = await _create(client, admin, "양식 2")
    _ok(await client.post(f"{TEMPLATES}/{second['id']}:set-default", headers=admin))
    assert await _defaults(client, admin) == [second["id"]]
    r = await client.delete(f"{TEMPLATES}/{first['id']}", headers=admin)
    assert r.status_code == 204, r.text
    listed = _ok(
        await client.get(
            f"{ADMIN}/surveys", headers=admin, params={"course_id": course.id}
        )
    )["items"]
    assert [(i["id"], i["template_id"], i["template_name"]) for i in listed] == [
        (survey["id"], None, "양식 1")
    ]
    deletes = await _audits(db_session, "survey_template.delete")
    assert [d[2] for d in deletes] == [str(seed_id), str(first["id"])]

    for method, path in (
        ("DELETE", f"{TEMPLATES}/{LARGEST}"),
        ("POST", f"{TEMPLATES}/{LARGEST}:set-default"),
    ):
        problem_of(
            await client.request(method, path, headers=admin),
            404,
            "/problems/not_found",
        )
    for method, path in (
        ("GET", f"{TEMPLATES}/{OVERFLOW}"),
        ("DELETE", f"{TEMPLATES}/{OVERFLOW}"),
        ("POST", f"{TEMPLATES}/{OVERFLOW}:set-default"),
        ("POST", f"{TEMPLATES}/{OVERFLOW}:duplicate"),
    ):
        body = problem_of(await client.request(method, path, headers=admin), 422)
        assert locs(body) == [["path", "template_id"]], (method, path)
    assert await _defaults(client, admin) == [second["id"]]


async def test_survey_template_duplicate(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    (seed_id,) = await _defaults(client, admin)
    seed = _ok(await client.get(f"{TEMPLATES}/{seed_id}", headers=admin))

    copy = _ok(
        await client.post(f"{TEMPLATES}/{seed_id}:duplicate", headers=admin), 201
    )
    assert set(copy) == TEMPLATE_KEYS
    assert copy["id"] != seed_id
    assert (
        copy["name"],
        copy["note"],
        copy["is_default"],
        copy["deployed"],
        copy["questions"],
    ) == ("기본 양식 (복제)", seed["note"], False, 0, seed["questions"])

    long = await _create(client, admin, "가" * 100)
    copy = _ok(
        await client.post(f"{TEMPLATES}/{long['id']}:duplicate", headers=admin), 201
    )
    assert copy["name"] == "가" * 95 + " (복제)"  # 이름 CHECK 100자 안
    assert len(copy["name"]) == 100
    assert (copy["is_default"], copy["questions"]) == (False, NORMALIZED)
    assert await _defaults(client, admin) == [seed_id]
    assert len(await _audits(db_session, "survey_template.duplicate")) == 2
    problem_of(
        await client.post(f"{TEMPLATES}/{LARGEST}:duplicate", headers=admin),
        404,
        "/problems/not_found",
    )


def _question(**over: Any) -> dict[str, Any]:
    return {"key": "q1", "type": "scale", "text": "만족도", **over}


async def test_survey_template_validation_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, admin = await admin_headers(db_session)
    choice = {"type": "single", "options": ["가", "나"]}
    cases: list[tuple[dict[str, Any], list[Any]]] = [
        ({"questions": [_question(key="1q")]}, ["body", "questions", 0, "key"]),
        ({"questions": [_question(key="Q1")]}, ["body", "questions", 0, "key"]),
        ({"questions": [_question(type="long")]}, ["body", "questions", 0, "type"]),
        ({"questions": [_question(text=" ")]}, ["body", "questions", 0, "text"]),
        ({"questions": [_question(text="가" * 301)]}, ["body", "questions", 0, "text"]),
        (
            {"questions": [_question(**{**choice, "options": ["가"]})]},
            ["body", "questions", 0, "options"],
        ),
        (
            {
                "questions": [
                    _question(**{**choice, "options": [str(n) for n in range(31)]})
                ]
            },
            ["body", "questions", 0, "options"],
        ),
        (
            {"questions": [_question(**{**choice, "options": ["가", "가"]})]},
            ["body", "questions", 0, "options"],
        ),
        ({"questions": [_question(foo=1)]}, ["body", "questions", 0, "foo"]),
        ({"questions": []}, ["body", "questions"]),
        (
            {"questions": [_question(key=f"q{n}") for n in range(61)]},
            ["body", "questions"],
        ),
        ({"name": "가" * 101}, ["body", "name"]),
        ({"name": "   "}, ["body", "name"]),
        ({"foo": 1}, ["body", "foo"]),
    ]
    for over, loc in cases:
        body = {"name": "검증", "questions": [_question()], **over}
        problem = problem_of(
            await client.post(TEMPLATES, headers=admin, json=body), 422
        )
        assert locs(problem), (over, problem)
        assert all(v[: len(loc)] == loc for v in locs(problem)), (over, locs(problem))
        if loc[-1] == "foo":
            assert [v["type"] for v in problem["violations"]] == ["extra_forbidden"]
    # 교차 규칙 — service 가 rules.survey.question_errors 로 재고 loc 은 ["body", "questions", 차례, 칸]
    info = {"key": "info", "type": "info", "text": "안내", "required": False}
    cross: list[tuple[list[dict[str, Any]], list[tuple[list[Any], str]]]] = [
        ([_question(), _question()], [(["body", "questions", 1, "key"], "duplicate")]),
        (
            [_question(), {"key": "q2", "type": "text", "text": "의견", "star": True}],
            [(["body", "questions", 1, "star"], "scale_only")],
        ),
        (
            [_question(is_overall=True), _question(key="q2", is_overall=True)],
            [(["body", "questions", 1, "is_overall"], "many")],
        ),
        (
            [_question(), _question(key="q2", **choice, is_overall=True)],
            [(["body", "questions", 1, "is_overall"], "scale_only")],
        ),
        (
            [_question(options=["가", "나"])],
            [(["body", "questions", 0, "options"], "choice_only")],
        ),
        (
            [_question(custom=True)],
            [(["body", "questions", 0, "custom"], "choice_only")],
        ),
        ([info], [(["body", "questions"], "no_answer_question")]),
        (
            [_question(), {**info, "required": True}],
            [(["body", "questions", 1, "required"], "info")],
        ),
    ]
    for questions, expected in cross:
        problem = problem_of(
            await client.post(
                TEMPLATES, headers=admin, json={"name": "검증", "questions": questions}
            ),
            422,
        )
        assert [(v["loc"], v["type"]) for v in problem["violations"]] == expected, (
            questions,
            problem["violations"],
        )
    assert await count(db_session, SurveyTemplate) == 1  # 시드만

    # 고치기도 같은 규칙이고 행은 그대로다
    (seed_id,) = await _defaults(client, admin)
    before = _ok(await client.get(f"{TEMPLATES}/{seed_id}", headers=admin))
    for patch in (
        {"questions": [_question(), _question()]},
        {"questions": []},
        {"name": ""},
        {"is_default": False},
    ):
        problem_of(
            await client.patch(f"{TEMPLATES}/{seed_id}", headers=admin, json=patch), 422
        )
    assert _ok(await client.get(f"{TEMPLATES}/{seed_id}", headers=admin)) == before
    assert await count(db_session, AuditLog, AuditLog.action.in_(TEMPLATE_ACTIONS)) == 0


async def test_survey_template_delete_keeps_deployed(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY_RUNNING)
    _, admin = await admin_headers(db_session)
    template = await _create(client, admin, "사업주훈련용")
    course, code = await open_test_course(db_session)
    survey = await _deploy(client, admin, course.id, template["id"])
    r = await enter_learner(client, code.code, "kim@example.com", "김가명")
    assert r.status_code == 201, r.text
    learner = bearer(r.json()["access_token"])
    url = f"/v1/learner/courses/{course.id}/survey"
    seen = _ok(await client.get(url, headers=learner))["survey"]
    assert (seen["id"], seen["questions"]) == (survey["id"], NORMALIZED)

    # 원본 양식을 고쳐도 배포본(복제본)은 그대로다 — 문항·해시 둘 다
    changed = [{**q, "text": q["text"] + " (수정)"} for q in NORMALIZED]
    patched = _ok(
        await client.patch(
            f"{TEMPLATES}/{template['id']}", headers=admin, json={"questions": changed}
        )
    )
    assert patched["questions"] == changed
    after = _ok(await client.get(url, headers=learner))["survey"]
    assert (after["questions"], after["questions_hash"]) == (
        seen["questions"],
        seen["questions_hash"],
    )

    r = await client.delete(f"{TEMPLATES}/{template['id']}", headers=admin)
    assert r.status_code == 204, r.text
    listed = _ok(
        await client.get(
            f"{ADMIN}/surveys", headers=admin, params={"course_id": course.id}
        )
    )["items"]
    assert [(i["template_id"], i["template_name"]) for i in listed] == [
        (None, "사업주훈련용")
    ]
    gone = _ok(await client.get(url, headers=learner))["survey"]
    assert (gone["questions"], gone["questions_hash"]) == (
        seen["questions"],
        seen["questions_hash"],
    )
    r = await client.post(
        f"{url}/responses",
        headers=learner,
        json={
            "survey_id": gone["id"],
            "questions_hash": gone["questions_hash"],
            "answers": {"q1": 5, "q3": "좋았습니다"},
        },
    )
    assert r.status_code == 201, r.text
    results = _ok(
        await client.get(f"{ADMIN}/surveys/{survey['id']}/results", headers=admin)
    )
    assert results["head"]["template_name"] == "사업주훈련용"
    assert results["response_rate"]["responses"] == 1
    assert [q["text"] for q in results["questions"]] == [q["text"] for q in NORMALIZED]
