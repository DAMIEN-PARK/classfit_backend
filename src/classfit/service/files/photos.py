"""교육 사진 올리기·설명 고치기·지우기(T7 결정 vii·viii·xii·xiii). flush 까지만.

- 올리기는 그 세션의 지금 담당 강사 ∧ 지난 차시(그 세션 일차 날짜 ≤ 오늘)만이다: 없음 404 → 남의 세션·미배정 403 →
  일차 미정·예정 차시 409. 끝점은 본문을 읽기 전에 writable_session(잠그지 않은 미리 판정)을 부른다.
- 종류는 rules.attachment.classify(확장자 표 + 첫 바이트)로 정하고 image(png·jpg·jpeg·webp)가 아니면
  FileRejected("unknown_type", kind=그 종류) — 사진 자리에서는 받지 않는 종류다. 크기가 상한(attachment_image_max_mb)을
  넘으면 FileRejected("too_large", kind="image", limit_mb=상한). content_type 은 받은 값이 아니라 표 값이다.
- 설명 고치기·지우기는 담당 강사 ∧ 내가 올린 사진만(남의 사진 403 — 재배정으로 내 세션이 아니게 되면 내 사진도 403).
  관리자는 지우기만(올리기·설명 고치기 끝점은 1차에 없다, 결정 viii).
- 쓰기 넷은 첫 DB 쓰기 전에 강의 행을 잠그고(crud.course.lock_course), 잠근 뒤 세션·사진을 populate_existing 으로 다시
  읽어 404·403·409 를 다시 판정한다(결정 xiii). 올리기는 바이트를 쓴 뒤 잠근다(10MB 를 쓰는 동안 강의 행을 쥐지 않는다 —
  그 사이 세션이 지워지면 404 이고 남은 바이트는 참조 0 이라 gc 몫). 넣기 순서는 사진 → stored_file → file_id 다.
  지우기는 사진 행 → 그 파일 행(DELETE … RETURNING 으로 그 사이 지워졌으면 404)이고 바이트는 gc 몫이다.
- audit 은 쓰기마다 1행(target photo · 사진 id): photo.create·photo.delete(detail {session_id}) · photo.update(detail
  {fields: ["caption"]}, 같은 값이면 없음). 설명·바이트·파일 이름은 싣지 않는다.
- crud 는 모듈 별칭(crud_*)의 속성으로 부른다 — 행동 시험의 감싸개·정적 시험이 그 꼴을 본다(T5 결정 xviii).
"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, Forbidden, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import photo as crud_photo
from classfit.crud import record as crud_record
from classfit.crud import stored_file as crud_stored_file
from classfit.models import CourseSession, Photo, StoredFile
from classfit.service.files.store import store_bytes
from classfit.service.rules.attachment import HEAD_BYTES, FileRejected, classify
from classfit.service.rules.record import is_past

MIB = 1024 * 1024
NO_SESSION = "세션이 없습니다"
NOT_MY_SESSION = "본인 세션에만 사진을 올릴 수 있습니다"
NOT_PAST = "지난 차시에만 사진을 올릴 수 있습니다"
NO_PHOTO = "사진이 없습니다"
NOT_MY_PHOTO = "본인 세션에 본인이 올린 사진만 고치거나 지울 수 있습니다"


def _uploadable(
    context: crud_record.SessionContext | None, instructor_id: int, today: dt.date
) -> crud_record.SessionContext:
    """없으면 NotFound → 내 세션 아님 Forbidden → 일차 미정·예정 차시 Conflict."""
    if context is None:
        raise NotFound(NO_SESSION)
    if context.row.instructor_id != instructor_id:
        raise Forbidden(NOT_MY_SESSION)
    if context.day is None or not is_past(context.day.date, today):
        raise Conflict(NOT_PAST)
    return context


def _found(
    found: tuple[Photo, CourseSession, int] | None, instructor_id: int | None
) -> tuple[Photo, CourseSession, int]:
    """없으면 NotFound. instructor_id 가 있으면 그 세션의 지금 담당 ∧ 내가 올린 사진이 아니면 Forbidden."""
    if found is None:
        raise NotFound(NO_PHOTO)
    photo, row, _ = found
    if instructor_id is not None and not (
        row.instructor_id == instructor_id
        and photo.uploaded_by_kind == "instructor"
        and photo.uploaded_by_id == instructor_id
    ):
        raise Forbidden(NOT_MY_PHOTO)
    return found


def image_checked(filename: str, data: bytes, max_bytes: int) -> str:
    """사진으로 받을 수 있으면 content_type. 아니면 FileRejected(unknown_type·mismatch·too_large)."""
    kind, content_type = classify(filename, data[:HEAD_BYTES])
    if kind != "image":
        raise FileRejected("unknown_type", kind=kind)
    if len(data) > max_bytes:
        raise FileRejected("too_large", kind="image", limit_mb=max_bytes // MIB)
    return content_type


async def writable_session(
    session: AsyncSession, *, instructor_id: int, session_id: int, today: dt.date
) -> crud_record.SessionContext:
    """잠그지 않은 미리 판정(끝점이 본문을 읽기 전에 부른다): 404 → 403 → 409."""
    return _uploadable(
        await crud_record.session_context(session, session_id), instructor_id, today
    )


async def add_my_photo(
    session: AsyncSession,
    *,
    root: Path,
    max_bytes: int,
    instructor_id: int,
    session_id: int,
    caption: str | None,
    filename: str,
    data: bytes,
    today: dt.date,
    actor: str,
) -> tuple[Photo, StoredFile]:
    """사진 한 장을 그 세션에 올린다. 모양·크기가 틀리면 FileRejected(아무것도 쓰지 않는다)."""
    content_type = image_checked(filename, data, max_bytes)
    sha256 = await asyncio.to_thread(store_bytes, root, data)
    context = _uploadable(
        await crud_record.session_context(session, session_id), instructor_id, today
    )
    if await crud_course.lock_course(session, context.course_id) is None:
        raise NotFound(NO_SESSION)
    context = _uploadable(
        await crud_record.session_context(session, session_id, fresh=True),
        instructor_id,
        today,
    )
    assert context.day is not None  # _uploadable 이 일차 미정을 막았다
    photo = await crud_photo.insert_photo(
        session,
        course_id=context.course_id,
        session_id=session_id,
        by_kind="instructor",
        by_id=instructor_id,
        caption=caption,
        taken_on=context.day.date,
    )
    stored = await crud_stored_file.insert_stored_file(
        session,
        sha256=sha256,
        owner_kind=crud_photo.OWNER_KIND,
        owner_id=photo.id,
        content_type=content_type,
        size=len(data),
    )
    photo = await crud_photo.set_photo_file(session, photo, stored.id)
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="photo.create",
        target_type="photo",
        target_id=str(photo.id),
        detail={"session_id": session_id},
    )
    return photo, stored


async def patch_my_photo(
    session: AsyncSession,
    *,
    instructor_id: int,
    photo_id: int,
    caption: str | None,
    actor: str,
) -> crud_photo.PhotoRow:
    """설명 고치기(None 은 지움). 같은 값이면 쓰지 않는다. (사진, 파일 key, 크기)."""
    _, _, course_id = _found(
        await crud_photo.get_with_context(session, photo_id), instructor_id
    )
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(NO_PHOTO)
    photo, _, _ = _found(
        await crud_photo.get_with_context(session, photo_id, fresh=True),
        instructor_id,
    )
    if await crud_photo.set_caption(session, photo, caption):
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="photo.update",
            target_type="photo",
            target_id=str(photo_id),
            detail={"fields": ["caption"]},
        )
    item = await crud_photo.get_row(session, photo_id)
    assert item is not None  # 같은 트랜잭션에서 잠근 강의 아래 방금 읽은 사진이다
    return item


async def delete_my_photo(
    session: AsyncSession, *, instructor_id: int, photo_id: int, actor: str
) -> None:
    """내가 올린 사진 하나와 그 파일 행을 지운다."""
    _, _, course_id = _found(
        await crud_photo.get_with_context(session, photo_id), instructor_id
    )
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(NO_PHOTO)
    photo, _, _ = _found(
        await crud_photo.get_with_context(session, photo_id, fresh=True),
        instructor_id,
    )
    session_id = photo.session_id
    if not await crud_photo.delete_photo(session, photo_id):
        raise NotFound(NO_PHOTO)
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="photo.delete",
        target_type="photo",
        target_id=str(photo_id),
        detail={"session_id": session_id},
    )


async def delete_photo_as_admin(
    session: AsyncSession, *, photo_id: int, actor: str
) -> None:
    """관리자: 아무 사진이나 하나와 그 파일 행을 지운다."""
    _, _, course_id = _found(await crud_photo.get_with_context(session, photo_id), None)
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(NO_PHOTO)
    photo, _, _ = _found(
        await crud_photo.get_with_context(session, photo_id, fresh=True), None
    )
    session_id = photo.session_id
    if not await crud_photo.delete_photo(session, photo_id):
        raise NotFound(NO_PHOTO)
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="photo.delete",
        target_type="photo",
        target_id=str(photo_id),
        detail={"session_id": session_id},
    )
