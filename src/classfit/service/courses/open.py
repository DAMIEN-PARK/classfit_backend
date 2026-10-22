"""강의 개설 + 초대코드 발급의 단일 진입점 open_course()(Design 5절 13, 기획안 A3 시작점 ① 빈 강의).

한 트랜잭션: course 1행 → (day_count ≥ 1 이면) course_day n행 → 초대코드 1행 → audit_log 1행.
flush 까지만 하고 커밋은 요청 트랜잭션(app.deps.db)이 한다. 중간에 실패하면 전부 롤백된다.
기간: day_count ≥ 1 이면 rules.schedule.make_days 의 첫·끝 날이다. 시작일이 토·일이면 첫 평일로 옮겨진다
(T2a 계획 결정 i, 기획안 A3 "종료일은 일정에서 자동"). 만료일은 end_on + invite_expiry_days 로 저장한다(결정 ii).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import schedule as crud_schedule
from classfit.crud.audit import insert_audit
from classfit.crud.course import insert_course
from classfit.models import Course, InviteCode
from classfit.schemas.course import CourseOpenIn
from classfit.service.courses.codes import issue_invite_code
from classfit.service.rules.schedule import make_days


async def open_course(
    session: AsyncSession,
    body: CourseOpenIn,
    *,
    actor: str,
    invite_expiry_days: int,
) -> tuple[Course, InviteCode]:
    planned = []
    if body.day_count >= 1:
        if (
            body.day_start is None or body.day_end is None
        ):  # CourseOpenIn 이 422 로 먼저 막는다
            raise ValueError("day_count ≥ 1 이면 day_start·day_end 가 있어야 한다")
        planned = make_days(body.start_on, body.day_count, body.day_start, body.day_end)
    if planned:
        start_on, end_on = planned[0].date, planned[-1].date
    elif body.end_on is not None:
        start_on, end_on = body.start_on, body.end_on
    else:  # CourseOpenIn 이 422 로 먼저 막는다
        raise ValueError("일정이 없으면 end_on 이 있어야 한다")

    course = await insert_course(
        session,
        title=body.title,
        client_name=body.client_name,
        course_type=body.course_type,
        cohort=body.cohort,
        method=body.method,
        hours_per_person=body.hours_per_person,
        start_on=start_on,
        end_on=end_on,
        slot_min=body.slot_min,
        break_min=body.break_min,
        intro=body.intro,
        notice=body.notice,
        status="prep",
        status_manual=False,
    )
    course_id = course.id
    await crud_schedule.insert_days(
        session,
        course_id,
        [
            {
                "day_no": d.no,
                "date": d.date,
                "start_time": d.start_time,
                "end_time": d.end_time,
            }
            for d in planned
        ],
    )
    code = await issue_invite_code(
        session,
        course_id=course_id,
        expires_on=end_on + timedelta(days=invite_expiry_days),
    )
    await insert_audit(
        session,
        actor=actor,
        action="course.open",
        target_type="course",
        target_id=str(course_id),
        detail={"day_count": len(planned)},
    )
    return course, code
