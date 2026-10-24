"""Alembic 환경 (async).

- target_metadata 는 `import classfit.models` 한 줄로 다 본다.
- 마이그레이션 URL 은 환경 변수 CLASSFIT_DATABASE_URL 하나만 읽는다. 폴백 없음.
- compare_type · compare_server_default 를 켠다. 리비전 id 는 손으로(0001, 0002 …).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

import classfit.models  # noqa: F401  (표 전부 등록)
from classfit.database.session import make_engine
from classfit.models import Base

ENV_VAR = "CLASSFIT_DATABASE_URL"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get(ENV_VAR)
    if not url:
        raise RuntimeError(
            f"미구성: {ENV_VAR} 이 없습니다 (마이그레이션은 이 변수 하나만 읽습니다)"
        )
    return url


def _configure(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(
        url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = make_engine(_database_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_async())
    else:
        # 돌고 있는 루프 안에서 env.py 를 부르면 asyncio.run 이 죽는다 — 시험은 자식 프로세스로 돌린다
        raise RuntimeError(
            "alembic env.py 는 이벤트 루프 밖에서만 돈다 (자식 프로세스로 실행)"
        )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
