"""관리자 경로는 전부 AdminCaller 다: 수강생·강사 토큰 403, 토큰 없음 401 + WWW-Authenticate: Bearer.

새 앱(create_app, probe 없음)의 OpenAPI 에서 /v1/admin/ 경로·메서드를 전부 뽑아 돈다. 경로 변수는 1, 본문은 없다.
권한 의존성은 본문 검증보다 먼저 풀리므로 본문이 없어도 403·401 이 먼저 나온다. 끝점을 더하면 자동으로 들어온다.
구조 시험은 ROUTERS 의 APIRoute 의존성 트리를 본다(T11 결정 vi): 관리자 경로에만 require_admin 이 있고, 스키마에서 숨지
않으며, 최상위 의존성에서 require_admin 앞에는 db 와 응답 헤더 전용 no_store 만 온다 — 허용 목록은 함수 객체로 비교한다
(이름 글자만 보면 다른 모듈의 db·no_store 가 인증 앞에 끼어도 지나간다).
"""

import re
from collections.abc import Callable, Iterator
from typing import Any

import httpx
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

import classfit.app.deps
from classfit.app.deps import require_admin
from classfit.app.routers import ROUTERS
from classfit.core.config import Settings
from classfit.main import create_app
from tests.fixtures.courses import learner_headers, open_test_course
from tests.fixtures.instructors import instructor_headers

METHODS = {"get", "post", "put", "patch", "delete"}
ADMIN_OPERATIONS_AT_LEAST = (
    92  # 1차 끝(T10)의 관리자 연산 수 — 빈 목록을 돌아 통과하지 않게
)
ADMIN_PREFIX = "/v1/admin"


def _admin_operations() -> list[tuple[str, str]]:
    spec = create_app(Settings()).openapi()
    return sorted(
        (method.upper(), re.sub(r"\{[^}]+\}", "1", path))
        for path, item in spec["paths"].items()
        if path.startswith("/v1/admin/")
        for method in item
        if method in METHODS
    )


async def test_admin_paths_learner_403_and_no_token_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operations = _admin_operations()
    assert len(operations) >= ADMIN_OPERATIONS_AT_LEAST, operations
    course, _ = await open_test_course(db_session)
    learner = await learner_headers(db_session, course.id)
    wrong = []
    for method, path in operations:
        as_learner = await client.request(method, path, headers=learner)
        anonymous = await client.request(method, path)
        if (
            as_learner.status_code != 403
            or anonymous.status_code != 401
            or anonymous.headers.get("www-authenticate") != "Bearer"
        ):
            wrong.append((method, path, as_learner.status_code, anonymous.status_code))
    assert wrong == []


async def test_admin_paths_instructor_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operations = _admin_operations()
    assert len(operations) >= ADMIN_OPERATIONS_AT_LEAST, operations
    instructor = await instructor_headers(db_session, 1)
    wrong = []
    for method, path in operations:
        r = await client.request(method, path, headers=instructor)
        if (
            r.status_code != 403
            or not r.headers["content-type"].startswith("application/problem+json")
            or r.json().get("type") != "/problems/forbidden"
        ):
            wrong.append((method, path, r.status_code))
    assert wrong == []


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any] | None]:
    """의존성 트리의 함수 전부(깊이 우선)."""
    for sub in dependant.dependencies:
        yield sub.call
        yield from _calls(sub)


def _requires_admin(dependant: Dependant) -> bool:
    return dependant.call is require_admin or require_admin in _calls(dependant)


def test_admin_routes_require_admin_structure() -> None:
    # worker-a 의 no_store(결정 ii)가 없으면 None 이라 허용 목록에서 빠질 뿐 시험은 돈다
    allowed = {classfit.app.deps.db, getattr(classfit.app.deps, "no_store", None)}
    allowed.discard(None)
    routes = [r for router in ROUTERS for r in router.routes if isinstance(r, APIRoute)]
    admin_operations = 0
    wrong: list[tuple[str, str]] = []
    for route in routes:
        is_admin = route.path == ADMIN_PREFIX or route.path.startswith(
            ADMIN_PREFIX + "/"
        )
        if not is_admin:
            if _requires_admin(route.dependant):  # ② 관리자 경로 밖에는 없다
                wrong.append((route.path, "밖인데 require_admin"))
            continue
        admin_operations += len(route.methods)
        if not route.include_in_schema:  # ③ OpenAPI 루프에서 빠지지 않는다
            wrong.append((route.path, "include_in_schema=False"))
        top = route.dependant.dependencies
        guarded = [i for i, sub in enumerate(top) if _requires_admin(sub)]
        if not guarded:  # ① 의존성 트리에 require_admin
            wrong.append((route.path, "require_admin 없음"))
            continue
        before = [sub.call for sub in top[: guarded[0]]]
        if not all(call in allowed for call in before):  # ④ 그 앞에는 db·no_store 만
            names = [getattr(call, "__qualname__", repr(call)) for call in before]
            wrong.append((route.path, f"require_admin 앞에 {names}"))
    assert admin_operations >= ADMIN_OPERATIONS_AT_LEAST, admin_operations
    assert wrong == []
