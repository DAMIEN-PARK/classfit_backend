"""전역 본문 상한(T11 결정 i): BodyLimitMiddleware — 업로드 연산은 (업로드 상한 최댓값 + 2) MiB, 그 밖은 1MiB.

- 상한은 Content-Type 이 아니라 라우트로 고른다(업로드 연산 = openapi_extra requestBody 가 multipart 인 APIRoute,
  Match.FULL 만). ① 선언 길이가 넘으면 앱을 부르지 않고(인증 전) 413 ② 읽은 바이트가 넘으면 읽는 자리에서 413.
- CORS · 요청 기록 단언과 업로드 갈래는 시험용 앱(업로드 상한 다섯 = 1MiB → 끝점 한도 2MiB · 업로드 상한 3MiB,
  CORS 출처 하나)으로 본다. 앱·db 재정의는 contracts conftest 의 꼴이다(바깥 트랜잭션 + savepoint).
"""

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from classfit.app.middleware import BodyLimitMiddleware
from classfit.core.config import Settings
from classfit.database.session import make_session_factory
from classfit.main import create_app
from classfit.models import SessionAttachment, StoredFile
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.enter import PDF, add_session
from tests.fixtures.instructors import problem_of

MIB = 1024 * 1024
ORIGIN = "https://app.example.com"
TOO_LARGE = "/problems/content-too-large"
JSON = {"content-type": "application/json"}
SMALL_UPLOADS = {
    "attachment_pdf_max_mb": 1,
    "attachment_office_max_mb": 1,
    "attachment_zip_max_mb": 1,
    "attachment_image_max_mb": 1,
    "document_pdf_max_mb": 1,
}
UPLOAD_OPERATIONS_AT_LEAST = 8  # T11 착수 때 multipart 연산 8


@pytest.fixture
def small_app(db_connection: AsyncConnection, tmp_path: Path) -> FastAPI:
    application = create_app(
        Settings(cors_origins=[ORIGIN], file_store_root=tmp_path, **SMALL_UPLOADS)
    )
    application.state.session_factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )
    return application


