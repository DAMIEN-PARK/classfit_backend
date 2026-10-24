"""관리자 홈 셈(T9b 결정 xiv·xv·xvi·xvii·xviii): 셈 == 상세 목록 문장의 길이(COM-004) · 주체별 자기 범위 · 비관리자 거절 ·
홈 service 호출당 실행 문장 둘. 라이브 PG.

상세 목록은 T2a~T9a 의 기존 crud 문장(과 T7 관리자 기록 service)이다 — 셈과 다른 길로 세어 대조한다.
문장 수는 세션 연결(첫 SAVEPOINT)을 먼저 세운 뒤 Connection 의 before_cursor_execute 로 admin_home() 한 번만 감싸 센다
(SAVEPOINT·RELEASE SAVEPOINT·ROLLBACK TO 는 세지 않는다 — codex 2차 #1).
"""

import dataclasses
import datetime as dt
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import Select, event, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.core.errors import Forbidden
from classfit.crud import course as crud_course
from classfit.crud import curriculum as crud_curriculum
from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud import home_admin as crud_home_admin
from classfit.crud import instructor as crud_instructor
from classfit.crud import pool as crud_pool
from classfit.crud import schedule as crud_schedule
from classfit.crud import survey as crud_survey
from classfit.crud.photo_list import gallery_stmt
from classfit.models import AuditLog
from classfit.service.auth.sessions import Principal
from classfit.service.courses import record_views
from classfit.service.home.admin import HOME_AUDIT_MAX, admin_home
from tests.fixtures.inquiry import (
    HOME_TODAY,
    LATER_DAYS,
    ZERO_COUNTS,
    home_fixtures,
)

ADMIN = Principal("admin", 1)
SKIPPED = ("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO")


async def _rows(db: AsyncSession, stmt: Select[Any]) -> list[Any]:
    return list((await db.scalars(stmt)).all())


async def _counts(db: AsyncSession, subject: Any, today: dt.date) -> dict[str, int]:
    return dataclasses.asdict(await crud_home_admin.counts(db, subject, today=today))


async def _listed(db: AsyncSession, today: dt.date) -> dict[str, int]:
    """관리자 셈 여덟을 상세 목록 문장으로 다시 센다."""
    running = await _rows(db, crud_course.list_stmt(ADMIN, "running", False, today))
    prep = await _rows(db, crud_course.list_stmt(ADMIN, "prep", False, today))
    unassigned = 0
    for course in running + prep:
        sessions = await crud_schedule.list_sessions(db, course.id)
        unassigned += sum(s.instructor_id is None for s in sessions)
    missing = 0
    for course in running:
        records = await record_views.admin_records(
            db, ADMIN, course_id=course.id, today=today
        )
        missing += records.summary.missing
    own = crud_pool.list_stmt(ADMIN, source="own", active=True, reviewed=False)
    curricula = crud_curriculum.list_stmt(ADMIN, reviewed=False, active=True)
    surveys = crud_survey.list_stmt(ADMIN, course_id=None, status="open", today=today)
    return {
        "pending_instructors": len(
            await _rows(db, crud_instructor.list_stmt(ADMIN, "pending", None))
        ),
        "running_courses": len(running),
        "unassigned_sessions": unassigned,
        "unreviewed_registrations": len(await _rows(db, own))
        + len(await _rows(db, curricula)),
        "open_surveys": len(await _rows(db, surveys)),
        "diagnoses_in_review": len(
            await _rows(db, crud_diagnosis.list_stmt(ADMIN, "review"))
        ),
        "records_missing": missing,
        "new_photos": len(await _rows(db, gallery_stmt(ADMIN, new_only=True))),
    }


async def test_admin_home_counts_match_lists(db_session: AsyncSession) -> None:
    db = db_session
    expected = await home_fixtures(db, Settings(_env_file=None), today=HOME_TODAY)

    got = await _counts(db, ADMIN, HOME_TODAY)
    assert got == await _listed(db, HOME_TODAY)
    assert got == expected.admin
    later = HOME_TODAY + dt.timedelta(days=LATER_DAYS)
    got_later = await _counts(db, ADMIN, later)
    assert got_later == await _listed(db, later) == expected.admin_later

    # 최근 이력: audit_log 를 직접 (at, id) 내림차순으로 읽은 것과 같다
    recent = await crud_home_admin.recent_audit(db, ADMIN, limit=HOME_AUDIT_MAX)
    direct = await db.scalars(
        select(AuditLog.id)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .limit(HOME_AUDIT_MAX)
    )
    assert [r.id for r in recent] == list(direct) == expected.audit_ids
    assert {f.name for f in dataclasses.fields(recent[0])} == {
        "id",
        "at",
        "actor",
        "action",
        "target_type",
        "target_id",
    }

    # 주체마다 자기 범위만 — 배정 강사 X 는 범위 밖 진행 강의 B 를 세지 않는다(running 1 ≠ 관리자 2)
    instructor = Principal("instructor", expected.instructor_id)
    assert await _counts(db, instructor, HOME_TODAY) == expected.instructor
    assert expected.instructor["running_courses"] != expected.admin["running_courses"]
    learner = Principal("learner", 1, expected.learner_course_id)
    assert await _counts(db, learner, HOME_TODAY) == expected.learner
    for subject in (Principal("other", 1), Principal("learner", 1)):
        assert await _counts(db, subject, HOME_TODAY) == ZERO_COUNTS
    for subject in (instructor, learner):
        assert await crud_home_admin.recent_audit(db, subject, limit=10) == []


@asynccontextmanager
async def _statements(db: AsyncSession) -> AsyncIterator[list[str]]:
    """이 안에서 세션 연결이 실행한 문장(SAVEPOINT 류 제외). 연결·SAVEPOINT 를 먼저 세운 뒤 붙인다."""
    await db.flush()
    conn = await db.connection()
    seen: list[str] = []

    def count(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        if not statement.lstrip().upper().startswith(SKIPPED):
            seen.append(statement)

    event.listen(conn.sync_connection, "before_cursor_execute", count)
    try:
        yield seen
    finally:
        event.remove(conn.sync_connection, "before_cursor_execute", count)


async def test_admin_home_rejects_non_admin_subject(db_session: AsyncSession) -> None:
    db = db_session
    expected = await home_fixtures(db, Settings(_env_file=None), today=HOME_TODAY)
    for subject in (
        Principal("instructor", expected.instructor_id),
        Principal("learner", 1, expected.learner_course_id),
    ):
        async with _statements(db) as seen:
            with pytest.raises(Forbidden):
                await admin_home(db, subject, today=HOME_TODAY)
        assert seen == []  # 질의 없이 거절한다


async def test_admin_home_two_statements(db_session: AsyncSession) -> None:
    db = db_session
    # 빈 DB 도 둘
    async with _statements(db) as seen:
        empty = await admin_home(db, ADMIN, today=HOME_TODAY)
    assert len(seen) == 2, seen
    assert dataclasses.asdict(empty.counts) == ZERO_COUNTS
    assert empty.recent_audit == []

    expected = await home_fixtures(db, Settings(_env_file=None), today=HOME_TODAY)
    async with _statements(db) as seen:
        home = await admin_home(db, ADMIN, today=HOME_TODAY)
    assert len(seen) == 2, seen
    assert dataclasses.asdict(home.counts) == expected.admin
    assert [r.id for r in home.recent_audit] == expected.audit_ids
