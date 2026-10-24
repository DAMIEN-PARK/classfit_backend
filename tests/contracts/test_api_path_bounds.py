"""정수 경로 매개변수 상한(T11 결정 iv): 전부 app.deps 의 IdPath(1 ≤ id < 2**63) · DayPath(일차 1..60) 다.

새 앱(create_app, probe 없음)의 OpenAPI 를 정본으로 정수 경로 매개변수를 전부 뽑는다. 밖의 값은 자원 질의에 닿지 않고
422 loc ["path", <이름>] 다(BIGINT DataError 500 이 아니다). 인증 의존성은 경로 검증보다 먼저 풀리므로 경로 접두마다
그 주체의 토큰을 단다(/v1/admin 관리자 · /v1/me 강사 · /v1/learner 수강생). 끝점을 더하면 자동으로 들어온다.
"""

import re
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.main import create_app
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.instructors import instructor_headers, locs, problem_of

METHODS = {"get", "post", "put", "patch", "delete"}
DB_ID_LIMIT = 2**63
# T11 착수 때 정수 경로 매개변수 101개(연산 91) — 빈 목록을 돌아 통과하지 않게
INT_PATH_PARAMS_AT_LEAST = 101
# limited_json 의존성은 경로 검증보다 먼저 본문을 읽는다(415 · 본문 422 가 먼저) — 모양이 맞는 본문을 준다
LIMITED_JSON_BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/v1/learner/courses/{course_id}/survey/responses"): {
        "survey_id": 1,
        "questions_hash": "0" * 16,
        "answers": {"q1": 1},
    }
}


def _int_path_operations() -> list[tuple[str, str, dict[str, dict[str, Any]]]]:
    """(메서드, 경로 틀, {정수 경로 매개변수 이름: 스키마})."""
    spec = create_app(Settings()).openapi()
    found = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in METHODS:
                continue
            params = {
                p["name"]: p["schema"]
                for p in op.get("parameters", [])
                if p["in"] == "path" and p["schema"].get("type") == "integer"
            }
            if params:
                found.append((method.upper(), path, params))
    return sorted(found)


def _path_locs(r: httpx.Response) -> list[list[Any]]:
    if not r.headers.get("content-type", "").startswith("application/problem+json"):
        return []
    return sorted(loc for loc in locs(r.json()) if loc[0] == "path")


def _fill(path: str, values: dict[str, int]) -> str:
    """정수 매개변수는 values, 나머지(글자 id)는 x."""
    return re.sub(r"\{([^}]+)\}", lambda m: str(values.get(m.group(1), "x")), path)


async def _headers(session: AsyncSession) -> dict[str, dict[str, str]]:
    _, admin = await admin_headers(session)
    course, _ = await open_test_course(session)
    return {
        "/v1/admin/": admin,
        "/v1/me/": await instructor_headers(session, 1),
        "/v1/learner/": await learner_headers(session, course.id),
    }


def _caller(headers: dict[str, dict[str, str]], path: str) -> dict[str, str]:
    [prefix] = [p for p in headers if path.startswith(p)]
    return headers[prefix]


async def _send(
    client: httpx.AsyncClient,
    headers: dict[str, dict[str, str]],
    method: str,
    path: str,
    values: dict[str, int],
) -> httpx.Response:
    body = LIMITED_JSON_BODIES.get((method, path), {})
    return await client.request(
        method, _fill(path, values), headers=_caller(headers, path), json=body
    )


def test_path_id_bounds_openapi() -> None:
    operations = _int_path_operations()
    schemas = [(m, p, n, s) for m, p, params in operations for n, s in params.items()]
    assert len(schemas) >= INT_PATH_PARAMS_AT_LEAST, len(schemas)
    wrong = []
    for method, path, name, schema in schemas:
        if name == "day_no":
            bounded = schema.get("minimum") == 1 and schema.get("maximum") == 60
        else:
            bounded = (
                schema.get("minimum") == 1
                and schema.get("exclusiveMaximum") == DB_ID_LIMIT
            )
        if not bounded:
            wrong.append((method, path, name, schema))
    assert wrong == []


async def test_path_id_bounds_2_63_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """정수 경로 매개변수가 있는 연산 전부에 2**63(일차는 61) → 422, 정수 매개변수마다 loc ["path", <이름>]."""
    headers = await _headers(db_session)
    operations = _int_path_operations()
    assert {(m, p) for m, p, _ in operations} >= set(LIMITED_JSON_BODIES)
    wrong = []
    for method, path, params in operations:
        over = {n: 61 if n == "day_no" else DB_ID_LIMIT for n in params}
        r = await _send(client, headers, method, path, over)
        expected = sorted(["path", n] for n in params)
        if r.status_code != 422 or _path_locs(r) != expected:
            wrong.append((method, path, r.status_code, _path_locs(r)))
    assert wrong == []
    # 0 도 밖이다(ge=1). 상한 바로 아래(2**63 - 1)는 BIGINT 라 검증을 지나 권한·자원 판정까지 간다(500 아님)
    for method, path, name, status in (
        ("GET", "/v1/learner/courses/{course_id}/portal", "course_id", 403),
        ("GET", "/v1/admin/instructors/{instructor_id}", "instructor_id", 404),
        (
            "DELETE",
            "/v1/me/pool-files/{pool_course_file_id}",
            "pool_course_file_id",
            404,
        ),
    ):
        r = await _send(client, headers, method, path, {name: 0})
        assert locs(problem_of(r, 422)) == [["path", name]], path
        r = await _send(client, headers, method, path, {name: DB_ID_LIMIT - 1})
        problem_of(r, status)


async def test_path_day_bounds_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """day_no 를 받는 연산 전부: 0·61 → 422 loc ["path", "day_no"], 1·60 은 경로 검증을 지난다(없는 강의 404 · 본문 422)."""
    headers = await _headers(db_session)
    day_ops = [(m, p) for m, p, params in _int_path_operations() if "day_no" in params]
    assert len(day_ops) >= 5, day_ops  # schedule 둘 · records 셋
    wrong = []
    for method, path in day_ops:
        for day in (0, 61, 1, 60):
            values = {"course_id": DB_ID_LIMIT - 1, "day_no": day}
            r = await _send(client, headers, method, path, values)
            rejected = day in (0, 61)
            if (["path", "day_no"] in _path_locs(r)) != rejected or (
                rejected and r.status_code != 422
            ):
                wrong.append((method, path, day, r.status_code))
    assert wrong == []
