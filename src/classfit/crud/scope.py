"""주체 범위(Design 5절 3). 목록·파일 조회의 첫 WHERE 가 여기서 나온다.

파일 소유 종류 등록부 OWNER_KINDS 는 기본 거절이다: 등록 안 된 owner_kind 는 404.
종류는 T2b 부터 Design 4절 순서로 등록한다(session_attachment → instructor_document … → diagnosis_pdf).
판정은 (session, 주체, owner_id) → 범위 안이면 True(아니면 403).
강의 범위 course_scope 도 기본 거절이다: 관리자만 전부 보고, 나머지는 아무것도 못 본다.
T2b(수강생의 course_id)·T5(강사 배정)가 넓힌다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from sqlalchemy import ColumnElement, false, true
from sqlalchemy.ext.asyncio import AsyncSession


class Subject(Protocol):
    """요청 주체. service.auth.sessions.Principal 이 이 모양이다(crud 는 service 를 모른다)."""

    @property
    def type(self) -> str: ...

    @property
    def id(self) -> int: ...

    @property
    def course_id(self) -> int | None: ...


OwnerCheck = Callable[[AsyncSession, Subject, int], Awaitable[bool]]

OWNER_KINDS: dict[str, OwnerCheck] = {}


def course_scope(subject: Subject) -> ColumnElement[bool]:
    """강의 목록의 첫 WHERE(Design 5절 3). 관리자는 전부, 그 밖은 기본 거절."""
    if subject.type == "admin":
        return true()
    return false()
