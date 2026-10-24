"""전역 본문 상한(T11 결정 i): BodyLimitMiddleware — 업로드 연산은 (업로드 상한 최댓값 + 2) MiB, 그 밖은 1MiB.

- 상한은 Content-Type 이 아니라 라우트로 고른다(업로드 연산 = openapi_extra requestBody 가 multipart 인 APIRoute,
  Match.FULL 만). ① 선언 길이가 넘으면 앱을 부르지 않고(인증 전) 413 ② 읽은 바이트가 넘으면 읽는 자리에서 413.
- 응답이 시작된 뒤의 초과(본문을 안 읽는 FileResponse 의 disconnect 대기 루프)는 던지지 않고 응답을 끝낸다(리뷰 N1).
- 정상 본문이 1MiB 를 넘는 JSON 연산은 라우트별 상한 표(ROUTE_MAX_BYTES — 차시표 PUT 7MiB)가 따로 정한다(codex 구현 1·2차 — 필수 이스케이프 최대).
- CORS · 요청 기록 단언과 업로드 갈래는 시험용 앱(업로드 상한 다섯 = 1MiB → 끝점 한도 2MiB · 업로드 상한 3MiB,
  CORS 출처 하나)으로 본다. 앱·db 재정의는 contracts conftest 의 꼴이다(바깥 트랜잭션 + savepoint).
"""

import ast
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from starlette.types import Message, Receive, Scope, Send

from classfit.app.deps import limited_json
from classfit.app.errors import AppError
from classfit.app.middleware import ROUTE_MAX_BYTES, BodyLimitMiddleware, route_limits
from classfit.app.routers import ROUTERS
from classfit.app.upload import check_length
from classfit.core.config import Settings
from classfit.database.session import make_session_factory
from classfit.main import create_app
from classfit.models import SessionAttachment, StoredFile
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.enter import PDF, add_pdf, add_session
from tests.fixtures.instructors import problem_of
from tests.fixtures.pool import curriculum_body, instructor_pair

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
SLOTS = "/v1/me/curricula/{curriculum_id}/slots"
ENDPOINTS = Path(__file__).resolve().parents[2] / "src/classfit/app/endpoints"


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


def _form_readers() -> set[tuple[str, str]]:
    """endpoints 모듈마다 request.form( 을 부르는 함수와, 같은 모듈에서 그 함수를 (거쳐) 부르는 함수 — (모듈, 이름)."""
    found: set[tuple[str, str]] = set()
    for path in sorted(ENDPOINTS.glob("*.py")):
        calls: dict[str, set[str]] = {}
        readers: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls[node.name] = set()
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                func = sub.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "form"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "request"
                ):
                    readers.add(node.name)
                elif isinstance(func, ast.Name):
                    calls[node.name].add(func.id)
        grown = True
        while grown:
            grown = False
            for name, called in calls.items():
                if name not in readers and called & readers:
                    readers.add(name)
                    grown = True
        found |= {(f"classfit.app.endpoints.{path.stem}", name) for name in readers}
    return found


def test_body_limit_upload_routes_match_form_readers() -> None:
    """업로드 라우트 = 소스에서 request.form( 을 (도우미를 거쳐) 부르는 끝점 — openapi_extra 와 다른 근원이라 빠짐을 잡는다."""
    app = create_app(Settings())
    [entry] = [m for m in app.user_middleware if m.cls is BodyLimitMiddleware]
    uploads = {
        (r.endpoint.__module__, r.endpoint.__name__)
        for r in entry.kwargs["upload_routes"]
    }
    endpoints = {
        (r.endpoint.__module__, r.endpoint.__name__)
        for router in ROUTERS
        for r in router.routes
        if isinstance(r, APIRoute)
    }
    readers = _form_readers() & endpoints
    assert len(readers) >= UPLOAD_OPERATIONS_AT_LEAST, readers
    assert uploads == readers


