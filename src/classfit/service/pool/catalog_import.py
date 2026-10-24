"""AX 카탈로그 import(scripts.import_ax_catalog, T4 결정 ii·iii·iv). flush 까지만 — 커밋·롤백은 스크립트가 한다.

- 키는 id 다(기획안 :243 "id 고정"). 없는 id 는 넣는다(inserted). 있는 id 는 어떤 칸도 쓰지 않는다 —
  내용 지문(service.rules.pool.content_fingerprint)이 같으면 unchanged, 다르면 differs 로 보고만 한다(결정 iii).
  플랫폼이 원본이므로 이관 뒤 고치는 길은 관리자 PATCH 하나다(원칙 6).
- 새 과정은 source ax · reviewed true(reviewed_at 지금) · pub true · active true, 새 심화는 pub·active true(결정 iv).
  재실행은 기존 행의 pub·active 를 건드리지 않는다.
- 새로 넣은 것이 있으면 audit 1행(actor system, pool_course.import, detail 여섯 개수). 0건이면 audit 없음.
  미리 보기도 끝까지 돌고 스크립트가 롤백한다(scripts.create_admin 꼴).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import advanced as crud_advanced
from classfit.crud import pool as crud_pool
from classfit.crud.audit import insert_audit
from classfit.models.advanced import ADVANCED_CONTENT_FIELDS
from classfit.schemas.catalog_import import AxCatalogFileIn
from classfit.service.rules.pool import content_fingerprint


@dataclass
class SectionResult:
    inserted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    differs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "inserted": self.inserted,
            "unchanged": self.unchanged,
            "differs": self.differs,
        }


@dataclass
class ImportResult:
    applied: bool
    courses: SectionResult = field(default_factory=SectionResult)
    advanced: SectionResult = field(default_factory=SectionResult)

    def as_dict(self) -> dict[str, Any]:
        """스크립트 stdout 모양 {applied, courses: {inserted, unchanged, differs}, advanced: {…}}."""
        return {
            "applied": self.applied,
            "courses": self.courses.as_dict(),
            "advanced": self.advanced.as_dict(),
        }

    def counts(self) -> dict[str, int]:
        """audit detail 의 여섯 개수."""
        return {
            "inserted": len(self.courses.inserted),
            "unchanged": len(self.courses.unchanged),
            "differs": len(self.courses.differs),
            "advanced_inserted": len(self.advanced.inserted),
            "advanced_unchanged": len(self.advanced.unchanged),
            "advanced_differs": len(self.advanced.differs),
        }


def _classify(
    result: SectionResult, item_id: str, stored: dict[str, Any], given: dict[str, Any]
) -> None:
    if content_fingerprint(stored) == content_fingerprint(given):
        result.unchanged.append(item_id)
    else:
        result.differs.append(item_id)


async def import_ax_catalog(
    session: AsyncSession, data: AxCatalogFileIn, *, apply: bool
) -> ImportResult:
    """파일의 과정·심화를 id 로 맞춰 없는 것만 넣는다. apply 는 결과에 싣기만 한다(커밋은 스크립트)."""
    result = ImportResult(applied=apply)
    now = datetime.now(UTC)
    for course in data.courses:
        given = course.content()
        row = await crud_pool.get_pool_course_any(session, course.id)
        if row is None:
            await crud_pool.insert_pool_course(
                session,
                id=course.id,
                source="ax",
                owner_instructor_id=None,
                reviewed=True,
                reviewed_at=now,
                pub=True,
                active=True,
                **given,
            )
            result.courses.inserted.append(course.id)
        else:
            _classify(result.courses, course.id, crud_pool.content_fields(row), given)
    for item in data.advanced:
        given = item.content()
        row = await crud_advanced.get_advanced(session, item.id)
        if row is None:
            await crud_advanced.insert_advanced(
                session, id=item.id, pub=True, active=True, **given
            )
            result.advanced.inserted.append(item.id)
        else:
            stored = {name: getattr(row, name) for name in ADVANCED_CONTENT_FIELDS}
            _classify(result.advanced, item.id, stored, given)
    if result.courses.inserted or result.advanced.inserted:
        await insert_audit(
            session,
            actor="system",
            action="pool_course.import",
            target_type="pool_course",
            detail=result.counts(),
        )
    return result
