"""session_attachment 읽기·쓰기. flush 까지만.

- 넣기는 첨부 행 → stored_file(owner_kind='session_attachment', owner_id=첨부 id) → set_file_id 순서다(service.files.attachments).
- 목록 두 개의 첫 WHERE 는 주체 범위다(crud.scope.course_scope). 세션 → 섹션 → 강의로 잇고, 파일 key·size 를 같이 읽는다.
  잠긴 세션(is_open 거짓)의 처리는 부르는 쪽 몫이다(포털은 카드만, 수강생 첨부 목록은 403).
- 지우기는 첨부 행 → 그 첨부가 소유한 stored_file 행 순서다. file_id FK 가 NO ACTION 이라 거꾸로면 23503 이다.
  바이트는 지우지 않는다(scripts.file_gc 몫).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import ColumnElement, Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.scope import Subject, course_scope
from classfit.models import (
    Course,
    CourseSession,
    Section,
    SessionAttachment,
    StoredFile,
)

OWNER_KIND = "session_attachment"

# (첨부, 파일 key, 파일 크기). link 첨부는 key·size 가 None
AttachmentRow = tuple[SessionAttachment, str | None, int | None]


async def insert_attachment(
    session: AsyncSession,
    *,
    session_id: int,
    kind: str,
    title: str,
    description: str | None,
    url: str | None = None,
    origin: str | None = None,
) -> SessionAttachment:
    """그 세션의 끝에 붙인다(sort = 지금 최댓값 + 1, 처음이면 0). pdf 는 url 없이 넣고 set_file_id 로 잇는다.

    origin 은 기본 강의안 사본의 원본 owner_kind 다(T5 결정 xi). 보통 첨부는 주지 않는다(NULL).
    """
    last = select(func.max(SessionAttachment.sort)).where(
        SessionAttachment.session_id == session_id
    )
    top = await session.scalar(last)
    row = SessionAttachment(
        session_id=session_id,
        kind=kind,
        title=title,
        description=description,
        url=url,
        sort=0 if top is None else top + 1,
        origin=origin,
    )
    session.add(row)
    await session.flush()
    return row


async def set_file_id(
    session: AsyncSession, row: SessionAttachment, file_id: int
) -> SessionAttachment:
    row.file_id = file_id
    await session.flush()
    return row


async def get_attachment(
    session: AsyncSession, attachment_id: int
) -> SessionAttachment | None:
    return await session.get(SessionAttachment, attachment_id)


async def counts_by_session(
    session: AsyncSession, session_ids: Iterable[int]
) -> dict[int, int]:
    """세션마다 첨부 수. 첨부가 없으면 키가 없다(부르는 쪽이 0 으로).

    범위로 걸러진 세션 id 만 받는다 — 강의 범위·잠금을 지난 뒤 부른다.
    """
    ids = list(session_ids)
    if not ids:
        return {}
    stmt = (
        select(SessionAttachment.session_id, func.count())
        .where(SessionAttachment.session_id.in_(ids))
        .group_by(SessionAttachment.session_id)
    )
    return {sid: n for sid, n in (await session.execute(stmt)).all()}


def _listed(subject: Subject) -> Select[Any]:
    return (
        select(SessionAttachment, StoredFile.key, StoredFile.size)
        .join(CourseSession, CourseSession.id == SessionAttachment.session_id)
        .join(Section, Section.id == CourseSession.section_id)
        .join(Course, Course.id == Section.course_id)
        .outerjoin(StoredFile, StoredFile.id == SessionAttachment.file_id)
        .where(course_scope(subject))
    )


async def _rows(session: AsyncSession, stmt: Select[Any]) -> list[AttachmentRow]:
    return [(a, key, size) for a, key, size in (await session.execute(stmt)).all()]


async def list_for_session(
    session: AsyncSession, subject: Subject, session_id: int
) -> list[AttachmentRow]:
    """그 세션의 첨부. 순서는 (sort, id)."""
    stmt = (
        _listed(subject)
        .where(SessionAttachment.session_id == session_id)
        .order_by(SessionAttachment.sort, SessionAttachment.id)
    )
    return await _rows(session, stmt)


async def list_for_course(
    session: AsyncSession, subject: Subject, course_id: int
) -> list[AttachmentRow]:
    """그 강의의 모든 세션 첨부(포털 조립용). 순서는 (session_id, sort, id)."""
    stmt = (
        _listed(subject)
        .where(Section.course_id == course_id)
        .order_by(
            SessionAttachment.session_id, SessionAttachment.sort, SessionAttachment.id
        )
    )
    return await _rows(session, stmt)


async def _delete_where(session: AsyncSession, which: ColumnElement[bool]) -> int:
    """which 에 걸린 첨부 행을 지우고, 그 첨부들이 소유한 stored_file 행도 지운다. 지운 첨부 수."""
    gone = (
        (
            await session.execute(
                delete(SessionAttachment).where(which).returning(SessionAttachment.id)
            )
        )
        .scalars()
        .all()
    )
    if gone:
        await session.execute(
            delete(StoredFile).where(
                StoredFile.owner_kind == OWNER_KIND, StoredFile.owner_id.in_(gone)
            )
        )
    return len(gone)


async def delete_attachment(session: AsyncSession, attachment_id: int) -> bool:
    """지웠으면 True."""
    return await _delete_where(session, SessionAttachment.id == attachment_id) > 0


async def delete_attachments_under(
    session: AsyncSession,
    *,
    course_id: int | None = None,
    section_id: int | None = None,
    session_id: int | None = None,
) -> int:
    """강의·섹션·세션 하나 아래의 첨부와 그 파일 행을 지운다(소유자 삭제 전에, r3 부록 C). 셋 중 하나만 준다."""
    given = [v for v in (course_id, section_id, session_id) if v is not None]
    if len(given) != 1:
        raise ValueError("course_id · section_id · session_id 중 하나만 준다")
    if session_id is not None:
        which = SessionAttachment.session_id == session_id
    elif section_id is not None:
        which = SessionAttachment.session_id.in_(
            select(CourseSession.id).where(CourseSession.section_id == section_id)
        )
    else:
        which = SessionAttachment.session_id.in_(
            select(CourseSession.id)
            .join(Section, Section.id == CourseSession.section_id)
            .where(Section.course_id == course_id)
        )
    return await _delete_where(session, which)
