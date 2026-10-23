"""관리자 사진 모아보기·내려받기 목록(T7 결정 xi ②③). 읽기만 한다.

crud/photo.py 가 300줄에 닿아 목록 함수를 나눴다(T7 계획 "바뀌는 파일" crud/photo.py 항목).
- 첫 WHERE 는 course_scope 다(관리자 전부 — 끝점은 관리자 주체로만 부른다). 필터는 고객사(course.client_name 과 같음) ·
  강의 id · 검색어(설명 · 세션 제목 · 강의 제목 · 고객사 · 올린 강사 이름, crud.like 이스케이프) · 새 사진만(seen_at NULL).
- gallery_stmt 는 select(Photo) 라 crud.page.keyset_page 가 (created_at, id) 내림차순으로 쪽을 나눈다. 한 쪽의 파일·강의·
  세션 칸은 gallery_context 가 한 문장으로 읽는다.
- 일차는 둘이다: day_no 는 세션의 지금 일차(모아보기 항목), taken_day_no 는 사진 교육일(taken_on)과 같은 날짜인 그 강의의
  일차다(내려받기 이름 — 세션을 다른 일차로 옮겨도 사진을 찍은 날의 일차를 쓴다). 그런 일차가 없으면 None.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.like import LIKE_ESCAPE, contains_pattern
from classfit.crud.scope import Subject, course_scope
from classfit.models import (
    Course,
    CourseDay,
    CourseSession,
    Instructor,
    Photo,
    StoredFile,
)


@dataclass(frozen=True)
class GalleryContext:
    """사진 한 장의 파일·강의·세션 칸.

    day_no 는 지금 세션의 일차(일차를 지웠으면 None), taken_day_no 는 교육일과 같은 날짜인 그 강의의 일차(없으면 None).
    """

    key: str
    size: int
    content_type: str
    course_title: str
    client_name: str
    session_title: str
    day_no: int | None
    taken_on: dt.date
    taken_day_no: int | None


def gallery_stmt(
    subject: Subject,
    *,
    company: str | None = None,
    course_id: int | None = None,
    q: str | None = None,
    new_only: bool = False,
) -> Select[tuple[Photo]]:
    """모아보기 질의(정렬·커서는 keyset_page 가 단다). 첫 WHERE 는 course_scope."""
    stmt = (
        select(Photo)
        .join(Course, Course.id == Photo.course_id)
        .join(CourseSession, CourseSession.id == Photo.session_id)
        .outerjoin(
            Instructor,
            and_(
                Photo.uploaded_by_kind == "instructor",
                Instructor.id == Photo.uploaded_by_id,
            ),
        )
        .where(course_scope(subject))
    )
    if company is not None:
        stmt = stmt.where(Course.client_name == company)
    if course_id is not None:
        stmt = stmt.where(Photo.course_id == course_id)
    if q is not None:
        pattern = contains_pattern(q)
        searched = (
            Photo.caption,
            CourseSession.title,
            Course.title,
            Course.client_name,
            Instructor.name,
        )
        stmt = stmt.where(
            or_(*(column.ilike(pattern, escape=LIKE_ESCAPE) for column in searched))
        )
    if new_only:
        stmt = stmt.where(Photo.seen_at.is_(None))
    return stmt


async def gallery_context(
    session: AsyncSession, photos: Sequence[Photo]
) -> dict[int, GalleryContext]:
    """사진 id → 칸. 이미 범위 안에서 읽은 사진만 받는다."""
    ids = [p.id for p in photos]
    if not ids:
        return {}
    taken_day = (
        select(CourseDay.day_no)
        .where(CourseDay.course_id == Photo.course_id, CourseDay.date == Photo.taken_on)
        .order_by(CourseDay.day_no)
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(
            Photo.id,
            StoredFile.key,
            StoredFile.size,
            StoredFile.content_type,
            Course.title,
            Course.client_name,
            CourseSession.title,
            CourseSession.day_no,
            Photo.taken_on,
            taken_day,
        )
        .join(StoredFile, StoredFile.id == Photo.file_id)
        .join(Course, Course.id == Photo.course_id)
        .join(CourseSession, CourseSession.id == Photo.session_id)
        .where(Photo.id.in_(ids))
    )
    return {
        pid: GalleryContext(*values)
        for pid, *values in (await session.execute(stmt)).all()
    }


async def by_ids(
    session: AsyncSession, subject: Subject, ids: Collection[int]
) -> list[Photo]:
    """범위 안에서 그 id 의 사진(내려받기 목록). 없는 id 는 빠진다 — 차례는 부르는 쪽이 맞춘다."""
    wanted = list(ids)
    if not wanted:
        return []
    stmt = gallery_stmt(subject).where(Photo.id.in_(wanted))
    return list((await session.scalars(stmt)).all())
