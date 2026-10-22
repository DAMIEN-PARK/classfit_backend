"""gc 유예와 소유자 삭제(Design 부록 A T6 · E-14 의 gc 2): 강사 첨부 service 를 거쳐 잰다. 라이브 PG, 커밋하지 않는다.

- test_gc_grace: 강사 업로드가 "바이트는 썼고 행은 아직 없음" 인 순간에 gc 를 돌려도 그 바이트를 지우지 않는다
  (store_bytes 가 mtime 을 갱신 — service/files/store.py). crud.attachment.insert_attachment 를 첫 호출에서 gc 를 먼저
  돌리는 감싸개로 바꿔 그 순간을 잡는다. 같은 실행에서 48시간 된 참조 0 바이트는 지워진다(gc 가 실제로 돌았다는 대조).
- test_gc_owner_delete_cascade: 첨부 지우기·교체·세션 삭제가 stored_file 행을 같은 트랜잭션에서 지우고(SAVEPOINT 롤백이면
  함께 돌아온다), gc 는 강사 바이트를 지우되 기본 강의안 사본과 sha 가 같은 원본 바이트는 원본 행이 가리켜 남긴다.
- factory·_settings·_age 는 T1 tests/integration/test_db_admin_commands.py 꼴을 복사했다(시험 연결에 묶은 savepoint factory —
  gc 는 이 시험 트랜잭션의 행을 본다).
- 표본 바이트는 서로 다르고 어느 픽스처 바이트와도 다르다. 같은 바이트면 내용 주소가 한 파일로 합쳐 "지워짐/남음" 이
  갈리지 않으므로 gc 전에 sha 관계를 단언한다(T6 계획 codex 1차 #3).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

import classfit.crud.attachment
from classfit.core.config import Settings
from classfit.crud import stored_file as crud_stored_file
from classfit.database.session import make_session_factory
from classfit.models import SessionAttachment, StoredFile
from classfit.schemas.course import SessionPatchIn
from classfit.service.courses import sections
from classfit.service.files import my_attachment_edit, my_attachments
from classfit.service.files.store import path_for, store_bytes
from classfit.service.rules.attachment import UPLOAD_KINDS
from scripts import file_gc
from tests.fixtures.assign import (
    PDF,
    capability_files,
    course_with_section,
    pool_session,
)
from tests.fixtures.instructors import make_instructor
from tests.fixtures.my_attachments import SAMPLES, assigned_session
from tests.fixtures.pool import make_pool_course

MAX = {kind: 1024 * 1024 for kind in UPLOAD_KINDS}
OWNER = "session_attachment"


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


def _settings(root: Path) -> Settings:
    return Settings(_env_file=None, file_store_root=root, file_gc_grace_hours=24)


def _age(path: Path, hours: float) -> None:
    then = time.time() - hours * 3600
    os.utime(path, (then, then))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _gc(
    factory: async_sessionmaker[AsyncSession],
    root: Path,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    assert await file_gc.run(["--apply"], factory, _settings(root)) == 0
    return json.loads(capsys.readouterr().out)


async def _x_session(session: AsyncSession, email: str) -> tuple[int, int]:
    """(강사 X id, X 에게 배정된 닫힌 세션 id)."""
    x = await make_instructor(
        session, Settings(_env_file=None), email=email, status="approved"
    )
    _, section = await course_with_section(session)
    return x, await assigned_session(session, section.id, instructor_id=x)


async def _file(
    session: AsyncSession, root: Path, x: int, sid: int, name: str, data: bytes
) -> SessionAttachment:
    row, _ = await my_attachments.add_my_file(
        session,
        root=root,
        max_bytes=MAX,
        instructor_id=x,
        session_id=sid,
        title=name,
        description=None,
        filename=name,
        data=data,
        actor=f"instructor:{x}",
    )
    return row


async def _rows_by_sha(session: AsyncSession, sha: str) -> int:
    stmt = select(func.count()).select_from(StoredFile).where(StoredFile.sha256 == sha)
    return await session.scalar(stmt) or 0


async def test_gc_grace(
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    b = (
        PDF + b"%t6-gc-grace-b\n"
    )  # 올릴 바이트(같은 바이트가 48시간 전부터 디스크에 있다)
    c = b"t6-gc-grace-c orphan"  # 48시간 된 참조 0 바이트(대조)
    d = PDF + b"%t6-gc-grace-d\n"  # 롤백할 업로드
    sha_b, sha_c, sha_d = _sha(b), _sha(c), _sha(d)
    assert len({sha_b, sha_c, sha_d}) == 3
    for sha in (sha_b, sha_c, sha_d):
        assert await _rows_by_sha(db_session, sha) == 0
    for data in (b, c):
        _age(path_for(tmp_path, store_bytes(tmp_path, data)), 48)

    x, sid = await _x_session(db_session, "gc-grace-x@example.com")
    real = classfit.crud.attachment.insert_attachment
    seen: list[dict[str, Any]] = []

    async def gc_first(*args: Any, **kwargs: Any) -> Any:
        if not seen:  # 바이트는 썼고 행은 아직 없다
            assert await _rows_by_sha(db_session, sha_b) == 0
            seen.append(await _gc(factory, tmp_path, capsys))
        return await real(*args, **kwargs)

    monkeypatch.setattr(classfit.crud.attachment, "insert_attachment", gc_first)
    await _file(db_session, tmp_path, x, sid, "b.pdf", b)
    (during,) = seen
    assert sha_b not in during["candidates"] and sha_b not in during["deleted"]
    assert during["deleted"] == [sha_c]
    assert not path_for(tmp_path, sha_c).exists()

    assert await _rows_by_sha(db_session, sha_b) == 1  # 넣기가 끝나면 행이 있다
    after = await _gc(factory, tmp_path, capsys)
    assert sha_b not in after["deleted"] and path_for(tmp_path, sha_b).is_file()

    # 롤백한 업로드: 바이트는 참조 0 이지만 mtime 이 새로워 남고, 유예가 지나면 지워진다
    nested = await db_session.begin_nested()
    await _file(db_session, tmp_path, x, sid, "d.pdf", d)
    await nested.rollback()
    assert await _rows_by_sha(db_session, sha_d) == 0
    kept = await _gc(factory, tmp_path, capsys)
    assert sha_d not in kept["candidates"] and path_for(tmp_path, sha_d).is_file()
    _age(path_for(tmp_path, sha_d), 25)
    gone = await _gc(factory, tmp_path, capsys)
    assert gone["deleted"] == [sha_d]
    assert path_for(tmp_path, sha_b).is_file()


async def test_gc_owner_delete_cascade(
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    x = await make_instructor(
        db_session,
        Settings(_env_file=None),
        email="gc-cascade-x@example.com",
        status="approved",
    )
    pool = await make_pool_course(db_session, source="ax")
    await capability_files(
        db_session, tmp_path, instructor_id=x, pool_id=pool.id, kinds=("pdf",)
    )
    _, section = await course_with_section(db_session)
    sid = (await pool_session(db_session, section_id=section.id, pool_id=pool.id)).id
    await sections.patch_session(  # 배정 → T5 기본 강의안 사본(origin capability_file)
        db_session, sid, SessionPatchIn(instructor_id=x), actor="admin:1"
    )
    pdf = await _file(db_session, tmp_path, x, sid, "own.pdf", SAMPLES[".pdf"])
    image = await _file(db_session, tmp_path, x, sid, "a.png", SAMPLES[".png"])
    await my_attachments.add_my_link(
        db_session,
        instructor_id=x,
        session_id=sid,
        title="링크",
        description=None,
        url="https://example.com/gc",
        actor=f"instructor:{x}",
    )
    swap = SAMPLES[".jpg"]

    # 행은 칸 값 튜플로 읽는다 — SAVEPOINT 롤백이 만료시킨 ORM 행을 다시 읽으면 async 에서 오류다
    async def files(*where: Any) -> list[tuple[int, str, str]]:
        """(id, key, sha256), id 순."""
        stmt = (
            select(StoredFile.id, StoredFile.key, StoredFile.sha256)
            .where(*where)
            .order_by(StoredFile.id)
        )
        return [(i, k, sha) for i, k, sha in (await db_session.execute(stmt)).all()]

    async def attachments() -> dict[int, tuple[str, str | None, int | None]]:
        """첨부 id → (kind, origin, file_id), (sort, id) 순."""
        stmt = (
            select(
                SessionAttachment.id,
                SessionAttachment.kind,
                SessionAttachment.origin,
                SessionAttachment.file_id,
            )
            .where(SessionAttachment.session_id == sid)
            .order_by(SessionAttachment.sort, SessionAttachment.id)
        )
        return {i: (k, o, f) for i, k, o, f in (await db_session.execute(stmt)).all()}

    pdf_id, image_id = pdf.id, image.id
    rows = await attachments()
    assert [(kind, origin) for kind, origin, _ in rows.values()] == [
        ("pdf", "capability_file"),
        ("pdf", None),
        ("image", None),
        ("link", None),
    ]
    copy_file = next(iter(rows.values()))[2]
    (original,) = await files(StoredFile.owner_kind == "capability_file")
    (copied,) = await files(StoredFile.id == copy_file)
    (own_pdf,) = await files(StoredFile.id == rows[pdf_id][2])
    (own_image,) = await files(StoredFile.id == rows[image_id][2])
    original_sha, own_pdf_sha, own_image_sha = original[2], own_pdf[2], own_image[2]
    # gc 전에 sha 관계: 사본은 원본과 같은 바이트(행 복제), 강사 업로드·교체 바이트는 서로·원본과 다르다
    assert copied[2] == original_sha == _sha(PDF)
    assert own_pdf_sha != original_sha
    assert own_image_sha not in {original_sha, own_pdf_sha}
    assert _sha(swap) not in {original_sha, own_pdf_sha, own_image_sha}
    actor = f"instructor:{x}"

    # ⓐ 지우기는 첨부와 파일 행을 같은 트랜잭션에서 지운다(롤백이면 함께 돌아온다)
    nested = await db_session.begin_nested()
    await my_attachments.delete_my_attachment(
        db_session, instructor_id=x, attachment_id=pdf_id, actor=actor
    )
    assert await files(StoredFile.id == own_pdf[0]) == []
    assert pdf_id not in await attachments()
    await nested.rollback()
    assert await files(StoredFile.id == own_pdf[0]) == [own_pdf]  # 같은 key
    assert (await attachments())[pdf_id][2] == own_pdf[0]

    # ⓑ 교체는 새 파일 행 → file_id 바꿈 → 옛 파일 행 삭제(같은 트랜잭션)
    owned_by_image = (StoredFile.owner_kind == OWNER, StoredFile.owner_id == image_id)
    nested = await db_session.begin_nested()
    _, new_key, _ = await my_attachment_edit.replace_my_file(
        db_session,
        root=tmp_path,
        max_bytes=MAX,
        instructor_id=x,
        attachment_id=image_id,
        filename="b.jpg",
        data=swap,
        actor=actor,
    )
    assert new_key is not None
    assert await files(StoredFile.id == own_image[0]) == []
    (fresh,) = await files(*owned_by_image)
    assert fresh[1:] == (new_key, _sha(swap))
    assert (await attachments())[image_id][2] == fresh[0]
    await nested.rollback()
    assert await files(*owned_by_image) == [own_image]
    assert (await attachments())[image_id][2] == own_image[0]
    assert await crud_stored_file.get_by_key(db_session, new_key) is None

    # ⓒ 실제로 지우고, 세션 삭제가 남은 첨부 셋과 그 파일 행 둘(link 는 파일 행 없음)을 함께 지운다
    await my_attachments.delete_my_attachment(
        db_session, instructor_id=x, attachment_id=pdf_id, actor=actor
    )
    assert await files(StoredFile.id == own_pdf[0]) == []
    assert len(await files(StoredFile.owner_kind == OWNER)) == 2
    await sections.remove_session(db_session, sid)
    assert await attachments() == {}
    assert await files(StoredFile.owner_kind == OWNER) == []

    # ⓓ 유예가 지난 뒤 gc: 강사 바이트는 지워지고, 사본과 sha 가 같은 원본 바이트는 원본 행이 가리켜 남는다
    for prefix in tmp_path.iterdir():
        for path in prefix.iterdir():
            _age(path, 25)
    result = await _gc(factory, tmp_path, capsys)
    assert set(result["deleted"]) == {own_pdf_sha, own_image_sha, _sha(swap)}
    assert path_for(tmp_path, original_sha).is_file()
    for sha in (own_pdf_sha, own_image_sha, _sha(swap)):
        assert not path_for(tmp_path, sha).exists()
