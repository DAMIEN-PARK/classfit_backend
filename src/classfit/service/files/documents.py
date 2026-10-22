"""강사 서류 넣기·바꾸기·지우기(T3 결정 ix). flush 까지만.

- PDF 만 받는다: 크기(max_bytes) → 첫 5바이트 %PDF- → 바이트 저장(asyncio.to_thread) → stored_file 행
  (owner_kind instructor_document, owner_id = 강사 id, content_type application/pdf 고정) → 서류 행 넣기·바꾸기
  → 바꿨으면 옛 stored_file 행 삭제(같은 트랜잭션, 기획안 8-3 "교체 시 이전 파일 즉시 삭제"). 바이트는 gc 몫이다.
- 매직 바이트·content_type·거절 예외는 세션 첨부(attachments)와 한 원본이다. 거절은 PdfRejected(아무것도 쓰지 않는다).
- 지우기는 서류 행 → 그 stored_file 행 순서다(Design 5절 11). 강사 본인의 일이라 audit 은 없다.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import instructor_document as crud_document
from classfit.crud.stored_file import insert_stored_file
from classfit.models import InstructorDocument
from classfit.service.files.attachments import PDF_CONTENT_TYPE, PDF_MAGIC, PdfRejected
from classfit.service.files.store import store_bytes

OWNER_KIND = "instructor_document"


async def put_document(
    session: AsyncSession,
    *,
    root: Path,
    max_bytes: int,
    instructor_id: int,
    type_id: str,
    data: bytes,
) -> tuple[InstructorDocument, bool]:
    """(서류 행, 새로 만들었는지). 없는 종류면 NotFound(404), 크기·모양이 틀리면 PdfRejected."""
    if await crud_document.get_document_type(session, type_id) is None:
        raise NotFound("서류 종류가 없습니다")
    if len(data) > max_bytes:
        raise PdfRejected("too_large")
    if not data.startswith(PDF_MAGIC):
        raise PdfRejected("not_pdf")
    sha256 = await asyncio.to_thread(store_bytes, root, data)
    stored = await insert_stored_file(
        session,
        sha256=sha256,
        owner_kind=OWNER_KIND,
        owner_id=instructor_id,
        content_type=PDF_CONTENT_TYPE,
        size=len(data),
    )
    row, created, old_file_id = await crud_document.upsert_document(
        session, instructor_id, type_id, stored.id
    )
    if old_file_id is not None:
        await crud_document.delete_stored_file(session, old_file_id)
    return row, created


async def remove_document(
    session: AsyncSession, *, instructor_id: int, type_id: str
) -> bool:
    """그 종류 서류와 파일 행을 지운다. 낸 서류가 없으면 False(끝점이 404)."""
    row = await crud_document.get_document(
        session, instructor_id, type_id, for_update=True
    )
    if row is None:
        return False
    await crud_document.delete_document(session, row)
    return True
