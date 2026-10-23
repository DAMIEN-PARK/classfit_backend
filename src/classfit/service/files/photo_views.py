"""교육 사진 응답 조립 · 관리자 모아보기 · 내려받기 목록 · 확인 표시(T7 결정 xi ②③④·xiii·xxi). 확인 표시만 쓴다.

- 모아보기 gallery: 평평한 키셋 목록((created_at, id) 내림차순, crud.page.keyset_page). 첫 WHERE 는 course_scope 다
  (crud.photo_list.gallery_stmt). 항목에 고객사·강의·세션·일차(세션의 지금 일차)·교육일을 실어 화면이 회사 → 강의 →
  교육일로 묶는다.
- 내려받기 목록 download_list: 준 id 차례(겹친 id 는 하나로)대로 {id, href, filename}. 바이트는 GET /v1/files/{key}
  로만 준다(ADR-003). 이름은 rules.photo.download_name 이고 차례 번호는 목록 안에서 1부터다. 이름의 일차는 사진
  교육일(taken_on)과 같은 날짜인 그 강의의 일차다(세션을 옮겨도 찍은 날의 일차, 그런 일차가 없으면 일차 마디 없음).
  범위 밖·없는 id 는 missing.
- 쪽(keyset_page)과 그 쪽의 파일·강의·세션 칸(gallery_context)은 두 문장이다. READ COMMITTED 라 그 사이 지워져 커밋된
  사진은 두 번째 문장에 없으므로 목록에서 뺀다 — next_cursor·has_more 는 keyset_page 가 준 원래 쪽 값 그대로라 다음 쪽이
  어긋나지 않는다(한 쪽이 limit 보다 짧을 수 있다). 내려받기 목록은 같은 경우를 missing 에 담는다.
- 깨진 커서는 keyset_page 호출만 감싸 InvalidCursor(ValueError)로 바꾼다 — 끝점은 그것만 422 loc ["query","cursor"]
  로 바꾼다(T6 service/courses/my_views.py 꼴. 구성요소가 달라 그 이름을 들이지 않고 따로 둔다).
- 확인 표시 mark_seen 은 강의를 잠그지 않는다(여러 강의에 걸치고 seen_at 한 칸만 바꾼다). 대신 crud.photo.mark_seen 이
  대상 사진 행을 id 오름차순으로 잡는다 — 세션·섹션·강의 삭제의 사진 지우기와 같은 순서라 교착 고리가 없다(결정 xiii).
  audit 은 없다(결정 xii).
- 사람 칸은 올린 강사 이름 하나다. 공개 칸은 없다(r3 §7-7).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import instructor as crud_instructor
from classfit.crud import page as crud_page
from classfit.crud import photo as crud_photo
from classfit.crud import photo_list as crud_photo_list
from classfit.crud.scope import Subject
from classfit.models import Photo
from classfit.service.files.store import href_for
from classfit.service.rules.photo import download_name


class InvalidCursor(ValueError):
    """깨진 키셋 커서. 끝점은 이 예외만 422 loc ["query","cursor"] 로 바꾼다."""


@dataclass(frozen=True)
class PhotoView:
    """사진 한 장. 속성 이름이 응답 칸이다(강사 응답은 editable, 관리자 응답은 seen 을 쓴다)."""

    id: int
    session_id: int
    href: str
    size: int
    caption: str | None
    taken_on: dt.date
    uploaded_by: str  # instructor · admin
    uploader_name: str | None  # 강사가 올렸으면 그 강사 이름
    created_at: dt.datetime
    editable: bool  # 강사 주체이고 내가 올린 사진
    seen: bool  # 관리자 확인 표시


@dataclass(frozen=True)
class GalleryItem(PhotoView):
    course_id: int
    course_title: str
    client_name: str
    session_title: str
    day_no: int | None  # 지금 세션의 일차(일차를 지웠으면 None)


@dataclass(frozen=True)
class GalleryPage:
    items: list[GalleryItem]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class DownloadItem:
    id: int
    href: str
    filename: str


def _view(
    photo: Photo, key: str, size: int, subject: Subject, names: dict[int, str]
) -> PhotoView:
    by_instructor = photo.uploaded_by_kind == "instructor"
    return PhotoView(
        id=photo.id,
        session_id=photo.session_id,
        href=href_for(key),
        size=size,
        caption=photo.caption,
        taken_on=photo.taken_on,
        uploaded_by=photo.uploaded_by_kind,
        uploader_name=names.get(photo.uploaded_by_id) if by_instructor else None,
        created_at=photo.created_at,
        editable=subject.type == "instructor"
        and by_instructor
        and photo.uploaded_by_id == subject.id,
        seen=photo.seen_at is not None,
    )


async def _names(session: AsyncSession, photos: Iterable[Photo]) -> dict[int, str]:
    return await crud_instructor.names_by_id(
        session,
        [p.uploaded_by_id for p in photos if p.uploaded_by_kind == "instructor"],
    )


async def photo_view(
    session: AsyncSession, subject: Subject, item: crud_photo.PhotoRow
) -> PhotoView:
    """(사진, 파일 key, 크기) 하나의 응답 모양. 올리기·설명 고치기 응답에 쓴다."""
    photo, key, size = item
    names = await _names(session, [photo])
    return _view(photo, key, size, subject, names)


def _unique(ids: Iterable[int]) -> list[int]:
    return list(dict.fromkeys(ids))


async def gallery(
    session: AsyncSession,
    subject: Subject,
    *,
    company: str | None,
    course_id: int | None,
    q: str | None,
    new_only: bool,
    cursor: str | None,
    limit: int,
) -> GalleryPage:
    """관리자 사진 모아보기 한 쪽. 깨진 커서는 InvalidCursor."""
    stmt = crud_photo_list.gallery_stmt(
        subject, company=company, course_id=course_id, q=q, new_only=new_only
    )
    try:
        photos, next_cursor, has_more = await crud_page.keyset_page(
            session, stmt, cursor, limit
        )
    except ValueError as exc:
        raise InvalidCursor(str(exc)) from exc
    context = await crud_photo_list.gallery_context(session, photos)
    names = await _names(session, photos)
    items = []
    for photo in photos:
        c = context.get(photo.id)
        if c is None:
            continue  # 두 질의 사이에 지워졌다(READ COMMITTED) — 빼고, 커서는 원래 쪽 그대로
        items.append(
            GalleryItem(
                **asdict(_view(photo, c.key, c.size, subject, names)),
                course_id=photo.course_id,
                course_title=c.course_title,
                client_name=c.client_name,
                session_title=c.session_title,
                day_no=c.day_no,
            )
        )
    return GalleryPage(items=items, next_cursor=next_cursor, has_more=has_more)


async def download_list(
    session: AsyncSession, subject: Subject, *, ids: Iterable[int]
) -> tuple[list[DownloadItem], list[int]]:
    """(내려받기 항목 — 준 차례, 찾지 못한 id — 준 차례)."""
    wanted = _unique(ids)
    photos = {p.id: p for p in await crud_photo_list.by_ids(session, subject, wanted)}
    context = await crud_photo_list.gallery_context(session, list(photos.values()))
    items: list[DownloadItem] = []
    missing: list[int] = []
    for pid in wanted:
        c = context.get(pid)
        if pid not in photos or c is None:
            missing.append(pid)
            continue
        name = download_name(
            c.client_name, c.taken_on, c.taken_day_no, len(items) + 1, c.content_type
        )
        items.append(DownloadItem(id=pid, href=href_for(c.key), filename=name))
    return items, missing


async def mark_seen(session: AsyncSession, *, ids: Iterable[int]) -> int:
    """준 id 가운데 아직 확인 표시가 없는 사진을 확인으로. 바꾼 수. 강의를 잠그지 않는다."""
    return await crud_photo.mark_seen(session, _unique(ids))
