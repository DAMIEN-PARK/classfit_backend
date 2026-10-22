"""관리자 과정 풀·커리큘럼 플래그·심화 과정(기획안 A3 :765-790, T4 결정 v·xiii·xvii·xviii). flush 까지만.

- AX 추가: id ax-custom-<n> → source ax · reviewed true(reviewed_at 지금) · pub false · active true(관리자.html:1476).
- 풀 과정 PATCH: AX 행은 내용 칸 + pub·active, 고유 과정 행은 reviewed·pub·active 만이다. 고유 과정의 내용 칸이나
  AX 행의 reviewed 가 오면 NotEditable(422, 아무것도 쓰지 않는다).
- 플래그는 한 본문 안에서 reviewed → pub → active 순으로 따진다(결정 v): reviewed 켜기는 reviewed_at=지금,
  끄기는 reviewed_at=NULL 이고 pub 도 끈다. pub=true 는 (이 본문 적용 뒤) reviewed 여야 하고 아니면
  Conflict(409, reviewed: false 칸) — 아무것도 쓰지 않는다. 커리큘럼 플래그 PATCH 도 같은 규칙이다.
- 바뀐 칸이 있으면 요청마다 audit 1행(<종류>.update, detail {changed}), 없으면 없다. reviewed_at 은 changed 에 넣지 않는다.
- 심화 과정: id adv-<n>(import 가 넣은 id 는 next_id 가 건너뛴다) · pub false · active true. 지우기는 없다.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import advanced as crud_advanced
from classfit.crud import curriculum as crud_curriculum
from classfit.crud import pool as crud_pool
from classfit.crud.audit import insert_audit
from classfit.models import AdvancedCourse, Curriculum, PoolCourse
from classfit.models.advanced import ADVANCED_CONTENT_FIELDS
from classfit.models.pool import POOL_CONTENT_FIELDS, POOL_FLAGS
from classfit.service.pool.common import clean_fields, not_editable
from classfit.service.rules import pool as rules

ADVANCED_FLAGS = ("pub", "active")


def _next_flags(
    row: PoolCourse | Curriculum, changes: Mapping[str, Any]
) -> dict[str, Any]:
    """본문의 플래그를 reviewed → pub → active 순으로 따져 쓸 값을 정한다. 공개 조건이 깨지면 Conflict."""
    out: dict[str, Any] = {}
    reviewed = changes.get("reviewed", row.reviewed)
    if "reviewed" in changes and reviewed != row.reviewed:
        out["reviewed"] = reviewed
        out["reviewed_at"] = datetime.now(UTC) if reviewed else None
    if "pub" in changes:
        if changes["pub"] and not reviewed:
            raise Conflict("검토하지 않은 항목은 공개할 수 없습니다", reviewed=False)
        out["pub"] = changes["pub"]
    elif out.get("reviewed") is False and row.pub:
        # 이 본문이 검토를 풀면 공개도 내린다(관리자.html:1548-1549). 검토 뒤 강사가 고쳐 reviewed 만 false 인
        # 공개 항목은 다른 플래그 PATCH 로 내려가지 않는다(결정 vi)
        out["pub"] = False
    if "active" in changes:
        out["active"] = changes["active"]
    return out


async def _audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    target: str,
    target_id: str,
    changed: list[str],
) -> None:
    await insert_audit(
        session,
        actor=actor,
        action=action,
        target_type=target,
        target_id=target_id,
        detail={"changed": changed},
    )


def _reported(changed: list[str]) -> list[str]:
    return [name for name in changed if name != "reviewed_at"]


async def create_ax_course(
    session: AsyncSession, *, actor: str, fields: Mapping[str, Any]
) -> PoolCourse:
    """관리자 AX 과정 추가. fields 는 내용 칸."""
    content = clean_fields(fields, POOL_CONTENT_FIELDS)
    new_id = await crud_pool.next_id(session, "ax-custom", make=rules.pool_id)
    row = await crud_pool.insert_pool_course(
        session,
        id=new_id,
        source="ax",
        owner_instructor_id=None,
        reviewed=True,
        reviewed_at=datetime.now(UTC),
        pub=False,
        active=True,
        **content,
    )
    await insert_audit(
        session,
        actor=actor,
        action="pool_course.create",
        target_type="pool_course",
        target_id=row.id,
        detail={"source": "ax"},
    )
    return row


async def patch_pool_course(
    session: AsyncSession, *, actor: str, pool_id: str, changes: Mapping[str, Any]
) -> list[str]:
    """풀 과정 하나를 고친다. 바뀐 칸 이름(정렬). 없으면 NotFound."""
    row = await crud_pool.get_pool_course_any(session, pool_id)
    if row is None:
        raise NotFound("풀 과정이 없습니다")
    fields = clean_fields(changes, (*POOL_CONTENT_FIELDS, *POOL_FLAGS))
    content = {k: v for k, v in fields.items() if k in POOL_CONTENT_FIELDS}
    if row.source == "own" and content:
        raise not_editable(content, "고유 과정의 내용은 강사만 고칩니다")
    if row.source == "ax" and "reviewed" in fields:
        raise not_editable(["reviewed"], "AX 과정에는 검토 표시가 없습니다")
    flags = _next_flags(row, fields)
    changed = await crud_pool.update_pool_course(session, row, **content, **flags)
    if reported := _reported(changed):
        await _audit(
            session,
            actor=actor,
            action="pool_course.update",
            target="pool_course",
            target_id=row.id,
            changed=reported,
        )
    return reported


async def patch_curriculum_flags(
    session: AsyncSession, *, actor: str, curriculum_id: str, changes: Mapping[str, Any]
) -> list[str]:
    """커리큘럼의 reviewed·pub·active 를 바꾼다(내용은 강사 몫). 바뀐 칸 이름(정렬). 없으면 NotFound."""
    row = await crud_curriculum.get_curriculum_any(session, curriculum_id)
    if row is None:
        raise NotFound("커리큘럼이 없습니다")
    flags = _next_flags(row, clean_fields(changes, POOL_FLAGS))
    changed = await crud_curriculum.set_flags(session, row, **flags)
    if reported := _reported(changed):
        await _audit(
            session,
            actor=actor,
            action="curriculum.update",
            target="curriculum",
            target_id=row.id,
            changed=reported,
        )
    return reported


async def create_advanced(
    session: AsyncSession, *, actor: str, fields: Mapping[str, Any]
) -> AdvancedCourse:
    """심화 과정 추가. fields 는 내용 칸(ADVANCED_CONTENT_FIELDS)."""
    content = clean_fields(fields, ADVANCED_CONTENT_FIELDS)
    new_id = await crud_pool.next_id(session, "adv", make=rules.pool_id)
    row = await crud_advanced.insert_advanced(
        session, id=new_id, pub=False, active=True, **content
    )
    await insert_audit(
        session,
        actor=actor,
        action="advanced_course.create",
        target_type="advanced_course",
        target_id=row.id,
    )
    return row


async def patch_advanced(
    session: AsyncSession, *, actor: str, advanced_id: str, changes: Mapping[str, Any]
) -> list[str]:
    """심화 과정의 내용 칸·pub·active 를 바꾼다. 바뀐 칸 이름(정렬). 없으면 NotFound."""
    row = await crud_advanced.get_advanced(session, advanced_id)
    if row is None:
        raise NotFound("심화 과정이 없습니다")
    fields = clean_fields(changes, (*ADVANCED_CONTENT_FIELDS, *ADVANCED_FLAGS))
    changed = await crud_advanced.update_advanced(session, row, **fields)
    if changed:
        await _audit(
            session,
            actor=actor,
            action="advanced_course.update",
            target="advanced_course",
            target_id=row.id,
            changed=changed,
        )
    return changed
