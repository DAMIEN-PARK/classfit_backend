"""survey(배포 설문) 읽기·쓰기·잠금과 상태의 SQL 판(T8 결정 iii·vi·vii·xiv·xvi·xvii·xix). flush 까지만.

- 상태 survey_status_sql 은 service.rules.survey.status_at 의 SQL 판이다. 경계는 두 판이 같다: closed_at 있음 → closed,
  오늘 < open_on → scheduled, 오늘 ≤ close_on → open, 그 밖 closed. 목록 필터·홈은 이 판이다.
- 강의당 현재 설문은 부분 유일 색인 uq_survey_course_id_current 가 하나로 지킨다. 넣기(insert_survey)는 flush_or_conflict 로
  그 위반을 409 로 바꾼다. 밀어내기(supersede)는 current = false · closed_at = coalesce(closed_at, 지금)이다.
- 잠금: 설문 한 행 lock_survey(FOR UPDATE + populate_existing)와, 강의 삭제·양식 삭제가 여러 행을 잡는 lock_in_id_order
  (id 오름차순 FOR UPDATE — 배포·밀어내기와 같은 순서). 이 파일의 with_for_update 는 그 둘이다. 순서는 template → course →
  survey → survey_response 의 한 방향이고, 쓰는 쪽은 강의 행(crud.course.lock_course)을 먼저 잡는다(결정 xix).
- 목록 list_stmt·홈 home_rows 의 첫 WHERE 는 주체 범위(course_scope)다. 홈은 보관하지 않은 강의의 현재 설문만 본다.
- 사람 칸은 여기서 읽지 않는다. 알림 수신 주소 recipient_emails 만 수강생·배정 강사 이메일을 읽는다(outbox 몫).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.crud.scope import Subject, course_scope
from classfit.models import (
    Course,
    CourseSession,
    Enrollment,
    Instructor,
    Learner,
    Section,
    Survey,
)

CURRENT_TAKEN = "이 강의에는 이미 현재 설문이 있습니다"


@dataclass(frozen=True)
class HomeSurveyRow:
    course_id: int
    course_title: str
    survey_id: int
    open_on: dt.date
    close_on: dt.date
    closed_at: dt.datetime | None
    reopened_at: dt.datetime | None
    status: str  # 오늘 기준(survey_status_sql)


async def insert_survey(
    session: AsyncSession,
    *,
    course_id: int,
    template_id: int | None,
    template_name: str,
    questions: list[dict[str, Any]],
    open_on: dt.date,
    close_on: dt.date,
) -> Survey:
    """현재 설문 한 행. 같은 강의에 현재 설문이 있으면(부분 유일 색인) Conflict."""
    row = Survey(
        course_id=course_id,
        template_id=template_id,
        template_name=template_name,
        questions=questions,
        open_on=open_on,
        close_on=close_on,
    )
    await flush_or_conflict(session, CURRENT_TAKEN, row)
    await session.refresh(row)
    return row


async def get_survey(
    session: AsyncSession, survey_id: int, *, fresh: bool = False
) -> Survey | None:
    """범위 없는 getter(404 판정용). fresh 는 잠근 뒤 다시 읽을 때(populate_existing)."""
    stmt = select(Survey).where(Survey.id == survey_id)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def lock_survey(session: AsyncSession, survey_id: int) -> Survey | None:
    """설문 행을 SELECT … FOR UPDATE 로 잠그고 새로 읽는다. 없으면 None.

    제출·닫기·다시 열기·문항 수정·밀어내기가 이 행 하나로 줄 선다(결정 xix).
    """
    stmt = (
        select(Survey)
        .where(Survey.id == survey_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def current_for_course(
    session: AsyncSession, course_id: int, *, fresh: bool = False
) -> Survey | None:
    stmt = select(Survey).where(Survey.course_id == course_id, Survey.current.is_(True))
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def current_for_courses(
    session: AsyncSession, course_ids: Collection[int]
) -> dict[int, Survey]:
    """강의 id → 현재 설문(없는 강의는 빠진다)."""
    wanted = list(course_ids)
    if not wanted:
        return {}
    stmt = select(Survey).where(Survey.course_id.in_(wanted), Survey.current.is_(True))
    return {row.course_id: row for row in (await session.scalars(stmt)).all()}


async def supersede(session: AsyncSession, row: Survey) -> None:
    """닫힌 현재 설문을 밀어낸다: current = false, closed_at 이 비었으면(날짜로 닫힘) 지금. row 는 잠근 행이다."""
    row.current = False
    if row.closed_at is None:
        row.closed_at = func.now()
    await session.flush()


async def lock_in_id_order(
    session: AsyncSession,
    *,
    course_id: int | None = None,
    template_id: int | None = None,
) -> list[int]:
    """그 강의(또는 그 양식으로 배포한) 설문 행을 id 오름차순 FOR UPDATE 로 잡고 그 id 를 돌려준다. 둘 중 하나만 준다.

    강의 삭제(CASCADE)·양식 삭제(SET NULL)가 survey 행들을 고치는 순서를 배포·밀어내기와 맞춘다(결정 xix).
    """
    if (course_id is None) == (template_id is None):
        raise ValueError("course_id · template_id 중 하나만 준다")
    which = (
        Survey.course_id == course_id
        if course_id is not None
        else Survey.template_id == template_id
    )
    stmt = select(Survey.id).where(which).order_by(Survey.id).with_for_update()
    return list((await session.scalars(stmt)).all())


async def apply_survey(session: AsyncSession, row: Survey, **fields: Any) -> Survey:
    """칸을 바꾸고 flush 한 뒤 다시 읽는다(updated_at·closed_at = now() 가 만료된다)."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    await session.refresh(row)
    return row


