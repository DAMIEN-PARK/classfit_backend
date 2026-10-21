"""계약 시험: 진짜 create_app() 을 httpx.ASGITransport 로 부른다.

db() 의존성은 바꿔치기하지 않는다 — 트랜잭션 경계 자체가 시험 대상이다.
앱의 session_factory 만 시험 연결(바깥 트랜잭션 + savepoint)에 묶는다. lifespan 은 돌리지 않는다.
Settings 는 환경(.env 포함)과 무관하다: CLASSFIT_* 를 지우고 env_file 을 끄고 get_settings 캐시를 비운다.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncConnection

from classfit.core.config import Settings, get_settings
from classfit.database.session import make_session_factory
from classfit.main import create_app
from tests.fixtures.probe_routes import NestedTxProbe
from tests.fixtures.probe_routes import router as probe_router


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in list(os.environ):
        if key.startswith("CLASSFIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()  # classfit.main import 때 모듈 최상위 create_app() 이 채운 캐시
    yield
    get_settings.cache_clear()


@pytest.fixture
def nested_at_response_start() -> list[bool]:
    return []


@pytest_asyncio.fixture
async def app(db_connection: AsyncConnection, nested_at_response_start: list[bool]) -> FastAPI:
    application = create_app(Settings())
    application.state.session_factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )
    application.include_router(probe_router)  # 시험 전용 (tests/fixtures/probe_routes.py)
    application.add_middleware(NestedTxProbe, connection=db_connection, sink=nested_at_response_start)
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_noraise(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """처리되지 않은 예외의 500 problem+json 을 응답으로 받아 보는 클라이언트."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
