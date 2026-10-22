"""과정 풀에서 세션 고르기(기획안 A3 :774, T5 결정 vi). flush 까지만.

- 고른 순서대로 세션을 만든다: 제목 = 과정 제목 · 설명 = 과정 목표 · 분 = 과정 분(일차에 넣으면 강의 교시) ·
  pool_course_id · keywords [] · is_open 거짓 · 강사 없음. 미검토 고유 과정도 고를 수 있다(시안 :1827).
- day 가 있으면 그 일차부터 그 섹션의 빈 교시에 차례로 넣고, 그날이 차면 다음 일차로, 일차가 모자라면 일차 미정이다
  (rules.schedule.place_in_free_slots · 하루 교시 수 slot_count). day 가 없으면 전부 일차 미정이다(넘친 것이 아니다).
- 판정·잠금 순서: ① 섹션이 그 강의 것인지(없으면 404, 아무것도 쓰지 않음) ② 과정 id — 없는 id 404 + missing,
  비활성 409 + inactive ③ 새 세션이 FK 로 가리킬 풀 과정 행 FOR KEY SHARE(결정 xvii) ④ 강의 행 잠금(같은 강의의
  풀 배치 두 요청이 같은 빈 교시를 두 번 주지 않게) ⑤ 섹션을 다시 확인(기다린 사이 지워졌으면 404) ⑥ 그 강의에 없는
  day 409 ⑦ 잠근 뒤 쓴 교시를 읽어 배치 → 세션 넣기.
- 기본 강의안은 여기서 붙지 않는다(고르는 때는 강사가 없다). 배정될 때 붙는다(assign). audit 은 없다(T2a 결정 viii).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import course as crud_course
from classfit.crud import materials as crud_materials
from classfit.crud import pool as crud_pool
from classfit.crud import schedule as crud_schedule
from classfit.models import CourseSession, PoolCourse
from classfit.service.courses import sections
from classfit.service.rules.schedule import place_in_free_slots, slot_count


@dataclass(frozen=True)
class FromPoolResult:
    rows: list[CourseSession]  # 고른 순서
    spilled: int  # day 를 골랐는데 일차가 모자라 일차 미정이 된 수


async def add_from_pool(
    session: AsyncSession,
    *,
    course_id: int,
    section_id: int,
    pool_ids: Sequence[str],
    day: int | None,
) -> FromPoolResult:
    """pool_ids 는 1~20개 · 중복 없음(schemas 가 422 로 먼저 막는다)."""
    await sections.section_in_course(session, course_id, section_id)
    found: dict[str, PoolCourse] = {}
    missing: list[str] = []
    for pid in pool_ids:
        row = await crud_pool.get_pool_course_any(session, pid)
        if row is None:
            missing.append(pid)
        else:
            found[pid] = row
    if missing:
        raise NotFound("풀 과정이 없습니다", missing=missing)
    inactive = [pid for pid in pool_ids if not found[pid].active]
    if inactive:
        raise Conflict("사용 중지된 과정은 고를 수 없습니다", inactive=inactive)
    await crud_materials.key_share_refs(session, pool_course_ids=pool_ids)
    course = await crud_course.lock_course(session, course_id)
    if course is None:
        raise NotFound("이 강의의 섹션이 없습니다")
    await sections.section_in_course(session, course_id, section_id)
    days = await crud_schedule.list_days(session, course_id)
    capacity = {
        d.day_no: slot_count(d, course.slot_min, course.break_min) for d in days
    }
    if day is not None and day not in capacity:
        raise Conflict(f"이 강의에 {day}일차가 없습니다")
    used = await crud_schedule.used_slots(session, section_id)
    places = place_in_free_slots(capacity, used, day, len(pool_ids))
    rows: list[CourseSession] = []
    for pid, place in zip(pool_ids, places, strict=True):
        pool = found[pid]
        rows.append(
            await crud_schedule.insert_session(
                session,
                section_id,
                title=pool.title,
                description=pool.goal,
                minutes=pool.minutes if place is None else course.slot_min,
                day_no=None if place is None else place[0],
                slot=None if place is None else place[1],
                pool_course_id=pid,
                keywords=[],
                is_open=False,
            )
        )
    spilled = 0 if day is None else sum(1 for place in places if place is None)
    return FromPoolResult(rows=rows, spilled=spilled)
