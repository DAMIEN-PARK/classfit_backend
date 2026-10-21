"""관리 명령 create_admin · file_gc 의 미리 보기와 --apply. 라이브 PG, 시험 연결에 묶은 session_factory 를 넘긴다."""

import json
import os
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from classfit.core.config import Settings
from classfit.database.session import make_session_factory
from classfit.models import AdminAccount, AuditLog, StoredFile
from classfit.service.files.store import path_for, store_bytes
from scripts import create_admin, file_gc

PASSWORD = "probe-password-1234"


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


def _ask(answer: str = PASSWORD):
    asked: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return answer

    return ask, asked


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


def _settings(root: Path) -> Settings:
    return Settings(_env_file=None, file_store_root=root, file_gc_grace_hours=24)


def _age(path: Path, hours: float) -> None:
    then = time.time() - hours * 3600
    os.utime(path, (then, then))


async def test_create_admin_preview_writes_nothing(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ask, asked = _ask()
    assert await create_admin.run(["--login-id", "admin-a"], factory, ask=ask) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is False and out["admin"]["login_id"] == "admin-a"
    assert len(asked) == 2  # 두 번 받는다
    assert await _count(db_session, AdminAccount) == 0
    assert await _count(db_session, AuditLog) == 0


async def test_create_admin_apply_writes_one_row(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ask, _ = _ask()
    assert (
        await create_admin.run(["--login-id", "admin-a", "--apply"], factory, ask=ask)
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is True
    row = (await db_session.scalars(select(AdminAccount))).one()
    assert row.login_id == "admin-a" and row.id == out["admin"]["id"]
    assert (
        row.password_hash.startswith("$argon2id$") and PASSWORD not in row.password_hash
    )
    audit = (await db_session.scalars(select(AuditLog))).one()
    assert (audit.actor, audit.action, audit.target_type, audit.target_id) == (
        "system",
        "admin.create",
        "admin_account",
        str(row.id),
    )
    # 같은 아이디는 전제 거절(3), 행 수 그대로
    assert (
        await create_admin.run(["--login-id", "admin-a", "--apply"], factory, ask=ask)
        == 3
    )
    assert await _count(db_session, AdminAccount) == 1
    assert await _count(db_session, AuditLog) == 1


async def test_create_admin_password_not_in_argv(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ask, asked = _ask()
    argv = ["--login-id", "admin-a", "--password", PASSWORD, "--apply"]
    assert await create_admin.run(argv, factory, ask=ask) == 2
    captured = capsys.readouterr()
    assert PASSWORD not in captured.out + captured.err  # 값을 되찍지 않는다
    assert asked == []
    assert await _count(db_session, AdminAccount) == 0


async def test_file_gc_preview_deletes_nothing(
    factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sha = store_bytes(tmp_path, b"orphan")
    _age(path_for(tmp_path, sha), 25)
    assert await file_gc.run([], factory, _settings(tmp_path)) == 0
    out = json.loads(capsys.readouterr().out)
    assert (
        out["applied"] is False and out["candidates"] == [sha] and out["deleted"] == []
    )
    assert path_for(tmp_path, sha).is_file()


async def test_file_gc_apply_deletes_only_unreferenced_old_bytes(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    kept_ref = store_bytes(tmp_path, b"referenced and old")
    gone = store_bytes(tmp_path, b"unreferenced and old")
    kept_fresh = store_bytes(tmp_path, b"unreferenced but fresh")
    _age(path_for(tmp_path, kept_ref), 25)
    _age(path_for(tmp_path, gone), 25)
    _age(path_for(tmp_path, kept_fresh), 23)
    db_session.add(
        StoredFile(
            key="k-ref",
            sha256=kept_ref,
            owner_kind="probe",
            owner_id=1,
            content_type="application/octet-stream",
            size=18,
        )
    )
    await db_session.flush()

    assert await file_gc.run(["--apply"], factory, _settings(tmp_path)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is True and out["deleted"] == [gone]
    assert not path_for(tmp_path, gone).exists()
    assert path_for(tmp_path, kept_ref).is_file()
    assert path_for(tmp_path, kept_fresh).is_file()
