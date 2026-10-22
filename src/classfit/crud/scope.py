"""주체 범위(Design 5절 3). 목록·파일 조회의 첫 WHERE 가 여기서 나온다.

파일 소유 종류 등록부 OWNER_KINDS 는 기본 거절이다: 등록 안 된 owner_kind 는 404.
종류는 T2b 부터 Design 4절 순서로 등록한다(session_attachment → instructor_document … → diagnosis_pdf).
판정은 (session, 주체, owner_id) → 범위 안이면 True(아니면 403).
강의 범위 course_scope 도 기본 거절이다: 관리자는 전부, 수강생은 토큰의 강의 하나(T2b), 나머지는 아무것도 못 본다.
T5(강사 배정)가 넓힌다. 강사 범위 instructor_scope 는 관리자 전부 · 강사 자기 자신 · 그 밖 거절이다(T3).
과정 풀 범위(T4)도 기본 거절이다: pool_scope 는 관리자 전부 · 강사는 활성 과정, own_course_scope·curriculum_scope·
capability_scope 는 관리자 전부 · 강사는 자기 것. 범위 함수는 목록과 "범위 밖은 404" 인 읽기에만 쓴다. 쓰기·소유 판정은
service 가 범위 없는 getter 로 읽어 404 → 403(owned_by) → 409 순으로 한다(T4 결정 i).

등록된 owner_kind:
- session_attachment(T2b) — 관리자 참 · 수강생은 같은 강의 ∧ 세션 is_open · 그 밖 거짓(T6 이 강사를 넓힌다).
- instructor_document(T3) — owner_id = 강사 id. 본인 강사만 참(주체 종류까지 본다), 관리자도 거짓이다.
  관리자의 열람 문은 audit 을 남기는 관리자 서류 끝점 하나다(T3 결정 ix·x).
- instructor_photo(T3) — owner_id = 강사 id. 관리자 ∨ 본인 강사. 등록만 했고 행을 만드는 끝점은 아직 없다(결정 xv).
- pool_course_file(T4) — owner_id = 파일 행 id. 관리자 ∨ 그 고유 과정의 소유 강사(owned_by). 다른 강사는 거짓.
- capability_file(T4) — owner_id = 파일 행 id. 관리자 ∨ 그 역량의 강사(owned_by).
- curriculum_file(T4) — owner_id = 파일 행 id. 관리자 ∨ 그 커리큘럼의 강사(owned_by).
  셋 다 관리자 열람에 audit 이 없다(강의안은 서류가 아니다, T4 결정 ix).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from sqlalchemy import ColumnElement, false, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import (
    Capability,
    CapabilityFile,
    Course,
    CourseSession,
    Curriculum,
    CurriculumFile,
    Instructor,
    PoolCourse,
    PoolCourseFile,
    Section,
    SessionAttachment,
)


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


def instructor_scope(subject: Subject) -> ColumnElement[bool]:
    """강사 목록·단건의 첫 WHERE(Design 5절 3). 관리자는 전부, 강사는 자기 행 하나, 그 밖은 기본 거절."""
    if subject.type == "admin":
        return true()
    if subject.type == "instructor":
        return Instructor.id == subject.id
    return false()


def pool_scope(subject: Subject) -> ColumnElement[bool]:
    """풀 과정 목록·강사용 상세의 첫 WHERE. 관리자는 전부, 강사는 활성 과정(비활성은 풀에서 빠진다), 그 밖 거절."""
    if subject.type == "admin":
        return true()
    if subject.type == "instructor":
        return PoolCourse.active.is_(True)
    return false()


def own_course_scope(subject: Subject) -> ColumnElement[bool]:
    """고유 과정 목록의 첫 WHERE. 관리자는 전부, 강사는 자기 고유 과정(비활성 포함), 그 밖 거절."""
    if subject.type == "admin":
        return true()
    if subject.type == "instructor":
        return PoolCourse.owner_instructor_id == subject.id
    return false()


def curriculum_scope(subject: Subject) -> ColumnElement[bool]:
    """커리큘럼 목록·단건의 첫 WHERE. 관리자는 전부, 강사는 자기 커리큘럼(비활성 포함), 그 밖 거절."""
    if subject.type == "admin":
        return true()
    if subject.type == "instructor":
        return Curriculum.instructor_id == subject.id
    return false()


def capability_scope(subject: Subject) -> ColumnElement[bool]:
    """역량 목록의 첫 WHERE. 관리자는 전부, 강사는 자기 역량, 그 밖 거절."""
    if subject.type == "admin":
        return true()
    if subject.type == "instructor":
        return Capability.instructor_id == subject.id
    return false()


def owned_by(subject: Subject, owner_instructor_id: int | None) -> bool:
    """강사 주체이고 소유 강사가 그 강사면 참. 같은 id 의 관리자·수강생 토큰이 통과하지 않게 종류를 먼저 본다.

    파일 판정 셋과 service 의 Forbidden 검사(고유 과정·역량·커리큘럼)가 이 함수 하나를 부른다(T4 결정 ix).
    """
    return subject.type == "instructor" and subject.id == owner_instructor_id


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


async def _instructor_document(
    session: AsyncSession, subject: Subject, owner_id: int
) -> bool:
    """owner_id = 강사 id. 본인 강사만. id 만 비교하면 같은 id 의 관리자·수강생 토큰이 통과하므로 종류도 본다."""
    return subject.type == "instructor" and subject.id == owner_id


async def _instructor_photo(
    session: AsyncSession, subject: Subject, owner_id: int
) -> bool:
    """owner_id = 강사 id. 관리자 ∨ 본인 강사."""
    if subject.type == "admin":
        return True
    return subject.type == "instructor" and subject.id == owner_id


async def _pool_course_file(
    session: AsyncSession, subject: Subject, owner_id: int
) -> bool:
    """owner_id = pool_course_file.id. 관리자 ∨ 그 고유 과정의 소유 강사."""
    if subject.type == "admin":
        return True
    owner = await session.scalar(
        select(PoolCourse.owner_instructor_id)
        .join(PoolCourseFile, PoolCourseFile.pool_course_id == PoolCourse.id)
        .where(PoolCourseFile.id == owner_id)
    )
    return owned_by(subject, owner)


async def _capability_file(
    session: AsyncSession, subject: Subject, owner_id: int
) -> bool:
    """owner_id = capability_file.id. 관리자 ∨ 그 역량의 강사."""
    if subject.type == "admin":
        return True
    owner = await session.scalar(
        select(Capability.instructor_id)
        .join(CapabilityFile, CapabilityFile.capability_id == Capability.id)
        .where(CapabilityFile.id == owner_id)
    )
    return owned_by(subject, owner)


async def _curriculum_file(
    session: AsyncSession, subject: Subject, owner_id: int
) -> bool:
    """owner_id = curriculum_file.id. 관리자 ∨ 그 커리큘럼의 강사."""
    if subject.type == "admin":
        return True
    owner = await session.scalar(
        select(Curriculum.instructor_id)
        .join(CurriculumFile, CurriculumFile.curriculum_id == Curriculum.id)
        .where(CurriculumFile.id == owner_id)
    )
    return owned_by(subject, owner)


OWNER_KINDS: dict[str, OwnerCheck] = {
    "session_attachment": _session_attachment,
    "instructor_document": _instructor_document,
    "instructor_photo": _instructor_photo,
    "pool_course_file": _pool_course_file,
    "capability_file": _capability_file,
    "curriculum_file": _curriculum_file,
}
