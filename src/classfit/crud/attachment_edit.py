"""강사 첨부 쓰기·목록(T6). 넣기·지우기는 crud.attachment 를 같이 쓴다 — service 별칭 crud_attachment·crud_attachment_edit 둘.
flush 까지만.

- get_with_session 은 범위 없는 getter 다(첨부·세션·강의 id 한 문장). 판정은 service 가 404 → 403 으로 한다.
  fresh 면 populate_existing 이다 — 강의 행을 잠근 뒤 다시 읽을 때 identity map 의 옛 file_id·instructor_id 가
  잠금을 기다린 사이 커밋된 값을 가리지 않게 덮어 읽는다(T5 결정 xviii).
- swap_file 은 교체다: 옛 file_id 를 잡아 두고 → file_id 를 새 행으로 · origin NULL → flush → 옛 stored_file 행 삭제.
  file_id FK 가 NO ACTION 이라 바꾼 뒤 지운다(T6 결정 vii). 옛 행은 부르는 쪽이 잠근 뒤 읽은 file_id 다.
- list_for_my_session 의 첫 WHERE 는 session_scope(주체)다(결정 xxii ①) — 강사는 자기가 맡은 세션만이라
  403 미리 판정을 건너뛰어도 남의 세션은 0행이다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.attachment import OWNER_KIND, AttachmentRow
from classfit.crud.scope import Subject, session_scope
from classfit.models import CourseSession, Section, SessionAttachment, StoredFile


async def get_with_session(
    session: AsyncSession, attachment_id: int, *, fresh: bool = False
) -> tuple[SessionAttachment, CourseSession, int] | None:
    """(첨부, 그 세션, 강의 id). 없으면 None."""
    stmt = (
        select(SessionAttachment, CourseSession, Section.course_id)
        .join(CourseSession, CourseSession.id == SessionAttachment.session_id)
        .join(Section, Section.id == CourseSession.section_id)
        .where(SessionAttachment.id == attachment_id)
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    found = (await session.execute(stmt)).first()
    return None if found is None else (found[0], found[1], found[2])


async def with_file(session: AsyncSession, row: SessionAttachment) -> AttachmentRow:
    """(첨부, 파일 key, 파일 크기) — 응답 모양. link·파일 없는 행은 key·size 가 None."""
    if row.file_id is None:
        return row, None, None
    found = (
        await session.execute(
            select(StoredFile.key, StoredFile.size).where(StoredFile.id == row.file_id)
        )
    ).first()
    return (row, None, None) if found is None else (row, found[0], found[1])


async def count_for_session(session: AsyncSession, session_id: int) -> int:
    """그 세션의 첨부 수(관리자 것·사본 포함, 상한 판정)."""
    stmt = (
        select(func.count())
        .select_from(SessionAttachment)
        .where(SessionAttachment.session_id == session_id)
    )
    return await session.scalar(stmt) or 0


async def rows_for_session(
    session: AsyncSession, session_id: int
) -> list[SessionAttachment]:
    """그 세션의 첨부, (sort, id) 순. 잠근 뒤 순서를 다시 매기기 전에 읽는 자리라 populate_existing 이다."""
    stmt = (
        select(SessionAttachment)
        .where(SessionAttachment.session_id == session_id)
        .order_by(SessionAttachment.sort, SessionAttachment.id)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def set_sorts(session: AsyncSession, rows: Sequence[SessionAttachment]) -> None:
    """준 차례대로 sort 를 0..n-1 로 매기고 flush. 이미 그 값인 행은 건드리지 않는다."""
    for n, row in enumerate(rows):
        if row.sort != n:
            row.sort = n
    await session.flush()


async def apply_changes(
    session: AsyncSession, row: SessionAttachment, fields: dict[str, Any]
) -> list[str]:
    """준 칸 중 현재 값과 다른 칸만 쓰고 flush 뒤 다시 읽는다. 바뀐 칸 이름(정렬). 바뀐 칸이 없으면 쓰지 않는다."""
    changed = {k: v for k, v in fields.items() if getattr(row, k) != v}
    for name, value in changed.items():
        setattr(row, name, value)
    if changed:
        await session.flush()
        await session.refresh(row)
    return sorted(changed)


async def swap_file(session: AsyncSession, row: SessionAttachment, file_id: int) -> int:
    """file_id 를 새 파일 행으로 바꾸고 origin 을 비운 뒤, 이 첨부가 소유한 옛 stored_file 행을 지운다. 지운 수."""
    old = row.file_id
    row.file_id = file_id
    row.origin = None
    await session.flush()
    await session.refresh(row)
    if old is None:
        return 0
    gone = await session.execute(
        delete(StoredFile)
        .where(
            StoredFile.id == old,
            StoredFile.owner_kind == OWNER_KIND,
            StoredFile.owner_id == row.id,
        )
        .returning(StoredFile.id)
    )
    return len(gone.scalars().all())


async def list_for_my_session(
    session: AsyncSession, subject: Subject, session_id: int
) -> list[AttachmentRow]:
    """그 세션의 첨부와 파일 key·size, (sort, id) 순. 첫 WHERE 는 session_scope(주체)."""
    stmt = (
        select(SessionAttachment, StoredFile.key, StoredFile.size)
        .join(CourseSession, CourseSession.id == SessionAttachment.session_id)
        .outerjoin(StoredFile, StoredFile.id == SessionAttachment.file_id)
        .where(session_scope(subject))
        .where(SessionAttachment.session_id == session_id)
        .order_by(SessionAttachment.sort, SessionAttachment.id)
    )
    return [(a, key, size) for a, key, size in (await session.execute(stmt)).all()]
