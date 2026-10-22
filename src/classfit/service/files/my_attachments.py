"""강사 첨부 넣기·지우기·목록(T6 결정 i·iii·iv·v·xii·xv·xxii). flush 까지만.

- 판정은 배정 강사만이다: 범위 없는 getter 로 없으면 404 → 그 세션의 담당(instructor_id) ≠ 주체면 403(결정 i·v).
  강사 상태는 다시 보지 않는다(배정은 승인 강사만 받고, 정지는 산 세션을 폐기한다). 담당 강사는 그 세션의 첨부 전부
  (관리자가 넣은 것·기본 강의안 사본 포함)를 지운다.
- 쓰기 셋(add_my_file · add_my_link · delete_my_attachment)은 첫 DB 쓰기 전에 강의 행을 잠그고(crud.course.lock_course),
  잠근 뒤 대상을 populate_existing 으로 다시 읽어 404·403·409 를 다시 판정한다(결정 xv — session.get 은 잠금을 기다린
  사이 커밋된 재배정·삭제를 못 본다). 파일은 바이트를 쓴 뒤 잠근다(최대 100MB 를 쓰는 동안 강의 행을 쥐지 않는다).
  그 사이 세션이 지워지면 404 이고 남은 바이트는 참조 0 이라 gc 몫이다.
- 세션당 첨부 상한(models.attachment.ATTACHMENTS_MAX)은 넣기 둘만 센다: 잠그지 않은 미리 셈(writable_session
  adding=True — 끝점이 본문을 읽기 전, 빠른 409) + 잠근 뒤 셈(정답). 셈의 대상은 그 세션의 첨부 전부다.
- 종류·content_type 은 업로드 파트 값이 아니라 rules.attachment.classify 의 확장자 표다(결정 iii). 끝점이 머리로
  먼저 판정해도 여기서 받은 바이트로 다시 판정한다.
- crud 는 모듈 별칭(crud_*)의 속성으로 부른다 — 행동 시험의 감싸개가 그 모듈 속성을 바꾼다(T5 결정 xviii).
- audit 은 service.files.attachments.audit_attachment 다(actor instructor:<id>, detail {session_id, kind}, 결정 xii).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.core.errors import Conflict, Forbidden, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import attachment_edit as crud_attachment_edit
from classfit.crud import course as crud_course
from classfit.crud import schedule as crud_schedule
from classfit.crud import scope as crud_scope
from classfit.crud import stored_file as crud_stored_file
from classfit.models import CourseSession, SessionAttachment, StoredFile
from classfit.models.attachment import ATTACHMENTS_MAX
from classfit.service.files.attachments import OWNER_KIND, audit_attachment
from classfit.service.files.store import store_bytes
from classfit.service.rules.attachment import HEAD_BYTES, FileRejected, classify

MIB = 1024 * 1024
_NO_SESSION = "세션이 없습니다"
_NO_ATTACHMENT = "첨부가 없습니다"


def upload_limits(settings: Settings) -> dict[str, int]:
    """종류마다 바이트 상한(결정 iv). pdf 는 관리자 첨부와 같은 attachment_pdf_max_mb 다."""
    return {
        "pdf": settings.attachment_pdf_max_mb * MIB,
        "office": settings.attachment_office_max_mb * MIB,
        "html": settings.attachment_zip_max_mb * MIB,
        "image": settings.attachment_image_max_mb * MIB,
    }


def require_mine(row: CourseSession, instructor_id: int) -> None:
    """그 세션의 담당이 instructor_id 가 아니면 Forbidden. 쓰기는 잠그기 전·잠근 뒤 두 번 부른다(my_attachment_edit 도)."""
    if row.instructor_id != instructor_id:
        raise Forbidden("본인 세션의 첨부만 고칠 수 있습니다")


def _full() -> Conflict:
    return Conflict(
        f"세션당 첨부는 {ATTACHMENTS_MAX}개까지입니다", limit=ATTACHMENTS_MAX
    )


def checked(
    filename: str,
    data: bytes,
    max_bytes: Mapping[str, int],
    *,
    expect_kind: str | None = None,
) -> tuple[str, str]:
    """(kind, content_type). 모양이 틀리면 FileRejected(unknown_type·mismatch) → expect_kind(교체)와 종류가 다르면
    kind_changed → 그 종류 상한을 넘으면 too_large 순이다."""
    kind, content_type = classify(filename, data[:HEAD_BYTES])
    if expect_kind is not None and kind != expect_kind:
        raise FileRejected("kind_changed", kind=kind)
    limit = max_bytes[kind]
    if len(data) > limit:
        raise FileRejected("too_large", kind=kind, limit_mb=limit // MIB)
    return kind, content_type


async def writable_session(
    session: AsyncSession, *, instructor_id: int, session_id: int, adding: bool
) -> tuple[CourseSession, int]:
    """잠그지 않은 미리 판정(끝점이 본문을 읽기 전에 부른다): 없으면 404 → 내 세션 아님 403 → adding 이면 상한 409."""
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_SESSION)
    require_mine(found[0], instructor_id)
    if (
        adding
        and await crud_attachment_edit.count_for_session(session, session_id)
        >= ATTACHMENTS_MAX
    ):
        raise _full()
    return found


async def writable_attachment(
    session: AsyncSession, *, instructor_id: int, attachment_id: int
) -> tuple[SessionAttachment, CourseSession, int]:
    """잠그지 않은 미리 판정(교체 끝점이 본문을 읽기 전에 부른다): 없으면 404 → 내 세션의 첨부가 아니면 403."""
    found = await crud_attachment_edit.get_with_session(session, attachment_id)
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    require_mine(found[1], instructor_id)
    return found


async def add_my_file(
    session: AsyncSession,
    *,
    root: Path,
    max_bytes: Mapping[str, int],
    instructor_id: int,
    session_id: int,
    title: str,
    description: str | None,
    filename: str,
    data: bytes,
    actor: str,
) -> tuple[SessionAttachment, StoredFile]:
    """파일 넷 중 하나를 그 세션 끝에 붙인다. 모양·크기가 틀리면 FileRejected(아무것도 쓰지 않는다)."""
    kind, content_type = checked(filename, data, max_bytes)
    sha256 = await asyncio.to_thread(store_bytes, root, data)
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_SESSION)
    if await crud_course.lock_course(session, found[1]) is None:
        raise NotFound(_NO_SESSION)
    found = await crud_schedule.get_session_and_course(session, session_id, fresh=True)
    if found is None:
        raise NotFound(_NO_SESSION)
    require_mine(found[0], instructor_id)
    if (
        await crud_attachment_edit.count_for_session(session, session_id)
        >= ATTACHMENTS_MAX
    ):
        raise _full()
    row = await crud_attachment.insert_attachment(
        session, session_id=session_id, kind=kind, title=title, description=description
    )
    stored = await crud_stored_file.insert_stored_file(
        session,
        sha256=sha256,
        owner_kind=OWNER_KIND,
        owner_id=row.id,
        content_type=content_type,
        size=len(data),
    )
    await crud_attachment.set_file_id(session, row, stored.id)
    await audit_attachment(
        session,
        actor=actor,
        action="session_attachment.create",
        attachment_id=row.id,
        session_id=session_id,
        kind=kind,
    )
    return row, stored


async def add_my_link(
    session: AsyncSession,
    *,
    instructor_id: int,
    session_id: int,
    title: str,
    description: str | None,
    url: str,
    actor: str,
) -> SessionAttachment:
    """링크를 그 세션 끝에 붙인다. 주소 모양(http·https, 2048자)은 끝점의 본문 검증이 먼저 막는다."""
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_SESSION)
    if await crud_course.lock_course(session, found[1]) is None:
        raise NotFound(_NO_SESSION)
    found = await crud_schedule.get_session_and_course(session, session_id, fresh=True)
    if found is None:
        raise NotFound(_NO_SESSION)
    require_mine(found[0], instructor_id)
    if (
        await crud_attachment_edit.count_for_session(session, session_id)
        >= ATTACHMENTS_MAX
    ):
        raise _full()
    row = await crud_attachment.insert_attachment(
        session,
        session_id=session_id,
        kind="link",
        title=title,
        description=description,
        url=url,
    )
    await audit_attachment(
        session,
        actor=actor,
        action="session_attachment.create",
        attachment_id=row.id,
        session_id=session_id,
        kind="link",
    )
    return row


async def delete_my_attachment(
    session: AsyncSession, *, instructor_id: int, attachment_id: int, actor: str
) -> None:
    """내 세션의 첨부와 그 파일 행을 지운다(바이트는 gc 몫). 없으면 404, 내 세션이 아니면 403."""
    found = await crud_attachment_edit.get_with_session(session, attachment_id)
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    require_mine(found[1], instructor_id)
    if await crud_course.lock_course(session, found[2]) is None:
        raise NotFound(_NO_ATTACHMENT)
    found = await crud_attachment_edit.get_with_session(
        session, attachment_id, fresh=True
    )
    if found is None:
        raise NotFound(_NO_ATTACHMENT)
    row, owner, _ = found
    require_mine(owner, instructor_id)
    session_id, kind = row.session_id, row.kind
    if not await crud_attachment.delete_attachment(session, attachment_id):
        raise NotFound(_NO_ATTACHMENT)
    await audit_attachment(
        session,
        actor=actor,
        action="session_attachment.delete",
        attachment_id=attachment_id,
        session_id=session_id,
        kind=kind,
    )


async def list_my_attachments(
    session: AsyncSession, subject: crud_scope.Subject, *, session_id: int
) -> list[crud_attachment.AttachmentRow]:
    """내 세션의 첨부 전부((sort, id) 순). 없으면 404, 내 세션이 아니면 403. 질의의 첫 WHERE 는 session_scope 다."""
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound(_NO_SESSION)
    if not crud_scope.owned_by(subject, found[0].instructor_id):
        raise Forbidden("본인 세션의 첨부만 볼 수 있습니다")
    return await crud_attachment_edit.list_for_my_session(session, subject, session_id)
