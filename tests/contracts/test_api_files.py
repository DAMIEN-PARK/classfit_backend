"""GET /v1/files/{key}: 401 → 501 → 404 → 403 → 200 (ADR-003 결정 1·3 · Design 부록 A `test_files_`).

시험 전용 owner_kind 는 crud.scope.OWNER_KINDS(정의 모듈)에 monkeypatch.setitem 으로 넣는다.
501 시험만 FILE_STORE_ROOT 를 비워 두고, 나머지는 app.state.settings 를 file_store_root=tmp_path 로 바꾼다.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import scope
from classfit.models import AuthSession, StoredFile
from classfit.service.files.store import store_bytes

TOKEN = "probe-files-token"
DATA = b"hello, file"


@pytest.fixture
async def bearer(db_session: AsyncSession) -> dict[str, str]:
    db_session.add(
        AuthSession(
            token_hash=hashlib.sha256(TOKEN.encode()).hexdigest(),
            principal_type="admin",
            principal_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db_session.flush()
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


async def _file(session: AsyncSession, root: Path, owner_kind: str) -> StoredFile:
    row = StoredFile(
        key=f"k-{owner_kind}",
        sha256=store_bytes(root, DATA),
        owner_kind=owner_kind,
        owner_id=7,
        content_type="text/plain",
        size=len(DATA),
    )
    session.add(row)
    await session.flush()
    return row


def _judge(allowed: bool, calls: list[Any]):
    async def judge(session: AsyncSession, principal: Any, owner_id: int) -> bool:
        calls.append(owner_id)
        return allowed

    return judge


def _is_problem(r: httpx.Response, status: int, slug: str) -> None:
    assert r.status_code == status
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["type"] == slug


async def test_files_requires_bearer_401(client: httpx.AsyncClient) -> None:
    # 파일 루트도 비어 있다: 401 이 501 보다 앞이다
    for headers in (
        {},
        {"Authorization": "Bearer nope"},
        {"Authorization": "Basic eA=="},
    ):
        r = await client.get("/v1/files/k-probe", headers=headers)
        _is_problem(r, 401, "/problems/unauthorized")
        assert r.headers["www-authenticate"] == "Bearer"


async def test_files_store_root_unset_501(
    client: httpx.AsyncClient, bearer: dict[str, str]
) -> None:
    r = await client.get("/v1/files/k-probe", headers=bearer)
    _is_problem(r, 501, "/problems/not_configured")
    assert r.json()["missing"] == ["CLASSFIT_FILE_STORE_ROOT"]


async def test_files_unregistered_owner_kind_404(
    client: httpx.AsyncClient,
    bearer: dict[str, str],
    store_root: Path,
    db_session: AsyncSession,
) -> None:
    assert "unregistered" not in scope.OWNER_KINDS
    row = await _file(db_session, store_root, "unregistered")
    r = await client.get(f"/v1/files/{row.key}", headers=bearer)
    _is_problem(r, 404, "/problems/not_found")
    unknown = await client.get("/v1/files/no-such-key", headers=bearer)
    assert r.json()["detail"] == unknown.json()["detail"]  # 행 없음과 구별되지 않는다


async def test_files_unknown_key_404(
    client: httpx.AsyncClient, bearer: dict[str, str], store_root: Path
) -> None:
    r = await client.get("/v1/files/no-such-key", headers=bearer)
    _is_problem(r, 404, "/problems/not_found")
    # 경로 이탈 모양은 라우터가 먼저 404 로 막는다(key 칸은 / 를 받지 않는다)
    r = await client.get("/v1/files/..%2F..%2Fetc%2Fpasswd", headers=bearer)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


async def test_files_out_of_scope_403(
    client: httpx.AsyncClient,
    bearer: dict[str, str],
    store_root: Path,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setitem(scope.OWNER_KINDS, "probe", _judge(False, calls))
    row = await _file(db_session, store_root, "probe")
    r = await client.get(f"/v1/files/{row.key}", headers=bearer)
    _is_problem(r, 403, "/problems/forbidden")
    assert calls == [7]


async def test_files_ok_without_signing_key_200(
    client: httpx.AsyncClient,
    app: FastAPI,
    bearer: dict[str, str],
    store_root: Path,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert app.state.settings.file_signing_key is None
    calls: list[Any] = []
    monkeypatch.setitem(scope.OWNER_KINDS, "probe", _judge(True, calls))
    row = await _file(db_session, store_root, "probe")
    r = await client.get(f"/v1/files/{row.key}", headers=bearer)
    assert r.status_code == 200
    assert r.content == DATA
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["cache-control"] == "private, no-store"
    assert calls == [7]
