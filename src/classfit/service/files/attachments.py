"""세션 첨부 넣기·지우기(T2b 계획 결정 viii·ix·xii). flush 까지만.

- pdf: 크기(max_bytes) → 첫 5바이트 %PDF- → 바이트 저장(asyncio.to_thread) → 첨부 행 → stored_file 행
  (owner_kind session_attachment, owner_id 첨부 id) → file_id 채움 → audit. id 가 Identity always 라 첨부 id 를
  미리 못 받아 이 순서다. content_type 은 받은 값이 아니라 application/pdf 로 고정한다.
- link: 첨부 행(url) → audit. 주소 모양(http·https, 2048자)은 끝점의 폼 검증이 먼저 막는다.
- 지우기: 읽어서 audit 칸을 잡고 → 첨부 행 → 그 stored_file 행(crud 한 함수) → audit. 바이트는 gc 몫이다.
- audit 은 action session_attachment.create·.delete · target_type session_attachment · target_id 첨부 id 글자 ·
  detail {session_id, kind} 다(결정 xii). 바이트를 쓴 뒤 행이 롤백되면 바이트는 참조 0 이라 gc 가 지운다.
- 셋 다 첫 DB 쓰기 전에 강의 행을 잠그고(crud.course.lock_course), 잠근 뒤 대상 행을 다시 읽는다(T5 결정 xviii —
  배정의 "첨부 0개" 판정·기본 강의안 사본과 줄 선다, 그 사이 지워졌으면 404). pdf 는 바이트를 쓴 뒤·행을 넣기 전에
  잡는다(최대 50MB 디스크 쓰기 동안 강의 행을 쥐면 같은 강의의 입장이 그만큼 기다린다). 지우기는 crud 지우기의 반환값
  (DELETE … RETURNING)으로 404 를 가린다 — get_attachment 는 session.get 이라 그 사이의 삭제를 못 본다.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import course as crud_course
from classfit.crud import schedule as crud_schedule
from classfit.crud.audit import insert_audit
from classfit.crud.stored_file import insert_stored_file
from classfit.models import SessionAttachment, StoredFile
from classfit.service.files.store import store_bytes

OWNER_KIND = "session_attachment"
PDF_CONTENT_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF-"
_NO_SESSION = "세션이 없습니다"
_NO_ATTACHMENT = "첨부가 없습니다"


class PdfRejected(ValueError):
    """pdf 본문이 받을 수 없는 모양이다. 끝점이 too_large → 413, not_pdf → 422 로 바꾼다."""

    def __init__(self, reason: Literal["too_large", "not_pdf"]) -> None:
        super().__init__(reason)
        self.reason = reason


async def _audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    attachment_id: int,
    session_id: int,
    kind: str,
) -> None:
    await insert_audit(
        session,
        actor=actor,
        action=action,
        target_type=OWNER_KIND,
        target_id=str(attachment_id),
        detail={"session_id": session_id, "kind": kind},
    )


async def add_pdf_attachment(
    session: AsyncSession,
    *,
    root: Path,
    max_bytes: int,
    session_id: int,
    title: str,
    description: str | None,
    data: bytes,
    actor: str,
) -> tuple[SessionAttachment, StoredFile]:
    """크기가 넘거나 %PDF- 로 시작하지 않으면 PdfRejected(아무것도 쓰지 않는다)."""
    if len(data) > max_bytes:
        raise PdfRejected("too_large")
    if not data.startswith(PDF_MAGIC):
        raise PdfRejected("not_pdf")
    sha256 = await asyncio.to_thread(store_bytes, root, data)
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_SESSION)
    if await crud_course.lock_course(session, found[1]) is None:
        raise NotFound(_NO_SESSION)
    if (
        await crud_schedule.get_session_and_course(session, session_id, fresh=True)
        is None
    ):
        raise NotFound(_NO_SESSION)
    row = await crud_attachment.insert_attachment(
        session, session_id=session_id, kind="pdf", title=title, description=description
    )
    stored = await insert_stored_file(
        session,
        sha256=sha256,
        owner_kind=OWNER_KIND,
        owner_id=row.id,
        content_type=PDF_CONTENT_TYPE,
        size=len(data),
    )
    await crud_attachment.set_file_id(session, row, stored.id)
    await _audit(
        session,
        actor=actor,
        action="session_attachment.create",
        attachment_id=row.id,
        session_id=session_id,
        kind="pdf",
    )
    return row, stored


async def add_link_attachment(
    session: AsyncSession,
    *,
    session_id: int,
    title: str,
    description: str | None,
    url: str,
    actor: str,
) -> SessionAttachment:
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_SESSION)
    if await crud_course.lock_course(session, found[1]) is None:
        raise NotFound(_NO_SESSION)
    if (
        await crud_schedule.get_session_and_course(session, session_id, fresh=True)
        is None
    ):
        raise NotFound(_NO_SESSION)
    row = await crud_attachment.insert_attachment(
        session,
        session_id=session_id,
        kind="link",
        title=title,
        description=description,
        url=url,
    )
    await _audit(
        session,
        actor=actor,
        action="session_attachment.create",
        attachment_id=row.id,
        session_id=session_id,
        kind="link",
    )
    return row


async def delete_attachment(
    session: AsyncSession, *, attachment_id: int, actor: str
) -> None:
    """첨부와 그 파일 행을 지운다. 없으면 404."""
    row = await crud_attachment.get_attachment(session, attachment_id)
    if row is None:
        raise NotFound(_NO_ATTACHMENT)
    session_id, kind = row.session_id, row.kind
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    if await crud_course.lock_course(session, found[1]) is None:
        raise NotFound(_NO_ATTACHMENT)
    if not await crud_attachment.delete_attachment(session, attachment_id):
        raise NotFound(_NO_ATTACHMENT)
    await _audit(
        session,
        actor=actor,
        action="session_attachment.delete",
        attachment_id=attachment_id,
        session_id=session_id,
        kind=kind,
    )
