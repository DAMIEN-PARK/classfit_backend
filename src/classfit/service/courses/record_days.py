"""일차 단위 계획대로 기록 · 일괄 확인(T7 결정 vi·xii·xiii, R9~R14·R17). flush 까지만.

- 그 강의 그 일차의 모든 섹션 세션을 본다. 계획대로는 지난 일차(일차 날짜 ≤ 오늘)만이고 아니면 409(R17).
  대상: 강사는 내 세션 ∧ 기록 없음(R9), 관리자는 그 일차 세션 전부 ∧ 기록 없음(R11). 이미 기록이 있으면 덮지 않는다
  (R10·R12). 강사 기록은 done, 관리자 기록은 ok(기록자·확인자 관리자)다.
- 계획 값은 rules.record.plan_fields: 실시일 = 일차 날짜 · 시작·끝 = rules.schedule.session_time(일정표 days.schedule_of 와
  같은 계산 — siblings 는 그 세션이 든 섹션의 그 일차 세션이라 섹션마다 따로 잰다) · 진행 내용 = 설명 또는 제목 ·
  참석 = 그 강의 등록 수 · 비고 없음.
- 일괄 확인은 그 일차의 done → ok 만이다(R13 — none·ok 는 빠진다 R14). 날짜는 보지 않는다(예정 차시도 저장될 수 있다).
- 강사 판정은 mine.course_for(없음 404 → 배정 세션 없는 강의 403)다. 그 강의에 내 세션이 있으면 남의 세션은 대상에서
  빠질 뿐이다(R15). 일차가 없으면(그 강의가 없어도) 404.
- 쓰기 둘은 첫 DB 쓰기 전에 강의 행을 잠그고, 잠근 뒤 일차(fresh=True)와 그 일차 세션·기록(day_sessions — 늘
  populate_existing)을 다시 읽어 대상을 고른다(결정 xiii — 그 사이 커밋된 저장·고침을 본다).
- audit 은 대상이 있을 때만 1행(target course · detail {day_no, status, session_ids}). 0건이면 200 · audit 없음.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import record as crud_record
from classfit.crud.scope import Subject
from classfit.models import CourseDay, CourseSession
from classfit.service.courses import mine
from classfit.service.rules.record import is_past, plan_fields
from classfit.service.rules.schedule import session_time

NO_DAY = "그 일차가 없습니다"
NOT_PAST = "지난 일차만 계획대로 기록할 수 있습니다"


@dataclass(frozen=True)
class DayResult:
    """처리한 일차 · 그 세션들의 새 상태(done·ok) · 처리한 세션 id(일차 세션 순서)."""

    day_no: int
    status: str
    session_ids: list[int]

    @property
    def changed(self) -> int:
        return len(self.session_ids)


def _past_day(day: CourseDay | None, today: dt.date) -> CourseDay:
    """없으면 NotFound, 지난 일차가 아니면 Conflict(R17)."""
    if day is None:
        raise NotFound(NO_DAY)
    if not is_past(day.date, today):
        raise Conflict(NOT_PAST)
    return day


async def record_day_as_planned(
    session: AsyncSession,
    subject: Subject,
    *,
    course_id: int,
    day_no: int,
    today: dt.date,
    actor: str,
) -> DayResult:
    """그 일차의 기록 없는 세션(강사는 내 세션만)을 계획 값으로 기록한다."""
    instructor = subject.type == "instructor"
    if instructor:
        await mine.course_for(session, subject, course_id)
    _past_day(await crud_record.course_day(session, course_id, day_no), today)
    course = await crud_course.lock_course(session, course_id)
    if course is None:
        raise NotFound(NO_DAY)
    day = _past_day(
        await crud_record.course_day(session, course_id, day_no, fresh=True), today
    )
    rows = await crud_record.day_sessions(session, course_id, day_no)
    by_section: dict[int, list[CourseSession]] = defaultdict(list)
    for row, _ in rows:
        by_section[row.section_id].append(row)
    targets = [
        row
        for row, record in rows
        if record is None and (not instructor or row.instructor_id == subject.id)
    ]
    status = "done" if instructor else "ok"
    if not targets:
        return DayResult(day_no, status, [])
    enrolled = await crud_enrollment.count_enrollments(session, course_id)
    for row in targets:
        times = session_time(
            day, course.slot_min, course.break_min, by_section[row.section_id], row
        )
        fields = plan_fields(
            day_date=day.date,
            times=times,
            title=row.title,
            description=row.description,
            enrolled=enrolled,
        )
        await crud_record.insert_record(
            session,
            session_id=row.id,
            status=status,
            values=asdict(fields),
            by_kind=subject.type,
            by_id=subject.id,
            confirmed_by_id=None if instructor else subject.id,
        )
    session_ids = [row.id for row in targets]
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="course_day.record_as_planned",
        target_type="course",
        target_id=str(course_id),
        detail={"day_no": day_no, "status": status, "session_ids": session_ids},
    )
    return DayResult(day_no, status, session_ids)


async def confirm_day(
    session: AsyncSession, *, admin_id: int, course_id: int, day_no: int, actor: str
) -> DayResult:
    """그 일차의 done 기록을 전부 ok 로(관리자). 없는 일차 404."""
    if await crud_record.course_day(session, course_id, day_no) is None:
        raise NotFound(NO_DAY)
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound(NO_DAY)
    if await crud_record.course_day(session, course_id, day_no, fresh=True) is None:
        raise NotFound(NO_DAY)
    rows = await crud_record.day_sessions(session, course_id, day_no)
    targets = [
        record for _, record in rows if record is not None and record.status == "done"
    ]
    if not targets:
        return DayResult(day_no, "ok", [])
    for record in targets:
        await crud_record.confirm_row(session, record, admin_id=admin_id)
    session_ids = [record.session_id for record in targets]
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="course_day.confirm_all",
        target_type="course",
        target_id=str(course_id),
        detail={"day_no": day_no, "status": "ok", "session_ids": session_ids},
    )
    return DayResult(day_no, "ok", session_ids)
