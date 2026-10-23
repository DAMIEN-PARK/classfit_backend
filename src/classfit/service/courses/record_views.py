"""강의 교육 기록 화면 조립(T7 결정 x·xi ①·xxi). 읽기만 한다.

- 강사 my_records: 그 강의에서 내가 맡은 세션만(첫 WHERE session_scope — 남의 세션 기록·사진은 없다). 판정은
  mine.course_for(없음 404 → 배정 세션 없는 강의 403). 관리자 admin_records: 모든 세션(미배정 포함) + 담당 강사 id·이름.
  없는 강의 404. 둘 다 같은 조립이고 주체 범위만 다르다(관리자는 session_scope 가 전부다).
- 세션 항목: 계획(섹션·제목·일차·날짜·일정표 시각 — days.schedule_of 와 같은 계산) · 상태(none·done·ok) · 기록 ·
  사진 앞 RECORD_PHOTOS_MAX 장(올린 순)과 더 있는지. 사진은 세션마다 DB 에서 많아야 RECORD_PHOTOS_MAX + 1 행만 읽는다
  (crud.photo.for_sessions). summary.photos 는 상한 없는 전체 장수다(count_for_sessions).
- 요약: sessions(항목 수) · recorded(done ∨ ok) · confirmed(ok) · missing(일차 날짜 ≤ 오늘 ∧ 기록 없음) · photos.
- 사진 항목은 파일 key 를 싣는다 — href 는 끝점이 service.files.store.href_for 로 단다(courses 는 files 를 모른다,
  service/courses/portal.py 와 같은 까닭). editable 은 강사 주체이고 내가 올린 사진일 때 참(관리자 주체는 거짓),
  seen 은 관리자 확인 표시가 있으면 참이다. 사람 칸은 강사 이름뿐이고 공개 칸은 없다(결정 xxi · r3 §7-7).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import course as crud_course
from classfit.crud import instructor as crud_instructor
from classfit.crud import photo as crud_photo
from classfit.crud import record as crud_record
from classfit.crud.scope import Subject
from classfit.models import Course, Photo
from classfit.service.courses import mine
from classfit.service.courses.days import schedule_of
from classfit.service.courses.records import RecordView
from classfit.service.rules.record import is_past

RECORD_PHOTOS_MAX = 20


@dataclass(frozen=True)
class RecordPhoto:
    """기록 화면의 사진 한 장. key 는 파일 key(href 는 끝점이 단다)."""

    id: int
    session_id: int
    key: str
    size: int
    caption: str | None
    taken_on: dt.date
    uploaded_by: str  # instructor · admin
    uploader_name: str | None  # 강사가 올렸으면 그 강사 이름
    created_at: dt.datetime
    editable: bool  # 강사 주체이고 내가 올린 사진(설명 고치기·지우기 가능)
    seen: bool  # 관리자 확인 표시


@dataclass(frozen=True)
class RecordSession:
    session_id: int
    section_id: int
    section_title: str
    title: str
    day_no: int | None
    date: dt.date | None  # 그 일차 날짜(일차 미정이면 None)
    plan_start: str | None  # 일정표 "HH:MM"(못 정하면 None)
    plan_end: str | None
    status: str  # none · done · ok
    record: RecordView | None
    photos: list[RecordPhoto]
    photos_more: bool
    instructor_id: int | None  # 관리자 응답 칸
    instructor_name: str | None


@dataclass(frozen=True)
class RecordSummary:
    sessions: int
    recorded: int
    confirmed: int
    missing: int
    photos: int


@dataclass(frozen=True)
class CourseRecords:
    course_id: int
    summary: RecordSummary
    sessions: list[RecordSession]


async def my_records(
    session: AsyncSession, subject: Subject, *, course_id: int, today: dt.date
) -> CourseRecords:
    """강사: 그 강의의 내 세션 기록·사진. 없는 강의 404 · 배정 세션 없는 강의 403."""
    course = await mine.course_for(session, subject, course_id)
    return await _assemble(session, subject, course, today)


async def admin_records(
    session: AsyncSession, subject: Subject, *, course_id: int, today: dt.date
) -> CourseRecords:
    """관리자: 그 강의 모든 세션의 기록·사진. 없는 강의 404."""
    course = await crud_course.get_course(session, course_id)
    if course is None:
        raise NotFound("강의가 없습니다")
    return await _assemble(session, subject, course, today)


def _photo(
    photo: Photo, key: str, size: int, subject: Subject, names: dict[int, str]
) -> RecordPhoto:
    by_instructor = photo.uploaded_by_kind == "instructor"
    return RecordPhoto(
        id=photo.id,
        session_id=photo.session_id,
        key=key,
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


async def _assemble(
    session: AsyncSession, subject: Subject, course: Course, today: dt.date
) -> CourseRecords:
    rows = await crud_record.course_rows(session, subject, course.id)
    session_ids = [r.row.id for r in rows]
    schedule = await schedule_of(session, course)
    planned = [item for day in schedule.days for item in day.sessions]
    times = {item.id: (item.start, item.end) for item in planned + schedule.undated}
    photos = await crud_photo.for_sessions(
        session, subject, session_ids, per_session=RECORD_PHOTOS_MAX
    )
    total_photos = await crud_photo.count_for_sessions(session, subject, session_ids)
    people = {r.row.instructor_id for r in rows if r.row.instructor_id is not None}
    people |= {
        r.record.recorded_by_id
        for r in rows
        if r.record is not None and r.record.recorded_by_kind == "instructor"
    }
    people |= {
        p.uploaded_by_id
        for items in photos.values()
        for p, _, _ in items
        if p.uploaded_by_kind == "instructor"
    }
    names = await crud_instructor.names_by_id(session, people)
    sessions: list[RecordSession] = []
    for r in rows:
        record = None
        if r.record is not None:
            by_instructor = r.record.recorded_by_kind == "instructor"
            record = RecordView(
                r.record, names.get(r.record.recorded_by_id) if by_instructor else None
            )
        items = photos.get(r.row.id, [])
        start, end = times.get(r.row.id, (None, None))
        sessions.append(
            RecordSession(
                session_id=r.row.id,
                section_id=r.section.id,
                section_title=r.section.title,
                title=r.row.title,
                day_no=r.row.day_no,
                date=r.day.date if r.day is not None else None,
                plan_start=start,
                plan_end=end,
                status="none" if r.record is None else r.record.status,
                record=record,
                photos=[
                    _photo(p, key, size, subject, names)
                    for p, key, size in items[:RECORD_PHOTOS_MAX]
                ],
                photos_more=len(items) > RECORD_PHOTOS_MAX,
                instructor_id=r.row.instructor_id,
                instructor_name=names.get(r.row.instructor_id)
                if r.row.instructor_id is not None
                else None,
            )
        )
    summary = RecordSummary(
        sessions=len(sessions),
        recorded=sum(s.status != "none" for s in sessions),
        confirmed=sum(s.status == "ok" for s in sessions),
        missing=sum(s.status == "none" and is_past(s.date, today) for s in sessions),
        photos=total_photos,
    )
    return CourseRecords(course_id=course.id, summary=summary, sessions=sessions)
