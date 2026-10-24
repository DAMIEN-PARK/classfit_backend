"""미들웨어 순서(바깥 → 안): 오류 처리기(500 그물) → 요청 기록 → GZip → CORS(설정한 출처가 있을 때만) → 라우터.

add_middleware 는 나중에 더한 것이 바깥쪽이다. GZip 제외 목록은 Starlette 기본값(text/event-stream 포함)을 쓴다.
요청 기록은 토큰 네임스페이스 경로를 {token} 으로 남기고, 그 네임스페이스의 응답(2xx·307·4xx)에 Cache-Control: no-store 를
하나만 둔다(T9a 결정 xxv — 라우트 유무와 무관하게 경로로 판정, 바깥이 보내는 500 은 problem() 이 단다).
"""

from __future__ import annotations

import logging
from time import perf_counter

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from classfit.app.errors import is_token_path, request_path
from classfit.core.config import Settings

log = logging.getLogger("classfit.request")


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


def install_middleware(app: FastAPI, settings: Settings) -> None:
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
