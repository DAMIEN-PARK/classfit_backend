"""시험 공통.

- 세션마다 한 번: alembic downgrade base → upgrade head (자식 프로세스, PYTHONPATH 는 시험이 직접 준다).
  head 가 1개인지도 본다. 스위트마다 따로 돌리면 서로의 자료를 지운다.
- 시험마다: 연결 하나 + 바깥 트랜잭션, 끝에 롤백. ORM 세션은 join_transaction_mode="create_savepoint" 로 합류.
- CLASSFIT_TEST_DATABASE_URL 이 없으면 pytest.fail. skip 하면 초록이 거짓말이 된다.
- 시험 폴더에 __init__.py 가 없으니 파일 이름(basename)이 폴더끼리 겹치면 안 된다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.pool import NullPool

from classfit.database.session import make_engine, make_session_factory

pytest_plugins = ["tests.stale_patch_guard"]

ROOT = Path(__file__).resolve().parent.parent
TEST_URL_VAR = "CLASSFIT_TEST_DATABASE_URL"


def _test_url() -> str:
    # 우선순위는 앱과 같다: 셸 환경 > .env. (make test 없이 pytest 를 직접 돌려도 .env 의 시험 URL 은 읽힌다)
    url = os.environ.get(TEST_URL_VAR) or dotenv_values(ROOT / ".env").get(TEST_URL_VAR)
    if not url:
        pytest.fail(
            f"미구성: {TEST_URL_VAR} 이 없습니다. 통합·계약 시험은 라이브 Postgres 가 필요하고 건너뛰지 않습니다.",
            pytrace=False,
        )
    dbname = url.rsplit("/", 1)[-1].split("?")[0]
    if not dbname.endswith("_test"):
        # downgrade base 가 표를 전부 지우므로, 개발 DB 를 가리키는 실수를 막는다
        pytest.fail(
            f"{TEST_URL_VAR} 의 DB 이름은 _test 로 끝나야 합니다 (지금: {dbname})",
            pytrace=False,
        )
    return url


@pytest.fixture(scope="session")
def migrated_db_url() -> str:
    """세션마다 한 번 마이그레이션 왕복. 실제 CLI 를 자식 프로세스로 돌려 env.py 까지 시험한다."""
    url = _test_url()
    heads = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads()
    assert len(heads) == 1, f"alembic head 가 {len(heads)}개입니다: {heads}"
    env = {**os.environ, "CLASSFIT_DATABASE_URL": url, "PYTHONPATH": str(ROOT / "src")}
    for step in (("downgrade", "base"), ("upgrade", "head")):
        done = subprocess.run(
            [sys.executable, "-m", "alembic", *step],
            check=False,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            pytest.fail(f"alembic {' '.join(step)} 실패:\n{done.stderr}", pytrace=False)
    return url


@pytest_asyncio.fixture
async def db_connection(migrated_db_url: str) -> AsyncIterator[AsyncConnection]:
    """시험마다 연결 하나 + 바깥 트랜잭션. 끝에 롤백."""
    engine = make_engine(migrated_db_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                yield connection
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )
    async with factory() as session:
        yield session