@pytest_asyncio.fixture
async def small(small_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=small_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _spaces(total: int, pulled: list[int] | None = None) -> AsyncIterator[bytes]:
    """길이 선언 없는 스트림(64KiB 청크). pulled 가 있으면 내보낸 청크 수를 적는다."""
    sent = 0
    while sent < total:
        n = min(64 * 1024, total - sent)
        sent += n
        if pulled is not None:
            pulled.append(n)
        yield b" " * n


def _logged(caplog: pytest.LogCaptureFixture, line: str) -> bool:
    return any(
        r.name == "classfit.request" and r.getMessage().startswith(line)
        for r in caplog.records
    )


def _too_large(r: httpx.Response, limit: int) -> None:
    body = problem_of(r, 413, TOO_LARGE)
    assert body["detail"] == f"본문이 너무 큽니다({limit}바이트까지)", body


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_body_limit_declared_413_before_auth(
    small: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="classfit.request")
    pulled: list[int] = []
    # 토큰 없이 관리자 JSON 연산에 1MiB + 1 선언 — 401 이 아니라 413, 앱은 본문을 한 바이트도 당기지 않는다
    r = await small.post(
        "/v1/admin/admins",
        headers={**JSON, "content-length": str(MIB + 1), "origin": ORIGIN},
        content=_spaces(MIB + 1, pulled),
    )
    _too_large(r, MIB)
    assert pulled == []
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert _logged(caplog, "POST /v1/admin/admins -> 413")
    # 본문을 읽지 않는 GET 도 선언 길이로 413(인증 전)
    r = await small.request(
        "GET",
        "/v1/admin/courses",
        headers={"content-length": str(MIB + 1)},
        content=_spaces(MIB + 1, pulled),
    )
    _too_large(r, MIB)
    assert pulled == []


async def test_body_limit_streamed_413(
    small: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="classfit.request")
    # 길이 선언 없는 스트림이 1MiB 를 1바이트 넘는다 — pydantic 본문 연산은 인증 전에 읽다가 413
    r = await small.post(
        "/v1/admin/admins",
        headers={**JSON, "origin": ORIGIN},
        content=_spaces(MIB + 1),
    )
    assert "content-length" not in r.request.headers
    _too_large(r, MIB)
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert _logged(caplog, "POST /v1/admin/admins -> 413")


async def test_body_limit_multipart_label_json_route(
    client: httpx.AsyncClient,
) -> None:
    """JSON 연산에 multipart 라고 붙여도 JSON 상한(1MiB) — 업로드 상한(기본 102MiB) 미만이어도 413."""
    multipart = {"content-type": "multipart/form-data; boundary=x"}
    r = await client.post(
        "/v1/admin/admins", headers=multipart, content=b" " * (2 * MIB)
    )
    _too_large(r, MIB)
    # 업로드 경로라도 메서드가 다르면(Match.PARTIAL) 업로드 연산이 아니다
    r = await client.request(
        "GET",
        "/v1/me/sessions/1/attachments",
        headers=multipart,
        content=b" " * (2 * MIB),
    )
    _too_large(r, MIB)


async def test_body_limit_upload_streamed_413(
    small: httpx.AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    _, admin = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    sid = await add_session(small, admin, course.id, day_no=1, slot=1, is_open=True)
    boundary = "b0undary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="kind"\r\n\r\npdf\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\nx\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + PDF

    async def form() -> AsyncIterator[bytes]:
        yield head
        async for chunk in _spaces(3 * MIB):
            yield chunk

    # 선언 길이 1MiB(끝점 한도 2MiB 안)로 통과한 뒤 업로드 상한 3MiB 를 넘게 흘린다 — request.form() 안에서 413
    r = await small.post(
        f"/v1/admin/sessions/{sid}/attachments",
        headers={
            **admin,
            "content-type": f"multipart/form-data; boundary={boundary}",
            "content-length": str(MIB),
        },
        content=form(),
    )
    _too_large(r, 3 * MIB)
    assert await _count(db_session, SessionAttachment) == 0
    assert await _count(db_session, StoredFile) == 0
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


async def test_body_limit_upload_endpoint_own_413_first(
    small: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """선언 길이 = 끝점 한도 + 1(2MiB + 1, 업로드 상한 3MiB 미만) → 미들웨어는 지나고 끝점 자체 413 안내문."""
    _, admin = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    sid = await add_session(small, admin, course.id, day_no=1, slot=1, is_open=True)
    r = await small.post(
        f"/v1/admin/sessions/{sid}/attachments",
        headers={**admin, "content-type": "multipart/form-data; boundary=x"},
        content=b" " * (2 * MIB + 1),
    )
    body = problem_of(r, 413, TOO_LARGE)
    assert body["detail"] == "본문이 너무 큽니다(1MiB 까지)", body


def test_body_limit_upload_routes_match_openapi() -> None:
    app = create_app(Settings())
    [entry] = [m for m in app.user_middleware if m.cls is BodyLimitMiddleware]
    collected = {
        (method, route.path)
        for route in entry.kwargs["upload_routes"]
        for method in route.methods
    }
    multipart = {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        for method, op in item.items()
        if "multipart/form-data" in op.get("requestBody", {}).get("content", {})
    }
    assert len(multipart) >= UPLOAD_OPERATIONS_AT_LEAST, multipart
    assert collected == multipart
    # 업로드 상한 = 업로드 상한 다섯 중 최댓값(기본 zip 100MiB) + 2MiB · 그 밖 1MiB
    assert entry.kwargs["upload_max"] == 102 * MIB
    assert entry.kwargs["default_max"] == MIB


async def test_body_limit_under_cap_unchanged(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """1MiB 까지(선언 길이 · 스트림)와 본문 없는 GET 은 지금과 같다: 401 · 403 · 422 · 200."""
    course, _ = await open_test_course(db_session)
    learner = await learner_headers(db_session, course.id)
    _, admin = await admin_headers(db_session)
    exact = b"{}" + b" " * (MIB - 2)
    r = await client.post("/v1/admin/admins", headers=JSON, content=exact)
    assert int(r.request.headers["content-length"]) == MIB
    problem_of(r, 401)

    async def exact_stream() -> AsyncIterator[bytes]:
        for start in range(0, MIB, 64 * 1024):
            yield exact[start : start + 64 * 1024]

    r = await client.post("/v1/admin/admins", headers=JSON, content=exact_stream())
    assert "content-length" not in r.request.headers
    problem_of(r, 401)
    r = await client.post(
        "/v1/admin/admins", headers={**JSON, **learner}, content=exact
    )
    problem_of(r, 403)
    r = await client.post("/v1/admin/admins", headers={**JSON, **admin}, content=exact)
    problem_of(r, 422)
    r = await client.get("/v1/health")
    assert r.status_code == 200, r.text
    r = await client.get("/v1/admin/courses", headers=admin)
    assert r.status_code == 200, r.text