def survey_status_sql(today: dt.date) -> ColumnElement[str]:
    return case(
        (Survey.closed_at.is_not(None), literal("closed")),
        (Survey.open_on > today, literal("scheduled")),
        (Survey.close_on >= today, literal("open")),
        else_=literal("closed"),
    )


def list_stmt(
    subject: Subject,
    *,
    course_id: int | None,
    status: str | None,
    today: dt.date,
) -> Select[tuple[Survey]]:
    """관리자 설문 목록(crud.page.keyset_page 에 넘긴다). 첫 WHERE 는 주체 범위다. 밀려난 설문도 든다."""
    stmt = (
        select(Survey)
        .join(Course, Course.id == Survey.course_id)
        .where(course_scope(subject))
    )
    if course_id is not None:
        stmt = stmt.where(Survey.course_id == course_id)
    if status is not None:
        stmt = stmt.where(survey_status_sql(today) == status)
    return stmt


async def course_header(
    session: AsyncSession, survey_ids: Collection[int]
) -> dict[int, tuple[str, str]]:
    """설문 id → (강의 제목, 고객사)."""
    wanted = list(survey_ids)
    if not wanted:
        return {}
    stmt = (
        select(Survey.id, Course.title, Course.client_name)
        .join(Course, Course.id == Survey.course_id)
        .where(Survey.id.in_(wanted))
    )
    return {sid: (title, client) for sid, title, client in await session.execute(stmt)}


async def enrollment_counts(
    session: AsyncSession, course_ids: Collection[int]
) -> dict[int, int]:
    """강의 id → 지금 등록 수(응답률 분모, 결정 xiii). 한 문장 GROUP BY. 등록이 없으면 0."""
    wanted = list(course_ids)
    counts = dict.fromkeys(wanted, 0)
    if not wanted:
        return counts
    stmt = (
        select(Enrollment.course_id, func.count())
        .where(Enrollment.course_id.in_(wanted))
        .group_by(Enrollment.course_id)
    )
    for course_id, n in (await session.execute(stmt)).all():
        counts[course_id] = n
    return counts


async def home_rows(
    session: AsyncSession, subject: Subject, *, today: dt.date, limit: int
) -> tuple[list[HomeSurveyRow], bool]:
    """보관 안 한 범위 강의의 현재 설문. 순서는 닫힘일 내림차순 → 설문 id 내림차순. (앞 limit 행, 더 있는지)."""
    stmt = (
        select(
            Course.id,
            Course.title,
            Survey.id,
            Survey.open_on,
            Survey.close_on,
            Survey.closed_at,
            Survey.reopened_at,
            survey_status_sql(today),
        )
        .select_from(Course)
        .join(Survey, Survey.course_id == Course.id)
        .where(course_scope(subject), Course.archived_at.is_(None))
        .where(Survey.current.is_(True))
        .order_by(Survey.close_on.desc(), Survey.id.desc())
        .limit(limit + 1)
    )
    rows = [HomeSurveyRow(*values) for values in (await session.execute(stmt)).all()]
    return rows[:limit], len(rows) > limit


async def recipient_emails(
    session: AsyncSession, course_id: int
) -> tuple[list[str], list[str]]:
    """(그 강의 등록 수강생 이메일 — 등록 순, 세션 담당 강사 이메일 — 겹침 없이 강사 id 순). 알림 outbox 몫(결정 xvii)."""
    learners = (
        select(Learner.email)
        .join(Enrollment, Enrollment.learner_id == Learner.id)
        .where(Enrollment.course_id == course_id)
        .order_by(Enrollment.id)
    )
    instructors = (
        select(Instructor.id, Instructor.email)
        .join(CourseSession, CourseSession.instructor_id == Instructor.id)
        .join(Section, Section.id == CourseSession.section_id)
        .where(Section.course_id == course_id)
        .distinct()
        .order_by(Instructor.id)
    )
    return (
        list((await session.scalars(learners)).all()),
        [email for _, email in await session.execute(instructors)],
    )
