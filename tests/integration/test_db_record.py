"""교육 기록·사진 표와 crud(T7 결정 iv·vii·ix·xvi): 사진 열람 판정표 · 소유자 삭제가 사진·파일 행·기록을 지움 · 표 제약.
라이브 PG.

행은 crud·service 로 직접 만든다(HTTP 없음). 배정은 운영 경로 sections.patch_session 이다(tests/fixtures/records.py).
시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(T4 대조 실험 13). 표본 sha 는 시험마다 다르다.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import attachment as crud_attachment
from classfit.crud import photo as crud_photo
from classfit.crud import record as crud_record
from classfit.crud import schedule as crud_schedule
from classfit.crud.scope import OWNER_KINDS
from classfit.crud.stored_file import insert_stored_file
from classfit.models import (
    CourseSession,
    Photo,
    Section,
    SessionAttachment,
    SessionRecord,
    StoredFile,
)
from classfit.schemas.course import SessionPatchIn
from classfit.service.auth.sessions import Principal
from classfit.service.courses import remove, sections
from tests.fixtures.assign import approved
from tests.fixtures.instructors import count
from tests.fixtures.records import assigned

DAY = dt.date(2026, 11, 2)


def _settings() -> Settings:
    return Settings(_env_file=None)


def _sha(tag: str) -> str:
    return hashlib.sha256(f"t7-record-{tag}".encode()).hexdigest()


async def _photo(
    db: AsyncSession, *, course_id: int, session_id: int, by_id: int, tag: str
) -> tuple[int, int]:
    """(사진 id, 그 파일 행 id). 넣기 순서는 사진 → stored_file → file_id(service 와 같다)."""
    row = await crud_photo.insert_photo(
        db,
        course_id=course_id,
        session_id=session_id,
        by_kind="instructor",
        by_id=by_id,
        caption=None,
        taken_on=DAY,
    )
    stored = await insert_stored_file(
        db,
        sha256=_sha(tag),
        owner_kind=crud_photo.OWNER_KIND,
        owner_id=row.id,
        content_type="image/png",
        size=16,
    )
    await crud_photo.set_photo_file(db, row, stored.id)
    return row.id, stored.id


async def _record(db: AsyncSession, session_id: int, by_id: int) -> None:
    await crud_record.insert_record(
        db,
        session_id=session_id,
        status="done",
        values={"held_on": DAY, "content": "진행"},
        by_kind="instructor",
        by_id=by_id,
        confirmed_by_id=None,
    )


async def _pdf_attachment(db: AsyncSession, session_id: int, tag: str) -> None:
    row = await crud_attachment.insert_attachment(
        db, session_id=session_id, kind="pdf", title="자료", description=None
    )
    stored = await insert_stored_file(
        db,
        sha256=_sha(f"pdf-{tag}"),
        owner_kind="session_attachment",
        owner_id=row.id,
        content_type="application/pdf",
        size=8,
    )
    await crud_attachment.set_file_id(db, row, stored.id)


async def test_photo_owner_kind_judgment_matrix(db_session: AsyncSession) -> None:
    db = db_session
    judge = OWNER_KINDS["photo"]
    x = await assigned(db, _settings(), email="photo-matrix-x@example.com")
    y, _ = await approved(db, _settings(), email="photo-matrix-y@example.com")
    z, _ = await approved(db, _settings(), email="photo-matrix-z@example.com")
    # Y 는 같은 강의의 다른 세션 담당이다
    other = await crud_schedule.insert_session(
        db, x.section_id, title="다른 교육", day_no=1, slot=2, keywords=[]
    )
    await sections.patch_session(
        db, other.id, SessionPatchIn(instructor_id=y), actor="admin:1"
    )
    pid, _ = await _photo(
        db,
        course_id=x.course_id,
        session_id=x.session_id,
        by_id=x.instructor_id,
        tag="matrix",
    )
    mine = Principal("instructor", x.instructor_id)
    cases = [
        (Principal("admin", 1), True),
        (mine, True),  # 그 세션의 지금 담당
        (Principal("instructor", y), False),  # 같은 강의 다른 세션 담당
        (Principal("instructor", z), False),  # 배정 없는 강사
        (
            Principal("learner", 1, x.course_id),
            False,
        ),  # 같은 강의 수강생(공개 표시 없음)
        (
            Principal("learner", x.instructor_id, x.course_id),
            False,
        ),  # 같은 id 다른 종류
        (Principal("admin", x.instructor_id), True),  # 관리자는 id 와 무관
        (Principal("system", x.instructor_id), False),
    ]
    for subject, expected in cases:
        assert await judge(db, subject, pid) is expected, subject
    assert await judge(db, mine, 999_999_999) is False  # 없는 사진

    # 그 세션을 Y 에게 다시 배정하면 올린 X 는 거짓, 새 담당 Y 는 참
    await sections.patch_session(
        db, x.session_id, SessionPatchIn(instructor_id=y), actor="admin:1"
    )
    assert await judge(db, mine, pid) is False
    assert await judge(db, Principal("instructor", y), pid) is True


async def _left(
    db: AsyncSession, session_id: int, photo_ids: list[int]
) -> dict[str, int]:
    """그 세션의 사진 행 · 그 사진들의 파일 행(owner_kind photo) · 기록 · 첨부 수."""
    return {
        "photos": await count(db, Photo, Photo.session_id == session_id),
        "photo_files": await count(
            db,
            StoredFile,
            StoredFile.owner_kind == "photo",
            StoredFile.owner_id.in_(photo_ids),
        ),
        "records": await count(
            db, SessionRecord, SessionRecord.session_id == session_id
        ),
        "attachments": await count(
            db, SessionAttachment, SessionAttachment.session_id == session_id
        ),
    }


async def test_photo_removed_with_session_section_course(
    db_session: AsyncSession,
) -> None:
    db = db_session
    x = await assigned(db, _settings(), email="photo-remove-x@example.com")
    second_section = await crud_schedule.insert_section(
        db, x.course_id, title="다른 트랙"
    )
    second = await crud_schedule.insert_session(
        db, second_section.id, title="다른 교육", day_no=1, slot=1, keywords=[]
    )
    s1, s2 = x.session_id, second.id
    photos: dict[int, list[int]] = {s1: [], s2: []}
    for sid, n in ((s1, 2), (s2, 1)):  # 여러 행 지우기(id 순 잠금)도 거친다
        for i in range(n):
            pid, _ = await _photo(
                db,
                course_id=x.course_id,
                session_id=sid,
                by_id=x.instructor_id,
                tag=f"remove-{sid}-{i}",
            )
            photos[sid].append(pid)
        await _record(db, sid, x.instructor_id)
        await _pdf_attachment(db, sid, f"remove-{sid}")
    full = {"photos": 2, "photo_files": 2, "records": 1, "attachments": 1}
    gone = dict.fromkeys(full, 0)
    second_full = {"photos": 1, "photo_files": 1, "records": 1, "attachments": 1}
    assert await _left(db, s1, photos[s1]) == full
    assert await _left(db, s2, photos[s2]) == second_full

    for name, deletion, second_after in (
        ("session", lambda: sections.remove_session(db, s1), second_full),
        (
            "section",
            lambda: sections.remove_section(db, x.course_id, x.section_id),
            second_full,
        ),
        ("course", lambda: remove.remove_course(db, x.course_id), gone),
    ):
        tx = await db.begin_nested()
        await deletion()
        assert await _left(db, s1, photos[s1]) == gone, name
        assert await _left(db, s2, photos[s2]) == second_after, name
        assert await count(db, CourseSession, CourseSession.id == s1) == 0, name
        if name == "course":
            assert await count(db, Photo, Photo.course_id == x.course_id) == 0
            assert await count(db, Section, Section.course_id == x.course_id) == 0
        await tx.rollback()
        assert await _left(db, s1, photos[s1]) == full, name
        assert await _left(db, s2, photos[s2]) == second_full, name


async def _violates(
    db: AsyncSession, stmt: Any, sqlstate: str, constraint: str | None = None
) -> None:
    """SAVEPOINT 안에서 stmt 가 sqlstate(그리고 그 제약 이름)로 실패하는지."""
    tx = await db.begin_nested()
    with pytest.raises(IntegrityError) as caught:
        await db.execute(stmt)
    await tx.rollback()
    assert caught.value.orig.sqlstate == sqlstate, caught.value
    if constraint is not None:
        assert caught.value.orig.diag.constraint_name == constraint, caught.value


async def test_record_table_checks(db_session: AsyncSession) -> None:
    db = db_session
    x = await assigned(db, _settings(), email="record-checks-x@example.com")
    records = SessionRecord.__table__
    base = {
        "session_id": x.session_id,
        "status": "done",
        "held_on": DAY,
        "content": "진행",
        "recorded_by_kind": "instructor",
        "recorded_by_id": x.instructor_id,
    }
    confirmed = dt.datetime(2026, 11, 2, 13, tzinfo=dt.UTC)
    bad = [
        ({"status": "none"}, "status"),
        ({"start_time": dt.time(13)}, "time_pair"),
        ({"start_time": dt.time(14), "end_time": dt.time(13)}, "time_order"),
        ({"start_time": dt.time(13), "end_time": dt.time(13)}, "time_order"),
        ({"attendees": -1}, "attendees"),
        ({"attendees": 10_001}, "attendees"),
        ({"content": "   "}, "content"),
        ({"status": "ok"}, "confirmed_status"),  # ok 인데 확인 시각 없음
        ({"status": "ok", "confirmed_at": confirmed}, "confirmed_pair"),  # 확인자 없음
        ({"recorded_by_kind": "learner"}, "recorded_by_kind"),
    ]
    for change, name in bad:
        await _violates(
            db,
            insert(records).values(**(base | change)),
            "23514",
            f"ck_session_record_{name}",
        )
    await _violates(
        db,
        insert(Photo.__table__).values(
            course_id=x.course_id,
            session_id=x.session_id,
            uploaded_by_kind="learner",
            uploaded_by_id=1,
            taken_on=DAY,
        ),
        "23514",
        "ck_photo_uploaded_by_kind",
    )

    # 세션당 1행
    await db.execute(insert(records).values(**base))
    await _violates(
        db, insert(records).values(**base), "23505", "uq_session_record_session_id"
    )
    # 사진 둘이 한 파일 행을 가리킬 수 없다
    pid, file_id = await _photo(
        db,
        course_id=x.course_id,
        session_id=x.session_id,
        by_id=x.instructor_id,
        tag="checks",
    )
    await _violates(
        db,
        insert(Photo.__table__).values(
            course_id=x.course_id,
            session_id=x.session_id,
            file_id=file_id,
            uploaded_by_kind="admin",
            uploaded_by_id=1,
            taken_on=DAY,
        ),
        "23505",
        "uq_photo_file_id",
    )
    # 사진이 남은 세션을 직접 지우면 23503(NO ACTION) — 삭제 경로는 delete_photos_under 를 먼저 부른다
    tx = await db.begin_nested()
    with pytest.raises(IntegrityError) as caught:
        await crud_schedule.delete_session(db, x.session_id)
    await tx.rollback()
    assert caught.value.orig.sqlstate == "23503"
    assert caught.value.orig.diag.constraint_name == "fk_photo_session_id_session"
    # 사진을 지우면 세션 삭제가 기록을 CASCADE 로 같이 지운다
    assert await crud_photo.delete_photo(db, pid) is True
    assert await count(db, StoredFile, StoredFile.id == file_id) == 0
    await crud_schedule.delete_session(db, x.session_id)
    assert await count(db, SessionRecord, SessionRecord.session_id == x.session_id) == 0
