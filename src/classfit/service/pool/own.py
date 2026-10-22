"""강사 고유 과정(기획안 I3 :560, T4 결정 i·vi·xi·xvi). flush 까지만.

- 만들기: id own-<강사 id>-<n> → source own · 소유 강사 · reviewed·pub false · active true → audit pool_course.create.
  강사 상태는 보지 않는다(pending·rejected 도 쓴다, 결정 xvi).
- 읽기·고치기·지우기 판정 순서는 404 → 403 → 409 다(결정 i): 범위 없는 get_pool_course_any 로 읽어 없으면 NotFound,
  AX 행이거나 소유 강사가 아니면 Forbidden(owned_by), 고치기는 비활성이면 Conflict.
- 내용 칸이 하나라도 바뀌면 reviewed=false 로 돌린다. reviewed_at·pub·active 는 그대로다(결정 vi).
  바뀐 칸이 없으면 audit 도 없다(같은 값 PATCH).
- 지우기는 active=false 다(결정 xi). 이미 비활성이면 아무것도 쓰지 않는다.
- insert_pool_course 를 부르는 곳은 이 모듈 · admin · catalog_import 셋뿐이다(단일 진입, Design 5절 13).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, Forbidden, NotFound
from classfit.crud import pool as crud_pool
from classfit.crud.audit import insert_audit
from classfit.crud.scope import owned_by
from classfit.models import PoolCourse
from classfit.models.pool import POOL_CONTENT_FIELDS
from classfit.service.pool.common import as_instructor, clean_fields, instructor_actor
from classfit.service.rules import pool as rules

TARGET = "pool_course"


async def create_own_course(
    session: AsyncSession, *, instructor_id: int, fields: Mapping[str, Any]
) -> PoolCourse:
    """fields 는 내용 칸(POOL_CONTENT_FIELDS 안). 새 행을 다시 읽어 돌려준다."""
    content = clean_fields(fields, POOL_CONTENT_FIELDS)
    new_id = await crud_pool.next_id(session, "own", instructor_id, make=rules.pool_id)
    row = await crud_pool.insert_pool_course(
        session,
        id=new_id,
        source="own",
        owner_instructor_id=instructor_id,
        reviewed=False,
        pub=False,
        active=True,
        **content,
    )
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="pool_course.create",
        target_type=TARGET,
        target_id=row.id,
        detail={"source": "own"},
    )
    return row


async def get_own_course(
    session: AsyncSession, *, instructor_id: int, pool_id: str
) -> PoolCourse:
    """본인 고유 과정(비활성 포함). 없으면 NotFound, AX·남의 것이면 Forbidden."""
    row = await crud_pool.get_pool_course_any(session, pool_id)
    if row is None:
        raise NotFound("풀 과정이 없습니다")
    if row.source != "own" or not owned_by(
        as_instructor(instructor_id), row.owner_instructor_id
    ):
        raise Forbidden("본인의 고유 과정만 다룰 수 있습니다")
    return row


async def patch_own_course(
    session: AsyncSession,
    *,
    instructor_id: int,
    pool_id: str,
    changes: Mapping[str, Any],
) -> list[str]:
    """내용 칸을 바꾼다. 바뀐 칸 이름(정렬). 비활성이면 Conflict(관리자가 되살린 뒤 고친다)."""
    row = await get_own_course(session, instructor_id=instructor_id, pool_id=pool_id)
    if not row.active:
        raise Conflict("사용 중지된 과정은 고칠 수 없습니다")
    content = clean_fields(changes, POOL_CONTENT_FIELDS)
    changed = await crud_pool.update_pool_course(session, row, **content)
    if not changed:
        return []
    if row.reviewed:
        await crud_pool.set_flags(session, row, reviewed=False)
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="pool_course.update",
        target_type=TARGET,
        target_id=row.id,
        detail={"changed": changed},
    )
    return changed


async def deactivate_own_course(
    session: AsyncSession, *, instructor_id: int, pool_id: str
) -> bool:
    """active=false. 이번에 껐으면 True, 이미 꺼져 있었으면 False(audit 없음). 행·역량·파일은 남는다."""
    row = await get_own_course(session, instructor_id=instructor_id, pool_id=pool_id)
    if not row.active:
        return False
    await crud_pool.set_flags(session, row, active=False)
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="pool_course.deactivate",
        target_type=TARGET,
        target_id=row.id,
    )
    return True
