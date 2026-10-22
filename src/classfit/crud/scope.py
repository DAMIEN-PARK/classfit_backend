"""주체 범위(Design 5절 3). 목록·파일 조회의 첫 WHERE 가 여기서 나온다.

파일 소유 종류 등록부 OWNER_KINDS 는 기본 거절이다: 등록 안 된 owner_kind 는 404.
종류는 T2b 부터 Design 4절 순서로 등록한다(session_attachment → instructor_document … → diagnosis_pdf).
판정은 (session, 주체, owner_id) → 범위 안이면 True(아니면 403).
강의 범위 course_scope 도 기본 거절이다: 관리자는 전부, 수강생은 토큰의 강의 하나(T2b), 나머지는 아무것도 못 본다.
T5(강사 배정)가 넓힌다.

등록된 owner_kind: session_attachment(T2b) — 관리자 참 · 수강생은 같은 강의 ∧ 세션 is_open · 그 밖 거짓(T6 이 강사를 넓힌다).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from sqlalchemy import ColumnElement, false, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import Course, CourseSession, Section, SessionAttachment


class Subject(Protocol):
    """요청 주체. service.auth.sessions.Principal 이 이 모양이다(crud 는 service 를 모른다)."""

    @property
    def type(self) -> str: ...

    @property
    def id(self) -> int: ...

    @property
    def course_id(self) -> int | None: ...


OwnerCheck = Callable[[AsyncSession, Subject, int], Awaitable[bool]]


def course_scope(subject: Subject) -> ColumnElement[bool]:
    """강의 목록의 첫 WHERE(Design 5절 3). 관리자는 전부, 수강생은 자기 강의 하나, 그 밖은 기본 거절."""
    if subject.type == "admin":
        return true()
    if subject.type == "learner" and subject.course_id is not None:
        return Course.id == subject.course_id
    return false()


async def _session_attachment(
    session: AsyncSession, subject: Subject, owner_id: int
) -> bool:
    """owner_id = session_attachment.id. 수강생은 자기 강의의 열린 세션 첨부만(잠긴 세션 파일은 403, T2b 결정 vii)."""
    if subject.type == "admin":
        return True
    if subject.type != "learner":
        return False
    found = (
        select(SessionAttachment.id)
        .join(CourseSession, CourseSession.id == SessionAttachment.session_id)
        .join(Section, Section.id == CourseSession.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(course_scope(subject))
        .where(SessionAttachment.id == owner_id, CourseSession.is_open.is_(True))
    )
    return bool(await session.scalar(select(found.exists())))


OWNER_KINDS: dict[str, OwnerCheck] = {
    "session_attachment": _session_attachment,
}
