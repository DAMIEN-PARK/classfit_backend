"""T5 시험 도우미: 승인 강사 · 섹션 있는 강의 · 풀 세션 · 기본 강의안 원본(역량·고유 과정·커리큘럼 파일).

- 전부 T2a~T4 의 실제 함수 위에 쌓는다(ORM 으로 직접 만들지 않는다). 강의는 open_course() 를 거치는 open_test_course,
  강사는 signup() 을 거치는 make_instructor, 풀 과정·커리큘럼은 T4 픽스처 make_pool_course·make_curriculum,
  역량은 crud.capability.get_or_create_capability, 파일 행·stored_file·바이트는 service.files.pool_files 의
  add_pdf_file·add_link_file, 차시는 crud.curriculum.replace_slots 다.
- 승인 강사는 approved() 로 만든다. T4 instructor_pair 는 대기 강사 둘이라 배정 시험에 쓰지 않는다.
- 파일 넣기의 actor 는 "system" 이다(시험 준비용).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import schedule as crud_schedule
from classfit.crud.capability import get_or_create_capability
from classfit.crud.curriculum import replace_slots
from classfit.crud.pool import get_pool_course_any
from classfit.models import Course, CourseSession, Section
from classfit.service.files.pool_files import add_link_file, add_pdf_file
from tests.fixtures.courses import open_test_course
from tests.fixtures.enter import PDF
from tests.fixtures.instructors import instructor_headers, make_instructor
from tests.fixtures.pool import make_curriculum

__all__ = [
    "PDF",
    "approved",
    "capability_files",
    "course_with_section",
    "curriculum_with_slots",
    "own_course_files",
    "pool_session",
]

MAX_BYTES = 1024 * 1024
LINK_URL = "https://example.com/guide"


async def approved(
    session: AsyncSession, settings: Settings, *, email: str, status: str = "approved"
) -> tuple[int, dict[str, str]]:
    """(강사 id, Bearer 헤더). 기본은 승인 강사다. status 로 대기·반려·정지도 만든다."""
    iid = await make_instructor(session, settings, email=email, status=status)
    return iid, await instructor_headers(session, iid)


async def course_with_section(
    session: AsyncSession, *, day_count: int = 2, **over: Any
) -> tuple[Course, Section]:
    """시험 강의(평일 day_count 일, 13:00~17:00 · 50·10 → 하루 4교시)와 섹션 하나."""
    course, _ = await open_test_course(session, day_count=day_count, **over)
    section = await crud_schedule.insert_section(session, course.id, title="공통")
    return course, section


async def pool_session(
    session: AsyncSession,
    *,
    section_id: int,
    pool_id: str,
    day_no: int | None = None,
    slot: int | None = None,
    **fields: Any,
) -> CourseSession:
    """그 풀 과정을 가리키는 미배정 세션(제목·설명·분은 과정 값)."""
    course = await get_pool_course_any(session, pool_id)
    assert course is not None, pool_id
    values: dict[str, Any] = {
        "title": course.title,
        "description": course.goal,
        "minutes": course.minutes,
        "day_no": day_no,
        "slot": slot,
        "keywords": [],
        "is_open": False,
        "pool_course_id": pool_id,
        **fields,
    }
    return await crud_schedule.insert_session(session, section_id, **values)


async def _add_files(
    session: AsyncSession,
    root: Path | None,
    *,
    owner_kind: str,
    owner_id: Any,
    kinds: Iterable[str],
) -> list[int]:
    ids: list[int] = []
    for n, kind in enumerate(kinds, start=1):
        if kind == "pdf":
            assert root is not None, "pdf 원본은 저장소 root 가 필요하다"
            row, _ = await add_pdf_file(
                session,
                owner_kind=owner_kind,
                owner_id=owner_id,
                root=root,
                max_bytes=MAX_BYTES,
                title=f"강의안 {n}",
                data=PDF,
                actor="system",
            )
        else:
            row = await add_link_file(
                session,
                owner_kind=owner_kind,
                owner_id=owner_id,
                title=f"참고 자료 {n}",
                url=LINK_URL,
                actor="system",
            )
        ids.append(row.id)
    return ids


async def capability_files(
    session: AsyncSession,
    root: Path | None,
    *,
    instructor_id: int,
    pool_id: str,
    kinds: Sequence[str] = ("pdf", "link"),
) -> list[int]:
    """그 강사의 그 과정 역량(없으면 만든다)에 파일 행을 kinds 순서대로 넣고 파일 행 id 를 돌려준다."""
    capability, _ = await get_or_create_capability(session, instructor_id, pool_id)
    return await _add_files(
        session, root, owner_kind="capability_file", owner_id=capability.id, kinds=kinds
    )


async def own_course_files(
    session: AsyncSession,
    root: Path | None,
    *,
    pool_id: str,
    kinds: Sequence[str] = ("pdf",),
) -> list[int]:
    """고유 과정의 기본 강의안 파일 행 id."""
    return await _add_files(
        session, root, owner_kind="pool_course_file", owner_id=pool_id, kinds=kinds
    )


async def curriculum_with_slots(
    session: AsyncSession,
    root: Path | None,
    *,
    instructor_id: int,
    slots: Sequence[Mapping[str, Any]],
    kinds: Sequence[str] = (),
    **over: Any,
) -> str:
    """그 강사의 커리큘럼(차시 slots — {day, slot, title, description?}, 기본 자료 kinds)의 id."""
    curriculum = await make_curriculum(session, instructor_id=instructor_id, **over)
    await replace_slots(session, curriculum.id, slots)
    await _add_files(
        session, root, owner_kind="curriculum_file", owner_id=curriculum.id, kinds=kinds
    )
    return curriculum.id
