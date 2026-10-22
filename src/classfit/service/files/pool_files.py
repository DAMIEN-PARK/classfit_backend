"""풀 파일 세 종류(pool_course_file · capability_file · curriculum_file) 넣기·지우기(T4 결정 viii·ix). flush 까지만.

- 대상 판정(404 → 403 → 409 → 개수 상한)은 바이트를 읽기 전에 끝점이 service.pool.file_targets 로 한다.
  여기는 (owner_kind, owner_id) 를 받아 쓰기만 한다.
- pdf: 크기(max_bytes) → 첫 5바이트 %PDF- → 바이트 저장(asyncio.to_thread) → 파일 행 → stored_file 행
  (owner_kind = 그 종류, owner_id = 파일 행 id, content_type application/pdf 고정) → file_id 채움 → audit.
  매직 바이트·content_type·거절 예외는 세션 첨부(attachments)와 한 원본이다(T3 결정 ix 와 같은 방식).
- link: 파일 행(url) → audit. 주소 모양은 끝점의 폼 검증이 먼저 막는다.
- 지우기: 파일 행이 없으면 NotFound(404), 주체가 crud.scope.OWNER_KINDS 판정에 걸리면 Forbidden(403),
  아니면 파일 행 → 그 stored_file 행(crud 한 함수) → audit. 바이트는 gc 몫이다.
- audit 은 action <owner_kind>.create·.delete · target_type <owner_kind> · target_id 파일 행 id 글자 ·
  detail {owner_id, kind} 다.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Forbidden, NotFound
from classfit.crud import pool_file as crud_files
from classfit.crud.audit import insert_audit
from classfit.crud.scope import OWNER_KINDS, Subject
from classfit.crud.stored_file import insert_stored_file
from classfit.models import StoredFile
from classfit.service.files.attachments import PDF_CONTENT_TYPE, PDF_MAGIC, PdfRejected
from classfit.service.files.store import store_bytes


async def _audit(
    session: AsyncSession,
    *,
    owner_kind: str,
    action: str,
    actor: str,
    file_row_id: int,
    owner_id: Any,
    kind: str,
) -> None:
    await insert_audit(
        session,
        actor=actor,
        action=f"{owner_kind}.{action}",
        target_type=owner_kind,
        target_id=str(file_row_id),
        detail={"owner_id": owner_id, "kind": kind},
    )


async def add_pdf_file(
    session: AsyncSession,
    *,
    owner_kind: str,
    owner_id: Any,
    root: Path,
    max_bytes: int,
    title: str,
    data: bytes,
    actor: str,
) -> tuple[crud_files.PoolFile, StoredFile]:
    """크기가 넘거나 %PDF- 로 시작하지 않으면 PdfRejected(아무것도 쓰지 않는다)."""
    if len(data) > max_bytes:
        raise PdfRejected("too_large")
    if not data.startswith(PDF_MAGIC):
        raise PdfRejected("not_pdf")
    sha256 = await asyncio.to_thread(store_bytes, root, data)
    row = await crud_files.insert_file_row(
        session, owner_kind, owner_id, kind="pdf", title=title
    )
    stored = await insert_stored_file(
        session,
        sha256=sha256,
        owner_kind=owner_kind,
        owner_id=row.id,
        content_type=PDF_CONTENT_TYPE,
        size=len(data),
    )
    await crud_files.set_file_id(session, row, stored.id)
    await _audit(
        session,
        owner_kind=owner_kind,
        action="create",
        actor=actor,
        file_row_id=row.id,
        owner_id=owner_id,
        kind="pdf",
    )
    return row, stored


async def add_link_file(
    session: AsyncSession,
    *,
    owner_kind: str,
    owner_id: Any,
    title: str,
    url: str,
    actor: str,
) -> crud_files.PoolFile:
    row = await crud_files.insert_file_row(
        session, owner_kind, owner_id, kind="link", title=title, url=url
    )
    await _audit(
        session,
        owner_kind=owner_kind,
        action="create",
        actor=actor,
        file_row_id=row.id,
        owner_id=owner_id,
        kind="link",
    )
    return row


async def remove_file(
    session: AsyncSession,
    *,
    owner_kind: str,
    file_row_id: int,
    subject: Subject,
    actor: str,
) -> None:
    """파일 행과 그 stored_file 행을 지운다. 없으면 NotFound, 주체가 볼 수 없는 파일이면 Forbidden."""
    row = await crud_files.get_file_row(session, owner_kind, file_row_id)
    if row is None:
        raise NotFound("파일이 없습니다")
    if not await OWNER_KINDS[owner_kind](session, subject, file_row_id):
        raise Forbidden("본인의 파일만 지울 수 있습니다")
    owner_id, kind = crud_files.owner_of(row), row.kind
    await crud_files.delete_file_row(session, owner_kind, file_row_id)
    await _audit(
        session,
        owner_kind=owner_kind,
        action="delete",
        actor=actor,
        file_row_id=file_row_id,
        owner_id=owner_id,
        kind=kind,
    )
