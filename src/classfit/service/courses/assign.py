"""강사 배정(T5 결정 vii·viii·x·xv·xvi·xvii). flush 까지만.

- 세션마다 담당 강사 1명(session.instructor_id). 배정을 바꾸는 문은 셋이다: 세션 PATCH(sections.patch_session) ·
  섹션 일괄 assign_section · 개설 시작점 ②④(starts). 셋 다 assign_locked 하나로 기록한다.
- 배정 가능은 승인(approved)만이다. lock_assignable 이 강사 행을 FOR UPDATE 로 잠근 뒤 판정한다(정지와 엇갈려
  "정지된 강사에게 새 배정" 이 커밋되지 않게). 없으면 404, 승인이 아니면 409 + instructor_status. 해제(null)는 상태를 보지 않는다.
- 잠금 순서(결정 xvii): course(lock_course) → instructor(lock_instructor) → 원본 capability·stored_file(crud.materials)
  → 쓰기. 부르는 쪽이 이 순서로 잡고 assign_locked 를 부른다.
- 새로 배정된 세션 중 pool_course_id 가 있고 첨부가 0개인 세션에만 그 강사의 기본 강의안을 붙인다(materials).
  담당이 바뀌어도 이전 첨부는 그대로이고, 해제도 첨부를 지우지 않는다.
- 배정이 바뀐 요청마다 audit session.assign 1행(target course, 세션마다 이전 강사 from · 같은 요청의 다른 칸까지 적용한
  뒤의 제목 · 강의 제목 스냅샷 · materials · skipped_missing). 새 강사면 outbox session_assigned 1행
  (params {instructor_id, audit_id}, to 강사 이메일 — 본문은 scripts.outbox_preview 가 audit 스냅샷으로 만든다).
  바뀐 세션이 0 이면(같은 값) 둘 다 없다.
- 배정 후보(candidates, 결정 xx)는 승인 강사만, 추천(그 과정 역량 ∨ 고유 과정 소유자) 먼저. 없는 강의·pool_id 는 404,
  비활성 과정이어도 목록은 준다(이미 있는 세션의 배정).
- crud 는 모듈 별칭으로 들여 부를 때마다 속성을 찾는다(행동 시험의 장벽 감싸개가 crud 모듈 속성에 먹게, 결정 xviii).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import instructor as crud_instructor
from classfit.crud import outbox as crud_outbox
from classfit.crud import pool as crud_pool
from classfit.crud import schedule as crud_schedule
from classfit.crud.instructor import CandidateRow
from classfit.crud.scope import Subject
from classfit.models import AuditLog, Course, CourseSession, Instructor
from classfit.service.courses import materials, sections

ASSIGNABLE = "approved"
AUDIT_ACTION = "session.assign"
MAIL_KIND = "session_assigned"


@dataclass(frozen=True)
class AssignResult:
    changed: list[int]  # 담당이 바뀐 세션 id
    materials: int  # 붙인 기본 강의안 사본 수
    skipped_missing: int  # 잠그려는 순간 사라져 건너뛴 원본 파일 수


async def lock_assignable(session: AsyncSession, instructor_id: int) -> Instructor:
    """강사 행을 잠그고 배정 가능(승인)인지 본다. 없으면 NotFound, 승인이 아니면 Conflict(instructor_status)."""
    row = await crud_instructor.lock_instructor(session, instructor_id)
    if row is None:
        raise NotFound("강사가 없습니다")
    if row.status != ASSIGNABLE:
        raise Conflict(
            f"승인된 강사만 배정할 수 있습니다(지금 상태 {row.status})",
            instructor_status=row.status,
        )
    return row


async def record(
    session: AsyncSession,
    *,
    course: Course,
    instructor: Instructor | None,
    rows: Sequence[CourseSession],
    previous: dict[int, int | None],
    materials: int,
    skipped_missing: int,
    actor: str,
) -> AuditLog | None:
    """바뀐 행(rows)의 배정 audit 1행과 새 강사면 outbox 1행. 바뀐 행이 없으면 아무것도 쓰지 않는다."""
    if not rows:
        return None
    audit = await crud_audit.insert_audit(
        session,
        actor=actor,
        action=AUDIT_ACTION,
        target_type="course",
        target_id=str(course.id),
        detail={
            "instructor_id": None if instructor is None else instructor.id,
            "sessions": [
                {"id": r.id, "title": r.title, "from": previous.get(r.id)} for r in rows
            ],
            "course_title": course.title,
            "materials": materials,
            "skipped_missing": skipped_missing,
        },
    )
    if instructor is not None:
        await crud_outbox.enqueue(
            session,
            kind=MAIL_KIND,
            params={"instructor_id": instructor.id, "audit_id": audit.id},
            to=instructor.email,
        )
    return audit


async def assign_locked(
    session: AsyncSession,
    *,
    course: Course,
    rows: Sequence[CourseSession],
    instructor: Instructor | None,
    actor: str,
) -> AssignResult:
    """강의·강사를 부르는 쪽이 이미 잠갔다는 전제로 rows 의 담당을 instructor(None 이면 해제)로 바꾸고 기록한다."""
    previous = {r.id: r.instructor_id for r in rows}
    changed = await crud_schedule.set_instructor(
        session, rows, None if instructor is None else instructor.id
    )
    changed_set = set(changed)
    changed_rows = [r for r in rows if r.id in changed_set]
    copied, skipped = 0, 0
    if instructor is not None and changed_rows:
        copied, skipped = await materials.attach_defaults(
            session, rows=changed_rows, instructor_id=instructor.id
        )
    await record(
        session,
        course=course,
        instructor=instructor,
        rows=changed_rows,
        previous=previous,
        materials=copied,
        skipped_missing=skipped,
        actor=actor,
    )
    return AssignResult(changed=changed, materials=copied, skipped_missing=skipped)


async def assign_rows(
    session: AsyncSession,
    *,
    course_id: int,
    rows: Sequence[CourseSession],
    instructor_id: int | None,
    actor: str,
) -> AssignResult:
    """그 강의의 세션 rows 를 instructor_id(None 이면 해제)에게. 강의 잠금 → 강사 잠금 → 행을 다시 읽고 기록한다.

    그 사이 지워졌거나 다른 강의의 세션은 다시 읽기에서 빠진다.
    """
    course = await crud_course.lock_course(session, course_id)
    if course is None:
        raise NotFound("강의가 없습니다")
    instructor = None
    if instructor_id is not None:
        instructor = await lock_assignable(session, instructor_id)
    fresh = await crud_schedule.reload_sessions(
        session, course_id, [r.id for r in rows]
    )
    return await assign_locked(
        session, course=course, rows=fresh, instructor=instructor, actor=actor
    )


async def assign_section(
    session: AsyncSession,
    *,
    course_id: int,
    section_id: int,
    instructor_id: int | None,
    actor: str,
) -> AssignResult:
    """그 섹션의 세션 전부를 한 강사에게(이미 그 강사인 세션은 건너뜀). 없는 섹션·다른 강의의 섹션은 404.

    섹션 존재는 잠그기 전에 한 번, 강의를 잠근 뒤 한 번 더 본다(기다린 사이 섹션이 지워졌으면 404, codex 2차 #6).
    세션 목록은 잠근 뒤 읽는다(기다린 사이 더해지거나 지워진 세션을 놓치지 않게).
    """
    await sections.section_in_course(session, course_id, section_id)
    course = await crud_course.lock_course(session, course_id)
    if course is None:
        raise NotFound("이 강의의 섹션이 없습니다")
    await sections.section_in_course(session, course_id, section_id)
    instructor = None
    if instructor_id is not None:
        instructor = await lock_assignable(session, instructor_id)
    rows = await crud_schedule.list_section_sessions(session, section_id)
    return await assign_locked(
        session, course=course, rows=rows, instructor=instructor, actor=actor
    )


async def candidates(
    session: AsyncSession,
    subject: Subject,
    *,
    course_id: int,
    pool_id: str | None,
    limit: int,
) -> tuple[list[CandidateRow], bool]:
    """(앞 limit 줄, 더 있는지). 없는 강의·풀 과정은 NotFound."""
    if await crud_course.get_course(session, course_id) is None:
        raise NotFound("강의가 없습니다")
    if (
        pool_id is not None
        and await crud_pool.get_pool_course_any(session, pool_id) is None
    ):
        raise NotFound("풀 과정이 없습니다")
    return await crud_instructor.list_candidates(
        session, subject, course_id=course_id, pool_course_id=pool_id, limit=limit
    )
