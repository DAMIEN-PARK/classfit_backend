"""API 진입점: uvicorn classfit.main:app

create_app() 이 앱을 만들고, lifespan 이 엔진을 만들어 app.state.session_factory 에 둔 뒤 끝날 때 dispose 한다.
엔진은 기동 때 실패해야 한다(첫 요청에서 실패하면 healthcheck 가 이미 통과한 뒤다).
계약 시험은 lifespan 을 돌리지 않으므로 app.state 에 넣는 것은 create_app() 안에서 만든다.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from classfit import __version__
from classfit.app.errors import install_error_handlers
from classfit.app.middleware import install_middleware
from classfit.app.routers import ROUTERS
from classfit.core.config import Settings, get_settings
from classfit.database.session import make_engine, make_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    # uvicorn 은 루트 로거를 비워 둔다. 여기서 켜야 INFO 가 보인다(모듈 최상위에 두면 pytest 캡처와 섞인다).
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s",
    )
    engine = make_engine(
        settings.require_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    async with engine.connect() as connection:  # 기동 때 실패하게
        await connection.execute(text("select 1"))
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="classfit API",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/v1/openapi.json",  # 계약 정본. 늘 연다
        docs_url="/v1/docs" if settings.enable_docs else None,  # 개발 스위치
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.session_factory = None  # lifespan 또는 시험이 채운다
    install_error_handlers(app)
    install_middleware(app, settings)
    for router in ROUTERS:
        app.include_router(router)
    return app


app = create_app()
