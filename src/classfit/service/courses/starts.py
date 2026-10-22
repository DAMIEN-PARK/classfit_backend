"""개설 시작점 ②(지난 강의 복제)·④(강사 커리큘럼)의 판정·잠금과 구조 채움(T5 결정 iii·iv·v·xvii). flush 까지만.

open.open_course() 안에서만 부른다(단일 진입). 순서: load(판정·잠금, 쓰기 없음) → 강의·일차·초대코드 → apply(구조).
- 복제(load_clone·apply_clone): 원본 강의·섹션·세션은 잠그지 않고 읽는다. 새 세션이 FK 로 가리킬 커리큘럼·풀 과정 행을
  강사보다 먼저 FOR KEY SHARE 로 잡고(결정 xvii ①② — 커리큘럼 시작점과의 교착 방지), 배정 강사를 id 오름차순으로
  lock_assignable 해 승인 강사만 남긴다(복제도 배정이다, 결정 viii). 섹션(title·sort·description)과 세션(title·
  description·keywords·minutes·일차·교시·예외 시각·pool_course_id·curriculum_id)을 복사하고 is_open 은 거짓,
  새 강의 일차 밖은 일차 미정이다. 첨부·일차·초대코드·수강생은 복사하지 않는다. 남은 강사마다 assign_locked 가
  배정·기본 강의안 다시 붙임·audit·outbox 를 쓴다.
- 커리큘럼(load_curriculum·apply_curriculum): 커리큘럼 행을 FOR UPDATE(lock_curriculum)로 잡고, 없으면 404 · 사용
  중지면 409 · 소유 강사가 승인이 아니면 409(instructor_status). 섹션 「전체」 하나에 차시마다 세션(분 = 새 강의 교시,
  일차 밖은 일차 미정), 커리큘럼 기본 자료를 모든 세션에 행 복제, 소유 강사 배정. 검토·공개는 조건이 아니다.
- 원본을 나중에 고쳐도 강의는 그대로다(내용을 복제하고 참조 id 만 둔다, CAT-007).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import course as crud_course
from classfit.crud import curriculum as crud_curriculum
from classfit.crud import materials as crud_materials
from classfit.crud import schedule as crud_schedule
from classfit.crud.materials import SourceSet
from classfit.models import (
    Course,
    CourseSession,
    Curriculum,
    CurriculumSlot,
    Instructor,
    Section,
)
from classfit.schemas.course import CourseOpenIn
from classfit.service.courses import assign, materials

CURRICULUM_SECTION = "전체"  # 시안 관리자.html:1670


@dataclass(frozen=True)
class CloneSource:
    course_id: int
    sections: list[Section]
    sessions: list[CourseSession]
    instructors: dict[int, Instructor]  # 잠근 승인 강사(남길 배정)


@dataclass(frozen=True)
class CurriculumSource:
    curriculum: Curriculum
    owner: Instructor
    slots: list[CurriculumSlot]
    files: SourceSet


Loaded = CloneSource | CurriculumSource


async def load_clone(session: AsyncSession, source_course_id: int) -> CloneSource:
    source = await crud_course.get_course(session, source_course_id)
    if source is None:
        raise NotFound("복제할 강의가 없습니다")
    sections = await crud_schedule.list_sections(session, source_course_id)
    sessions = await crud_schedule.list_sessions(session, source_course_id)
    await crud_materials.key_share_refs(
        session,
        curriculum_ids={s.curriculum_id for s in sessions if s.curriculum_id},
        pool_course_ids={s.pool_course_id for s in sessions if s.pool_course_id},
    )
    kept: dict[int, Instructor] = {}
    for iid in sorted({s.instructor_id for s in sessions if s.instructor_id}):
        try:
            kept[iid] = await assign.lock_assignable(session, iid)
        except Conflict, NotFound:
            continue  # 승인 아닌 강사의 배정은 비운다
    return CloneSource(
        course_id=source_course_id,
        sections=sections,
        sessions=sessions,
        instructors=kept,
    )


async def load_curriculum(
    session: AsyncSession, curriculum_id: str
) -> CurriculumSource:
    curriculum = await crud_curriculum.lock_curriculum(session, curriculum_id)
    if curriculum is None:
        raise NotFound("커리큘럼이 없습니다")
    if not curriculum.active:
        raise Conflict("사용 중지된 커리큘럼입니다")
    owner = await assign.lock_assignable(session, curriculum.instructor_id)
    slots = await crud_curriculum.list_slots(session, curriculum_id)
    files = await crud_materials.curriculum_sources(session, curriculum_id)
    return CurriculumSource(
        curriculum=curriculum, owner=owner, slots=slots, files=files
    )


async def load(session: AsyncSession, body: CourseOpenIn) -> Loaded | None:
    """시작점의 원본을 판정하고 잠근다(쓰기 없음). 빈 강의(①)는 None."""
    if body.start == "clone":
        assert body.source_course_id is not None  # CourseOpenIn 이 422 로 먼저 막는다
        return await load_clone(session, body.source_course_id)
    if body.start == "curriculum":
        assert body.curriculum_id is not None
        return await load_curriculum(session, body.curriculum_id)
    return None


def _place(day_no: int | None, slot: int | None, day_count: int) -> dict[str, Any]:
    """새 강의 일차 밖이면 일차 미정(day_no·slot NULL)."""
    if day_no is None or day_no > day_count:
        return {"day_no": None, "slot": None}
    return {"day_no": day_no, "slot": slot}


async def apply_clone(
    session: AsyncSession,
    course: Course,
    src: CloneSource,
    *,
    day_count: int,
    actor: str,
) -> dict[str, int]:
    by_section: dict[int, list[CourseSession]] = defaultdict(list)
    for row in src.sessions:
        by_section[row.section_id].append(row)
    owned: dict[int, list[CourseSession]] = defaultdict(list)
    for sec in src.sections:
        new_section = await crud_schedule.insert_section(
            session,
            course.id,
            title=sec.title,
            sort=sec.sort,
            description=sec.description,
        )
        for old in sorted(by_section[sec.id], key=lambda r: r.id):
            new = await crud_schedule.insert_session(
                session,
                new_section.id,
                title=old.title,
                description=old.description,
                keywords=list(old.keywords),
                minutes=old.minutes,
                time_start=old.time_start,
                time_end=old.time_end,
                pool_course_id=old.pool_course_id,
                curriculum_id=old.curriculum_id,
                is_open=False,
                **_place(old.day_no, old.slot, day_count),
            )
            if old.instructor_id in src.instructors:
                owned[old.instructor_id].append(new)
    copied = skipped = 0
    for iid in sorted(owned):
        result = await assign.assign_locked(
            session,
            course=course,
            rows=owned[iid],
            instructor=src.instructors[iid],
            actor=actor,
        )
        copied += result.materials
        skipped += result.skipped_missing
    return {"materials": copied, "skipped_missing": skipped}


async def apply_curriculum(
    session: AsyncSession,
    course: Course,
    src: CurriculumSource,
    *,
    day_count: int,
    actor: str,
) -> dict[str, int]:
    section = await crud_schedule.insert_section(
        session, course.id, title=CURRICULUM_SECTION, sort=0, description=None
    )
    rows: list[CourseSession] = []
    copied = 0
    for slot in src.slots:
        row = await crud_schedule.insert_session(
            session,
            section.id,
            title=slot.title,
            description=slot.description,
            keywords=[],
            minutes=course.slot_min,
            curriculum_id=src.curriculum.id,
            is_open=False,
            **_place(slot.day, slot.slot, day_count),
        )
        copied += await materials.copy_sources(
            session, session_id=row.id, sources=src.files.sources
        )
        rows.append(row)
    await assign.assign_locked(
        session, course=course, rows=rows, instructor=src.owner, actor=actor
    )
    return {"materials": copied, "skipped_missing": src.files.skipped_missing}


async def apply(
    session: AsyncSession,
    course: Course,
    loaded: Loaded | None,
    *,
    day_count: int,
    actor: str,
) -> dict[str, int]:
    """load 가 돌려준 원본으로 새 강의의 구조를 채운다. course.open audit detail 에 더할 칸(빈 강의는 {})."""
    if isinstance(loaded, CloneSource):
        return await apply_clone(
            session, course, loaded, day_count=day_count, actor=actor
        )
    if isinstance(loaded, CurriculumSource):
        return await apply_curriculum(
            session, course, loaded, day_count=day_count, actor=actor
        )
    return {}
