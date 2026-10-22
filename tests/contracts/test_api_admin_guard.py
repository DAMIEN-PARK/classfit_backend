"""관리자 경로는 전부 AdminCaller 다: 수강생 토큰 403, 토큰 없음 401 + WWW-Authenticate: Bearer.

새 앱(create_app, probe 없음)의 OpenAPI 에서 /v1/admin/ 경로·메서드를 전부 뽑아 돈다. 경로 변수는 1, 본문은 없다.
권한 의존성은 본문 검증보다 먼저 풀리므로 본문이 없어도 403·401 이 먼저 나온다. 끝점을 더하면 자동으로 들어온다.
"""

import re

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.main import create_app
from tests.fixtures.courses import learner_headers, open_test_course

METHODS = {"get", "post", "put", "patch", "delete"}
T2A_ADMIN_OPERATIONS = 25  # T1 POST /v1/admin/admins 1 + T2a 24


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
    assert len(operations) >= T2A_ADMIN_OPERATIONS, operations
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
