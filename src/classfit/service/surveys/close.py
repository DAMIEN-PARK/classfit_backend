"""배포 설문 닫기 · 다시 열기 · 고치기(T8 결정 vii·xvii·xviii·xix). flush 까지만.

- 셋 다 범위 없는 getter 로 없으면 404 → 그 설문의 강의 행을 잡고(lock_course) → 설문 행을 잡고(lock_survey) → fresh 로 다시
  읽어 판정한다(배포·밀어내기와 강의 행에서 줄 선다 — 닫힌 설문을 다시 여는 사이 배포가 그것을 밀어내지 않는다).
- 닫기: 예약·열림 → closed_at = 지금(닫힘일은 그대로) · audit survey.close · 배정 강사에게 survey_closed. 이미 닫힘 409.
- 다시 열기: 닫힘 ∧ 현재 설문 → closed_at 없앰 · 열림일 = min(열림일, 오늘)(열리기 전에 닫은 설문은 바로 연다) ·
  닫힘일 = max(닫힘일, 오늘 + REOPEN_DAYS) · reopened_at = 지금. 열림·예약 409 · 밀려난 설문 409. 기존 응답자는 다시 못 낸다.
- 고치기(PATCH): questions 는 응답이 1건이라도 있으면 409(잠근 뒤 센다) · open_on 은 예약일 때만 · 오늘 이상 · close_on 은
  예약·열림일 때만(닫힘은 다시 열기) · 오늘 이상(지난날로 당겨 날짜로 닫으면 closed_at·알림·audit 이 비니, 닫으려면 :close —
  리뷰 반영) · open_on 이상. 밀려난 설문은 409. 바뀐 칸이 없으면 쓰지 않는다(audit 없음).
- 날짜로 닫힌 설문은 알림이 없다(워커 없음). 알림 params 는 본문에 쓸 값의 스냅샷이다(닫은 날 closed_on = 오늘).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import outbox as crud_outbox
from classfit.crud import survey as crud_survey
from classfit.crud import survey_response as crud_survey_response
from classfit.models import Course, Survey
from classfit.service.rules.survey import REOPEN_DAYS, DatesRejected
from classfit.service.surveys.templates import check_questions
from classfit.service.surveys.views import status_of

NO_SURVEY = "설문이 없습니다"
SUPERSEDED = "새 설문으로 밀려난 설문은 바꿀 수 없습니다"
CLOSED_KIND = "survey_closed"
PATCHABLE = ("questions", "open_on", "close_on")


async def _audit(
    session: AsyncSession, actor: str, action: str, row: Survey, **detail: Any
) -> None:
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action=f"survey.{action}",
        target_type="survey",
        target_id=str(row.id),
        detail=detail,
    )


async def close_survey(
    session: AsyncSession, *, survey_id: int, today: dt.date, actor: str
) -> Survey:
    found = await crud_survey.get_survey(session, survey_id)
    if found is None:
        raise NotFound(NO_SURVEY)
    course = await crud_course.lock_course(session, found.course_id)
    if course is None:
        raise NotFound(NO_SURVEY)
    if await crud_survey.lock_survey(session, survey_id) is None:
        raise NotFound(NO_SURVEY)
    row = await crud_survey.get_survey(session, survey_id, fresh=True)
    assert row is not None  # 행을 잡고 있다
    if status_of(row, today) == "closed":
        raise Conflict("이미 닫힌 설문입니다")
    row = await crud_survey.apply_survey(
        session, row, closed_at=dt.datetime.now(dt.UTC)
    )
    await _audit(session, actor, "close", row, close_on=row.close_on.isoformat())
    await _notify_closed(session, survey=row, course=course, today=today)
    return row


async def reopen_survey(
    session: AsyncSession, *, survey_id: int, today: dt.date, actor: str
) -> Survey:
    found = await crud_survey.get_survey(session, survey_id)
    if found is None:
        raise NotFound(NO_SURVEY)
    if await crud_course.lock_course(session, found.course_id) is None:
        raise NotFound(NO_SURVEY)
    if await crud_survey.lock_survey(session, survey_id) is None:
        raise NotFound(NO_SURVEY)
    row = await crud_survey.get_survey(session, survey_id, fresh=True)
    assert row is not None  # 행을 잡고 있다
    if not row.current:
        raise Conflict(SUPERSEDED)
    if status_of(row, today) != "closed":
        raise Conflict("닫힌 설문만 다시 열 수 있습니다")
    row = await crud_survey.apply_survey(
        session,
        row,
        closed_at=None,
        open_on=min(row.open_on, today),
        close_on=max(row.close_on, today + dt.timedelta(days=REOPEN_DAYS)),
        reopened_at=dt.datetime.now(dt.UTC),
    )
    await _audit(session, actor, "reopen", row, close_on=row.close_on.isoformat())
    return row


async def patch_survey(
    session: AsyncSession,
    *,
    survey_id: int,
    changes: Mapping[str, Any],
    today: dt.date,
    actor: str,
) -> Survey:
    """준 칸(questions · open_on · close_on)만 바꾼다."""
    unknown = set(changes) - set(PATCHABLE)
    if unknown:
        raise ValueError(f"고칠 수 없는 칸: {sorted(unknown)}")
    found = await crud_survey.get_survey(session, survey_id)
    if found is None:
        raise NotFound(NO_SURVEY)
    if await crud_course.lock_course(session, found.course_id) is None:
        raise NotFound(NO_SURVEY)
    if await crud_survey.lock_survey(session, survey_id) is None:
        raise NotFound(NO_SURVEY)
    row = await crud_survey.get_survey(session, survey_id, fresh=True)
    assert row is not None  # 행을 잡고 있다
    if not row.current:
        raise Conflict(SUPERSEDED)
    status = status_of(row, today)
    if "questions" in changes:
        if await crud_survey_response.count_responses(session, survey_id) > 0:
            raise Conflict("응답이 들어온 설문의 문항은 고칠 수 없습니다")
        check_questions(changes["questions"])
    if "open_on" in changes:
        if status != "scheduled":
            raise Conflict("열림일은 예약 상태에서만 바꿀 수 있습니다")
        if changes["open_on"] < today:
            raise DatesRejected("open_before_today")
    if "close_on" in changes:
        if status == "closed":
            raise Conflict("닫힌 설문은 다시 열기로 엽니다")
        if changes["close_on"] < today:
            raise DatesRejected("close_before_today")  # 닫으려면 :close
    if changes.get("close_on", row.close_on) < changes.get("open_on", row.open_on):
        raise DatesRejected("close_before_open")
    changed = [f for f in PATCHABLE if f in changes and getattr(row, f) != changes[f]]
    if not changed:
        return row
    row = await crud_survey.apply_survey(
        session, row, **{f: changes[f] for f in changed}
    )
    await _audit(session, actor, "update", row, fields=changed)
    return row


async def _notify_closed(
    session: AsyncSession, *, survey: Survey, course: Course, today: dt.date
) -> int:
    """배정 강사(강사 id 순)에게 survey_closed 한 행씩. 쌓은 수."""
    _, instructors = await crud_survey.recipient_emails(session, course.id)
    params = {
        "survey_id": survey.id,
        "course_title": course.title,
        "closed_on": today.isoformat(),
    }
    for to in instructors:
        await crud_outbox.enqueue(session, kind=CLOSED_KIND, params=dict(params), to=to)
    return len(instructors)
