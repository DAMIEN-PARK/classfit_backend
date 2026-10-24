"""미들웨어 순서(바깥 → 안): 오류 처리기(500 그물) → 요청 기록 → GZip → CORS(설정한 출처가 있을 때만) → 본문 상한 → 라우터.

add_middleware 는 나중에 더한 것이 바깥쪽이다. GZip 제외 목록은 Starlette 기본값(text/event-stream 포함)을 쓴다.
요청 기록은 토큰 네임스페이스 경로를 {token} 으로 남기고, 그 네임스페이스의 응답(2xx·307·4xx)에 Cache-Control: no-store 를
하나만 둔다(T9a 결정 xxv — 라우트 유무와 무관하게 경로로 판정, 바깥이 보내는 500 은 problem() 이 단다).
본문 상한은 CORS · 요청 기록 안쪽이라 413 에도 CORS 헤더가 붙고 기록된다(T11 결정 i).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from time import perf_counter

from fastapi import APIRouter, FastAPI, Request
from fastapi.routing import APIRoute
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from classfit.app.errors import is_token_path, problem, request_path
from classfit.app.routers import ROUTERS
from classfit.app.upload import MIB
from classfit.core.config import Settings

log = logging.getLogger("classfit.request")

# 업로드 연산 밖 모든 요청의 본문 상한(Content-Type 과 상관없이). 실사용 꼴 JSON 본문은 수 KB 다(T11 결정 i 〔정함〕)
BODY_MAX_BYTES = MIB
# 업로드 연산 상한 = 업로드 상한 설정 중 가장 큰 값 + 이 여유. 끝점 check_length 의 상한 + 1MiB 보다 커서 끝점 413 이 먼저다
UPLOAD_SLACK_MIB = 2


class RequestLogMiddleware:
    """순수 ASGI. 메서드 · 경로 · 상태 · 소요 ms 한 줄. (DB request_log 는 나중에, 다른 트랜잭션으로)"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status: int | None = None
        no_store = is_token_path(scope)

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                if no_store:
                    # 있으면 바꿔 끼운다
                    MutableHeaders(scope=message)["cache-control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            # 처리되지 않은 예외는 이 바깥의 ServerErrorMiddleware 가 500 으로 보낸다 — 여기서는 응답을 못 본다
            status = status or 500
            raise
        finally:
            ms = (perf_counter() - started) * 1000
            log.info(
                "%s %s -> %s %.1fms",
                scope.get("method"),
                request_path(scope),
                status,
                ms,
            )


def upload_routes(routers: Iterable[APIRouter]) -> list[APIRoute]:
    """업로드 연산: openapi_extra 의 requestBody 에 multipart/form-data 가 있는 APIRoute(폼은 끝점이 인증 뒤에 읽는다)."""
    return [
        route
        for router in routers
        for route in router.routes
        if isinstance(route, APIRoute)
        and "multipart/form-data"
        in (route.openapi_extra or {}).get("requestBody", {}).get("content", {})
    ]


def _declared_length(scope: Scope) -> int | None:
    """Content-Length 가 ASCII 숫자면 그 값, 없거나 모양 밖이면 None(읽은 바이트 갈래가 잰다)."""
    for name, value in scope["headers"]:
        if name == b"content-length":
            raw = value.strip()
            # bytes.isdigit 은 ASCII 숫자만 참이다
            return int(raw) if raw.isdigit() else None
    return None


def _too_large(limit: int) -> str:
    return f"본문이 너무 큽니다({limit}바이트까지)"


class BodyLimitMiddleware:
    """순수 ASGI. 요청 본문 상한(T11 결정 i): 업로드 연산(라우트가 Match.FULL)은 upload_max, 그 밖은 default_max.

    상한은 Content-Type 이 아니라 라우트로 고른다 — JSON 끝점은 Content-Type 을 보기 전에 본문을 다 읽는다.
    ① 선언 길이: Content-Length 가 ASCII 숫자이고 상한을 넘으면 앱을 부르지 않고(인증 전) 413 problem 을 보낸다.
    ② 읽은 바이트: 그 밖이면 receive 를 감싸 http.request 본문 바이트를 세고 상한을 넘는 청크에서 Starlette
       HTTPException(413) 을 던진다. FastAPI 본문 읽기 · Starlette 폼 파서가 그대로 다시 던져 오류 처리기가 problem 으로
       바꾼다(다른 예외형이면 400·500 이 된다). 무언가 본문을 읽을 때만 돈다. http.disconnect 는 세지 않는다.
    http 밖 scope(websocket · lifespan)는 손대지 않는다.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        upload_routes: Sequence[APIRoute],
        upload_max: int,
        default_max: int,
    ) -> None:
        self.app = app
        self.upload_routes = tuple(upload_routes)
        self.upload_max = upload_max
        self.default_max = default_max

    def _limit(self, scope: Scope) -> int:
        for route in self.upload_routes:
            # PARTIAL 은 경로만 맞고 메서드가 다른 경우다
            if route.matches(scope)[0] == Match.FULL:
                return self.upload_max
        return self.default_max

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope)
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            response = problem(Request(scope), status=413, detail=_too_large(limit))
            await response(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, _too_large(limit))
            return message

        await self.app(scope, limited_receive, send)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    upload_mb = max(
        settings.attachment_pdf_max_mb,
        settings.attachment_office_max_mb,
        settings.attachment_zip_max_mb,
        settings.attachment_image_max_mb,
        settings.document_pdf_max_mb,
    )
    # 먼저 더한 것이 안쪽이다 — CORS · 요청 기록 안쪽(라우터를 더하기 전이라 app.routes 가 아니라 ROUTERS 를 본다)
    app.add_middleware(
        BodyLimitMiddleware,
        upload_routes=upload_routes(ROUTERS),
        upload_max=(upload_mb + UPLOAD_SLACK_MIB) * MIB,
        default_max=BODY_MAX_BYTES,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestLogMiddleware)
