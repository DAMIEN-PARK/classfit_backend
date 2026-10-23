"""교육 사진 쓰기·한 건 읽기·기록 화면 목록(T7 결정 vii·viii·x·xiii·xvi). flush 까지만.

- 넣기 순서는 사진 행 → stored_file(owner_kind photo, owner_id = 사진 id) → file_id 채움이다(insert_photo · set_photo_file).
- 사진 여러 행을 잡는 쓰기 둘(확인 표시 mark_seen · 세션·섹션·강의 삭제의 delete_photos_under)은 먼저
  _lock_in_id_order 로 대상 행을 id 오름차순 FOR UPDATE 로 잡는다(결정 xiii — 둘이 같은 순서라 교착 고리가 없다).
  이 파일의 with_for_update 는 그 한 자리다. 사진 한 행만 바꾸는 쓰기(설명 · 하나 지우기)는 강의 잠금 아래 그 한 행이다.
- 지우기는 사진 행 DELETE … RETURNING → 그 사진들이 소유한 stored_file 행이다(crud.attachment._delete_where 꼴). 바이트는
  gc 몫이다.
- 한 건 읽기 get_with_context 는 범위 없는 getter 다(404 → 403 판정용). 기록 화면 목록 for_sessions·count_for_sessions 의
  첫 WHERE 는 session_scope(관리자 전부 · 강사 내 세션, 결정 x)다. 모아보기·내려받기 목록은 crud.photo_list 다.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.scope import Subject, session_scope
from classfit.models import CourseSession, Photo, Section, StoredFile

OWNER_KIND = "photo"
# (사진, stored_file.key, stored_file.size)
PhotoRow = tuple[Photo, str, int]


async def insert_photo(
    session: AsyncSession,
    *,
    course_id: int,
    session_id: int,
    by_kind: str,
    by_id: int,
    caption: str | None,
    taken_on: dt.date,
) -> Photo:
    """file_id 없는 사진 행. 이어서 stored_file 을 넣고 set_photo_file 로 잇는다."""
    row = Photo(
        course_id=course_id,
        session_id=session_id,
        uploaded_by_kind=by_kind,
        uploaded_by_id=by_id,
        caption=caption,
        taken_on=taken_on,
    )
    session.add(row)
    await session.flush()
    return row


async def set_photo_file(session: AsyncSession, row: Photo, file_id: int) -> Photo:
    """file_id 를 채우고 다시 읽는다(created_at·updated_at 이 응답에 쓰인다)."""
    row.file_id = file_id
    await session.flush()
    await session.refresh(row)
    return row


async def get_with_context(
    session: AsyncSession, photo_id: int, *, fresh: bool = False
) -> tuple[Photo, CourseSession, int] | None:
    """(사진, 그 세션, 그 강의 id). 강의 id 는 섹션으로 읽는다. 없으면 None.

    fresh: 강의 행을 잠근 뒤 다시 읽을 때 쓴다(populate_existing — 그 사이 커밋된 재배정·설명을 본다).
    """
    stmt = (
        select(Photo, CourseSession, Section.course_id)
        .join(CourseSession, CourseSession.id == Photo.session_id)
        .join(Section, Section.id == CourseSession.section_id)
        .where(Photo.id == photo_id)
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    found = (await session.execute(stmt)).first()
    return (found[0], found[1], found[2]) if found is not None else None


async def get_row(session: AsyncSession, photo_id: int) -> PhotoRow | None:
    """(사진, 파일 key, 크기). 파일이 이어지지 않은 사진·없는 사진은 None. 범위 없는 getter 다(쓰기 응답용)."""
    stmt = (
        select(Photo, StoredFile.key, StoredFile.size)
        .join(StoredFile, StoredFile.id == Photo.file_id)
        .where(Photo.id == photo_id)
    )
    found = (await session.execute(stmt)).first()
    return (found[0], found[1], found[2]) if found is not None else None


async def set_caption(session: AsyncSession, row: Photo, caption: str | None) -> bool:
    """설명을 바꾸면 True, 같은 값이면 쓰지 않고 False."""
    if row.caption == caption:
        return False
    row.caption = caption
    await session.flush()
    await session.refresh(row)
    return True


async def _lock_in_id_order(
    session: AsyncSession, which: ColumnElement[bool]
) -> list[int]:
    """which 에 걸린 사진 행을 id 오름차순으로 FOR UPDATE 해 잡고 그 id 를 돌려준다(결정 xiii)."""
    stmt = select(Photo.id).where(which).order_by(Photo.id).with_for_update()
    return list((await session.scalars(stmt)).all())


async def _delete_ids(session: AsyncSession, ids: Collection[int]) -> int:
    """그 id 의 사진 행과, 그 사진들이 소유한 stored_file 행을 지운다. 지운 사진 수."""
    if not ids:
        return 0
    gone = (
        (
            await session.execute(
                delete(Photo).where(Photo.id.in_(ids)).returning(Photo.id)
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


async def delete_photo(session: AsyncSession, photo_id: int) -> bool:
    """사진 하나와 그 파일 행. 지웠으면 True(그 사이 지워졌으면 False)."""
    return await _delete_ids(session, [photo_id]) > 0


async def delete_photos_under(
    session: AsyncSession,
    *,
    course_id: int | None = None,
    section_id: int | None = None,
    session_id: int | None = None,
) -> int:
    """강의·섹션·세션 하나 아래의 사진과 그 파일 행을 지운다(소유자 삭제 전에, 결정 xvi). 셋 중 하나만 준다.

    대상 행을 _lock_in_id_order 로 먼저 잡는다(확인 표시와 같은 순서).
    """
    given = [v for v in (course_id, section_id, session_id) if v is not None]
    if len(given) != 1:
        raise ValueError("course_id · section_id · session_id 중 하나만 준다")
    if session_id is not None:
        which = Photo.session_id == session_id
    elif section_id is not None:
        which = Photo.session_id.in_(
            select(CourseSession.id).where(CourseSession.section_id == section_id)
        )
    else:
        which = Photo.course_id == course_id
    ids = await _lock_in_id_order(session, which)
    return await _delete_ids(session, ids)


async def mark_seen(session: AsyncSession, ids: Collection[int]) -> int:
    """준 id 의 사진을 id 순으로 잡은 뒤 seen_at 이 비어 있는 것만 now() 로. 바꾼 수(없는 id 는 빠진다)."""
    locked = await _lock_in_id_order(session, Photo.id.in_(list(ids)))
    if not locked:
        return 0
    stmt = (
        update(Photo)
        .where(Photo.id.in_(locked), Photo.seen_at.is_(None))
        .values(seen_at=func.now(), updated_at=func.now())
        .returning(Photo.id)
    )
    return len((await session.execute(stmt)).scalars().all())


async def for_sessions(
    session: AsyncSession,
    subject: Subject,
    session_ids: Collection[int],
    *,
    per_session: int,
) -> dict[int, list[PhotoRow]]:
    """세션마다 올린 순(created_at, id) 앞 per_session + 1 장(더 있는지 보려고 한 장 더). 사진 없는 세션은 빈 목록.

    첫 WHERE session_scope + 요청 세션으로 좁힌 안쪽 질의에서 세션별 차례(row_number)를 매기고, 바깥에서 그 차례로 자른다
    — 세션마다 많아야 per_session + 1 행만 읽는다.
    """
    wanted = list(session_ids)
    result: dict[int, list[PhotoRow]] = {sid: [] for sid in wanted}
    if not wanted:
        return result
    ranked = (
        select(
            Photo.id.label("id"),
            func.row_number()
            .over(partition_by=Photo.session_id, order_by=(Photo.created_at, Photo.id))
            .label("n"),
        )
        .join(CourseSession, CourseSession.id == Photo.session_id)
        .where(session_scope(subject))
        .where(Photo.session_id.in_(wanted))
        .subquery()
    )
    stmt = (
        select(Photo, StoredFile.key, StoredFile.size)
        .join(ranked, ranked.c.id == Photo.id)
        .join(StoredFile, StoredFile.id == Photo.file_id)
        .where(ranked.c.n <= per_session + 1)
        .order_by(Photo.session_id, Photo.created_at, Photo.id)
    )
    for row, key, size in (await session.execute(stmt)).all():
        result[row.session_id].append((row, key, size))
    return result


async def count_for_sessions(
    session: AsyncSession, subject: Subject, session_ids: Collection[int]
) -> int:
    """주체 범위(첫 WHERE session_scope) 안 그 세션들의 사진 전체 장수(상한 없음 — 기록 목록 summary.photos)."""
    wanted = list(session_ids)
    if not wanted:
        return 0
    stmt = (
        select(func.count(Photo.id))
        .join(CourseSession, CourseSession.id == Photo.session_id)
        .where(session_scope(subject))
        .where(Photo.session_id.in_(wanted))
    )
    return await session.scalar(stmt) or 0
