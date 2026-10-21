"""미들웨어 순서(바깥 → 안): 오류 처리기(500 그물) → 요청 기록 → GZip → CORS(설정한 출처가 있을 때만) → 라우터.

add_middleware 는 나중에 더한 것이 바깥쪽이다. GZip 제외 목록은 Starlette 기본값(text/event-stream 포함)을 쓴다.
"""

from __future__ import annotations

import logging
from time import perf_counter

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            # 처리되지 않은 예외는 이 바깥의 ServerErrorMiddleware 가 500 으로 보낸다 — 여기서는 응답을 못 본다
            status = status or 500
            raise
        finally:
            ms = (perf_counter() - started) * 1000
            log.info("%s %s -> %s %.1fms", scope.get("method"), scope.get("path"), status, ms)


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