async def test_body_limit_after_response_start_no_raise(
    app: FastAPI,
    db_session: AsyncSession,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """파일 GET(FileResponse 는 본문을 읽지 않고 disconnect 대기 루프로 receive 를 부른다)에 응답 시작 뒤 3MiB 를 흘려도
    던지지 않고(response already started RuntimeError 없음) 3MiB 파일을 끝까지 준다. 시작 전 갈래의 413 은 그대로다."""
    caplog.set_level(logging.INFO)
    app.state.settings = Settings(file_store_root=tmp_path)
    started = asyncio.Event()

    async def watched(scope: Scope, receive: Receive, send: Send) -> None:
        async def send_start(message: Message) -> None:
            if message["type"] == "http.response.start":
                started.set()
            await send(message)

        await app(scope, receive, send_start)

    transport = httpx.ASGITransport(app=watched)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        _, admin = await admin_headers(db_session)
        course, _ = await open_test_course(db_session)
        sid = await add_session(c, admin, course.id, day_no=1, slot=1, is_open=True)
        # 여러 청크(64KiB)인 파일 — 초과 때 바로 disconnect 하면 FileResponse 가 중간에 끊는다
        data = PDF + b"0" * (3 * MIB)
        r = await add_pdf(c, admin, sid, data)
        assert r.status_code == 201, r.text
        href = r.json()["href"]
        started.clear()

        async def body() -> AsyncIterator[bytes]:
            yield b" " * 1024
            await started.wait()  # 응답이 시작된 뒤에 상한(1MiB)을 넘긴다
            yield b" " * (3 * MIB)

        r = await c.request("GET", href, headers=admin, content=body())
        assert "content-length" not in r.request.headers
        assert (r.status_code, r.content) == (200, data)
        r = await c.post("/v1/admin/admins", headers=JSON, content=_spaces(MIB + 1))
        _too_large(r, MIB)
    assert [x.getMessage() for x in caplog.records if x.levelno >= logging.ERROR] == []
    assert _logged(caplog, f"GET {href} -> 200")


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


def test_body_limit_route_table_matches_routes() -> None:
    """표 항목마다 실제 라우트가 하나다(경로가 바뀌면 앱을 만들 때 실패) · 미들웨어가 그 라우트와 상한을 받는다."""
    assert ROUTE_MAX_BYTES == {("PUT", SLOTS): 7 * MIB}
    app = create_app(Settings())
    [entry] = [m for m in app.user_middleware if m.cls is BodyLimitMiddleware]
    got = {
        (method, route.path): limit
        for route, limit in entry.kwargs["route_limits"]
        for method in route.methods
    }
    assert got == ROUTE_MAX_BYTES
    operations = {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        for method in item
    }
    assert set(ROUTE_MAX_BYTES) <= operations
    for missing in (("PUT", "/v1/me/curricula/{id}/slots"), ("GET", SLOTS)):
        with pytest.raises(RuntimeError, match="라우트가 0개"):
            route_limits(ROUTERS, {missing: MIB})


async def test_body_limit_route_table_slots_max_body(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """차시표 PUT 의 필수 이스케이프 최대 본문: 25일차 × 8교시 = 200칸 · 제목 4바이트 글자 200 · 설명 제어 문자(\\u0001
    6바이트) 5,000 — 스키마·격자 검증을 지나는 6,169,539 B → 200. 표 상한(7MiB) + 1 은 413 · 다른 JSON 연산은 1MiB."""
    limit = ROUTE_MAX_BYTES[("PUT", SLOTS)]
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    r = await client.post(
        "/v1/me/curricula",
        headers=auth,
        json=curriculum_body(days=25, start_time="09:00", end_time="17:00"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["slots_per_day"] == 8
    url = SLOTS.format(curriculum_id=r.json()["id"])
    cells = [
        {"day": d, "slot": s, "title": "\U0001f600" * 200, "description": "\x01" * 5000}
        for d in range(1, 26)
        for s in range(1, 9)
    ]
    raw = json.dumps({"slots": cells}, ensure_ascii=False, separators=(",", ":"))
    big = raw.encode()
    assert len(big) == 6_169_539  # 필수 이스케이프 최대(scratchpad 측정과 같다)
    r = await client.put(url, headers={**auth, **JSON}, content=big)
    assert r.status_code == 200, r.text[:300]
    slots = r.json()["slots"]
    assert len(slots) == 200 and slots[-1]["description"] == "\x01" * 5000
    # 선언 길이 상한 + 1 은 앱 전에 · 길이 선언 없는 상한 + 1 스트림은 읽다가 413
    r = await client.put(
        url,
        headers={**auth, **JSON, "content-length": str(limit + 1)},
        content=_spaces(limit + 1),
    )
    _too_large(r, limit)
    r = await client.put(url, headers={**auth, **JSON}, content=_spaces(limit + 1))
    _too_large(r, limit)
    # 다른 JSON 연산(같은 커리큘럼 PATCH)은 여전히 1MiB
    r = await client.patch(
        url.removesuffix("/slots"), headers={**auth, **JSON}, content=big
    )
    _too_large(r, MIB)


class _Empty(BaseModel):
    pass


def _request(length: str) -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    headers = [
        (b"content-length", length.encode()),
        (b"content-type", b"application/json"),
    ]
    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": headers}, receive
    )


async def test_body_limit_long_content_length_413(client: httpx.AsyncClient) -> None:
    """4,301자리 Content-Length 는 int() 가 ValueError(500)다 — 자릿수로 먼저 보아 413. 앞 0 이 붙은 작은 값은 그대로."""
    huge, padded = "9" * 4301, "0" * 4400 + "2"
    r = await client.post(
        "/v1/admin/admins", headers={**JSON, "content-length": huge}, content=b"{}"
    )
    _too_large(r, MIB)
    r = await client.post(
        "/v1/admin/admins", headers={**JSON, "content-length": padded}, content=b"{}"
    )
    problem_of(r, 401)
    # 업로드 check_length · limited_json 도 같은 판정(미들웨어 뒤라 HTTP 로는 닿지 않아 직접 부른다)
    with pytest.raises(AppError) as caught:
        check_length(_request(huge), MIB)
    assert caught.value.status == 413
    check_length(_request(padded), MIB)
    with pytest.raises(AppError) as caught:
        await limited_json(_Empty, 1024)(_request(huge))
    assert caught.value.status == 413
    assert await limited_json(_Empty, 1024)(_request(padded)) == _Empty()
