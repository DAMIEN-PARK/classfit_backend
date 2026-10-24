"""관리자 홈 셈 여덟과 최근 처리 이력(T9b 결정 xiii·xiv·xv·xvi·xviii). 읽기만 한다.

셈마다 첫 WHERE 는 그 표의 주체 범위(Design 5절 3)이고, 조건은 카드가 이어지는 상세 목록 문장과 같다(요구정의서 COM-004 —
요약 건수 = 상세 목록의 조건·건수). 오늘은 인자로 받는다(Design 5절 15).
  1 승인 대기 강사 — instructor_scope ∧ status 'pending'(crud.instructor.list_stmt(subject, "pending", None))
  2 진행 중 강의 — course_scope ∧ 보관 아님 ∧ course_status_sql(today) 'running'(crud.course.list_stmt(…, "running", False, today))
  3 미배정 세션 — course_scope ∧ 보관 아님 ∧ 상태 ≠ 'ended' ∧ session.instructor_id IS NULL(그 강의들의 일정 list_sessions)
  4 미검토 강사 등록 — own_course_scope ∧ source 'own' ∧ active ∧ NOT reviewed + curriculum_scope ∧ active ∧ NOT reviewed
    (crud.pool.list_stmt(source="own", active=True, reviewed=False) + crud.curriculum.list_stmt(reviewed=False, active=True))
  5 열린 설문 — course_scope ∧ survey_status_sql(today) 'open'(crud.survey.list_stmt(…, status="open"))
  6 진단 검토 대기 — crud.diagnosis.list_stmt(subject, "review") 를 그대로 센다(company_scope ∧ status 'review', 결정 xxvii)
  7 교육 기록 미기록 — course_scope ∧ 보관 아님 ∧ 'running' ∧ 일차 날짜 ≤ today ∧ 기록 없음(T7 관리자 기록 summary.missing 합,
    결정 xv — T7 강사 홈의 "종료 아님" 과 달리 진행 중만)
  8 새 사진 — crud.photo_list.gallery_stmt(subject, new_only=True) 를 그대로 센다(course_scope ∧ seen_at IS NULL — 모아보기
    GET /v1/admin/photos?new_only=true 와 같은 문장, codex 구현 리뷰 1차 ②)
  9 최근 처리 이력 — audit_log (at, id) 내림차순 limit. 관리자 전용 표라 범위 함수가 없고, 그 밖 주체는 질의 없이 빈 목록이다.
    detail(반려 사유 같은 자유 글)은 읽지 않는다(결정 xiii).
셈 여덟은 scalar subquery 여덟을 가진 SELECT 한 문장(counts)이고 이력은 한 문장(recent_audit)이다 — 홈 한 번에 문장 둘(결정 xviii).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud.course import course_status_sql
from classfit.crud.photo_list import gallery_stmt
from classfit.crud.record import _same_day
from classfit.crud.scope import (
    Subject,
    course_scope,
    curriculum_scope,
    instructor_scope,
    own_course_scope,
)
from classfit.crud.survey import survey_status_sql
from classfit.models import (
    AuditLog,
    Course,
    CourseDay,
    CourseSession,
    Curriculum,
    Instructor,
    PoolCourse,
    Section,
    SessionRecord,
    Survey,
)


@dataclass(frozen=True)
class HomeCounts:
    pending_instructors: int
    running_courses: int
    unassigned_sessions: int
    unreviewed_registrations: int
    open_surveys: int
    diagnoses_in_review: int
    records_missing: int
    new_photos: int


@dataclass(frozen=True)
class AuditRow:
    id: int
    at: dt.datetime
    actor: str
    action: str
    target_type: str
    target_id: str | None


def _course_sessions() -> Select[tuple[int]]:
    """세션 ⋈ 섹션 ⋈ 강의 위의 셈(3·7)."""
    return (
        select(func.count())
        .select_from(CourseSession)
        .join(Section, Section.id == CourseSession.section_id)
        .join(Course, Course.id == Section.course_id)
    )


def _pending_instructors(subject: Subject) -> Select[tuple[int]]:
    return (
        select(func.count())
        .select_from(Instructor)
        .where(instructor_scope(subject), Instructor.status == "pending")
    )


def _running_courses(subject: Subject, today: dt.date) -> Select[tuple[int]]:
    return (
        select(func.count())
        .select_from(Course)
        .where(
            course_scope(subject),
            Course.archived_at.is_(None),
            course_status_sql(today) == "running",
        )
    )


def _unassigned_sessions(subject: Subject, today: dt.date) -> Select[tuple[int]]:
    return _course_sessions().where(
        course_scope(subject),
        Course.archived_at.is_(None),
        course_status_sql(today) != "ended",
        CourseSession.instructor_id.is_(None),
    )


def _unreviewed_registrations(subject: Subject) -> Select[tuple[int]]:
    own = (
        select(func.count())
        .select_from(PoolCourse)
        .where(
            own_course_scope(subject),
            PoolCourse.source == "own",
            PoolCourse.active.is_(True),
            PoolCourse.reviewed.is_(False),
        )
    )
    curricula = (
        select(func.count())
        .select_from(Curriculum)
        .where(
            curriculum_scope(subject),
            Curriculum.active.is_(True),
            Curriculum.reviewed.is_(False),
        )
    )
    return select(own.scalar_subquery() + curricula.scalar_subquery())


def _open_surveys(subject: Subject, today: dt.date) -> Select[tuple[int]]:
    return (
        select(func.count())
        .select_from(Survey)
        .join(Course, Course.id == Survey.course_id)
        .where(course_scope(subject), survey_status_sql(today) == "open")
    )


def _diagnoses_in_review(subject: Subject) -> Select[tuple[int]]:
    return select(func.count()).select_from(
        crud_diagnosis.list_stmt(subject, "review").subquery()
    )


def _records_missing(subject: Subject, today: dt.date) -> Select[tuple[int]]:
    recorded = exists().where(SessionRecord.session_id == CourseSession.id)
    return (
        _course_sessions()
        .join(CourseDay, _same_day())
        .where(
            course_scope(subject),
            Course.archived_at.is_(None),
            course_status_sql(today) == "running",
            CourseDay.date <= today,
            ~recorded,
        )
    )


def _new_photos(subject: Subject) -> Select[tuple[int]]:
    return select(func.count()).select_from(
        gallery_stmt(subject, new_only=True).subquery()
    )


async def counts(
    session: AsyncSession, subject: Subject, *, today: dt.date
) -> HomeCounts:
    """셈 여덟 — 한 문장(결정 xviii)."""
    builders = (
        _pending_instructors(subject),
        _running_courses(subject, today),
        _unassigned_sessions(subject, today),
        _unreviewed_registrations(subject),
        _open_surveys(subject, today),
        _diagnoses_in_review(subject),
        _records_missing(subject, today),
        _new_photos(subject),
    )
    row = (
        await session.execute(select(*(b.scalar_subquery() for b in builders)))
    ).one()
    return HomeCounts(*(int(v) for v in row))


async def recent_audit(
    session: AsyncSession, subject: Subject, *, limit: int
) -> list[AuditRow]:
    """최근 처리 이력 limit 건 — (at, id) 내림차순 한 문장. 관리자가 아니면 질의 없이 빈 목록."""
    if subject.type != "admin":
        return []
    stmt = (
        select(
            AuditLog.id,
            AuditLog.at,
            AuditLog.actor,
            AuditLog.action,
            AuditLog.target_type,
            AuditLog.target_id,
        )
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    return [AuditRow(*values) for values in (await session.execute(stmt)).all()]
