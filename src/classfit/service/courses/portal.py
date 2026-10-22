"""수강생 포털과 세션 첨부 목록(기획안 P3·원칙 5 · T2b 계획 결정 vii·x). 읽기만 한다.

- 포털은 섹션 → 세션 카드다. 시각은 일정표(days.schedule_of)와 같은 계산이고, 카드 상태는 rules.portal.card_state 다.
- 잠긴 카드(preparing)는 제목·일차·시각만 남기고 설명·키워드·첨부를 뺀다. 그 세션의 첨부 목록은 403 이다.
- 첨부는 crud 의 주체 범위(course_scope) 첫 WHERE 로 거른다. 자기 강의인지(경로 course_id)는 끝점이 먼저 403 으로 본다.
- 관리자 포털은 같은 판정의 미리 보기다. 응답의 href 는 끝점이 단다(schemas 는 service 를 모르고, courses 는 files 를 모른다).
- 종료·보관 강의도 판정은 같다(L1 "종료된 강의도 열람은 된다"). 보관(archived_at)은 쓰지 않는다.
- 카드마다 담당 강사 이름(instructor_name, T5 결정 xiv). 잠긴 카드에도 있고, 미배정이면 None 이다. 강사 id 는 싣지 않는다.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Forbidden, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import course as crud_course
from classfit.crud import instructor as crud_instructor
from classfit.crud import schedule as crud_schedule
from classfit.crud.scope import Subject
from classfit.models import Course, CourseSession, Section
from classfit.service.courses.days import schedule_of
from classfit.service.rules.portal import CardState, card_state

# (첨부, 파일 key, 파일 크기). link 는 key·size 가 None
AttachmentItem = crud_attachment.AttachmentRow


@dataclass(frozen=True)
class PortalCard:
    row: CourseSession
    date: dt.date | None
    start: str | None
    end: str | None
    state: CardState
    attachments: list[AttachmentItem]  # 잠긴 카드는 비어 있다
    instructor_name: str | None = None  # 미배정이면 None


@dataclass(frozen=True)
class PortalSection:
    row: Section
    cards: list[PortalCard]


@dataclass(frozen=True)
class Portal:
    course: Course
    sections: list[PortalSection]


def _card_key(card: PortalCard) -> tuple[bool, dt.date, bool, str, int, int]:
    """일차 순 → 시작 시각 순 → 교시 → id. 일차 미정·시각 미정은 뒤로."""
    return (
        card.date is None,
        card.date or dt.date.min,
        card.start is None,
        card.start or "",
        card.row.slot or 99,
        card.row.id,
    )


async def build_portal(
    session: AsyncSession, subject: Subject, *, course_id: int
) -> Portal:
    course = await crud_course.get_course(session, course_id)
    if course is None:
        raise NotFound("강의가 없습니다")
    schedule = await schedule_of(session, course)
    times: dict[int, tuple[dt.date | None, str | None, str | None]] = {}
    for day in schedule.days:
        for item in day.sessions:
            times[item.id] = (day.date, item.start, item.end)
    for undated in schedule.undated:
        times[undated.id] = (None, undated.start, undated.end)

    by_session: dict[int, list[AttachmentItem]] = defaultdict(list)
    for item in await crud_attachment.list_for_course(session, subject, course_id):
        by_session[item[0].session_id].append(item)

    rows = await crud_schedule.list_sessions(session, course_id)
    names = await crud_instructor.names_by_id(
        session, [s.instructor_id for s in rows if s.instructor_id is not None]
    )
    cards: dict[int, list[PortalCard]] = defaultdict(list)
    for s in rows:
        attachments = by_session[s.id]
        state = card_state(is_open=s.is_open, attachments=len(attachments))
        day, start, end = times.get(s.id, (None, None, None))
        cards[s.section_id].append(
            PortalCard(
                row=s,
                date=day,
                start=start,
                end=end,
                state=state,
                attachments=attachments if state == "open" else [],
                instructor_name=None
                if s.instructor_id is None
                else names.get(s.instructor_id),
            )
        )
    sections = [
        PortalSection(row=sec, cards=sorted(cards[sec.id], key=_card_key))
        for sec in await crud_schedule.list_sections(session, course_id)
    ]
    return Portal(course=course, sections=sections)


async def session_attachments(
    session: AsyncSession, subject: Subject, *, session_id: int
) -> list[AttachmentItem]:
    """열린 카드의 첨부. 없는 세션 404, 범위 밖(남의 강의)·잠긴 카드 403."""
    found = await crud_schedule.get_session_and_course(session, session_id)
    if found is None:
        raise NotFound("세션이 없습니다")
    row, _ = found
    items = await crud_attachment.list_for_session(session, subject, session_id)
    # 범위 밖이면 첨부가 0행이라 카드가 잠긴 것과 같다(남의 강의도 403)
    if card_state(is_open=row.is_open, attachments=len(items)) != "open":
        raise Forbidden("준비 중이거나 볼 수 없는 세션입니다")
    return items
