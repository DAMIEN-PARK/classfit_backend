"""공개 카탈로그 질의 published_catalog()(r3 부록 B T4 :304, 기획안 P2 :416). 끝점은 없다(ADR-004 결정 4).

- 조건은 셋 다 active ∧ pub 뿐이다(Design 부록 A T4, T4 결정 vii). reviewed 는 조건이 아니다 —
  검토 뒤 강사가 고친 공개 항목도 나간다(결정 vi).
- 출력 칸에 강사 id·이름·이메일·파일 href 가 없다. 강사 표를 join 하지 않는다. 출처는 source(ax·own)까지만이다
  (기획안 :435). 고유 과정·커리큘럼 id 글자에는 작성 강사 번호가 들어 있다(own-<n>-… · cur-<n>-…, 결정 vii·xiii).
- 순서는 과정 (source, id) · 커리큘럼 (id) · 심화 (id), 차시는 (일, 교시)다.
- published_ax_courses(T9a 권장 구성 후보): 공개 ∧ 활성 AX 풀 과정만 읽는 얇은 질의(id 순). 강사 고유 과정은 빼고
  curricula·slots·advanced 는 읽지 않는다 — 리포트 GET 마다·회사 잠금 아래의 확정에서 돈다(T9a 결정 viii).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.curriculum import slots_by_curriculum
from classfit.models import AdvancedCourse, Curriculum, PoolCourse


@dataclass(frozen=True)
class CatalogCourse:
    id: str
    source: str
    title: str
    job_groups: list[str]
    difficulty: str
    minutes: int
    goal: str | None
    output: str | None
    material: str | None
    theory: list[str]
    practice: list[str]
    schedule: list[Any]


@dataclass(frozen=True)
class CatalogSlot:
    day: int
    slot: int
    title: str
    description: str | None


@dataclass(frozen=True)
class CatalogCurriculum:
    id: str
    title: str
    job_groups: list[str]
    difficulty: str
    days: int
    start_time: dt.time
    end_time: dt.time
    slot_min: int
    break_min: int
    goal: str | None
    output: str | None
    slots: list[CatalogSlot]


@dataclass(frozen=True)
class CatalogAdvanced:
    id: str
    title: str
    audience: str
    tool: str
    hours: int
    goal: str | None
    features: list[str]


@dataclass(frozen=True)
class Catalog:
    courses: list[CatalogCourse]
    curricula: list[CatalogCurriculum]
    advanced: list[CatalogAdvanced]


def _course(row: PoolCourse) -> CatalogCourse:
    return CatalogCourse(
        id=row.id,
        source=row.source,
        title=row.title,
        job_groups=list(row.job_groups),
        difficulty=row.difficulty,
        minutes=row.minutes,
        goal=row.goal,
        output=row.output,
        material=row.material,
        theory=list(row.theory),
        practice=list(row.practice),
        schedule=list(row.schedule),
    )


def _curriculum(row: Curriculum, slots: list[CatalogSlot]) -> CatalogCurriculum:
    return CatalogCurriculum(
        id=row.id,
        title=row.title,
        job_groups=list(row.job_groups),
        difficulty=row.difficulty,
        days=row.days,
        start_time=row.start_time,
        end_time=row.end_time,
        slot_min=row.slot_min,
        break_min=row.break_min,
        goal=row.goal,
        output=row.output,
        slots=slots,
    )


def _advanced(row: AdvancedCourse) -> CatalogAdvanced:
    return CatalogAdvanced(
        id=row.id,
        title=row.title,
        audience=row.audience,
        tool=row.tool,
        hours=row.hours,
        goal=row.goal,
        features=list(row.features),
    )


async def published_ax_courses(session: AsyncSession) -> list[CatalogCourse]:
    """공개 ∧ 활성인 AX 풀 과정(source == "ax"), id 순."""
    rows = (
        await session.scalars(
            select(PoolCourse)
            .where(
                PoolCourse.source == "ax",
                PoolCourse.active.is_(True),
                PoolCourse.pub.is_(True),
            )
            .order_by(PoolCourse.id)
        )
    ).all()
    return [_course(r) for r in rows]


async def published_catalog(session: AsyncSession) -> Catalog:
    """공개 ∧ 활성인 풀 과정·커리큘럼·심화 과정."""
    courses = (
        await session.scalars(
            select(PoolCourse)
            .where(PoolCourse.active.is_(True), PoolCourse.pub.is_(True))
            .order_by(PoolCourse.source, PoolCourse.id)
        )
    ).all()
    curricula = (
        await session.scalars(
            select(Curriculum)
            .where(Curriculum.active.is_(True), Curriculum.pub.is_(True))
            .order_by(Curriculum.id)
        )
    ).all()
    advanced = (
        await session.scalars(
            select(AdvancedCourse)
            .where(AdvancedCourse.active.is_(True), AdvancedCourse.pub.is_(True))
            .order_by(AdvancedCourse.id)
        )
    ).all()
    slots = await slots_by_curriculum(session, [c.id for c in curricula])
    return Catalog(
        courses=[_course(r) for r in courses],
        curricula=[
            _curriculum(
                c,
                [
                    CatalogSlot(s.day, s.slot, s.title, s.description)
                    for s in slots.get(c.id, [])
                ],
            )
            for c in curricula
        ],
        advanced=[_advanced(r) for r in advanced],
    )
