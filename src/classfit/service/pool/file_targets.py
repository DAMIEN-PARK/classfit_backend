"""파일 올리기 전 대상 판정(T4 결정 i·viii). 바이트를 읽기 전에 끝점이 부른다. flush 없음(읽기만).

판정 순서는 404(과정·역량·커리큘럼) → 403(남의 것·AX, owned_by) → 409(소유 행이 비활성) → 409(파일 행이
POOL_FILES_MAX 개, limit 칸)이다. 역량은 강사 × 과정 키라 403 이 없고, 그 풀 과정이 비활성이면 409 다.
돌려준 (owner_kind, owner_id) 를 그대로 service.files.pool_files 의 add_pdf_file·add_link_file 에 넘긴다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict
from classfit.crud import pool as crud_pool
from classfit.crud.pool_file import count_file_rows
from classfit.models.pool import POOL_FILES_MAX
from classfit.service.pool.capabilities import get_capability
from classfit.service.pool.curricula import get_own_curriculum
from classfit.service.pool.own import get_own_course

UploadTarget = tuple[str, Any]  # (owner_kind, owner_id)


async def _room(session: AsyncSession, owner_kind: str, owner_id: Any) -> UploadTarget:
    if await count_file_rows(session, owner_kind, owner_id) >= POOL_FILES_MAX:
        raise Conflict(
            f"파일은 {POOL_FILES_MAX}개까지입니다. 하나를 지운 뒤 올리세요",
            limit=POOL_FILES_MAX,
        )
    return owner_kind, owner_id


async def own_course_upload_target(
    session: AsyncSession, *, instructor_id: int, pool_id: str
) -> UploadTarget:
    """고유 과정 파일(pool_course_file)."""
    row = await get_own_course(session, instructor_id=instructor_id, pool_id=pool_id)
    if not row.active:
        raise Conflict("사용 중지된 과정에는 파일을 올릴 수 없습니다")
    return await _room(session, "pool_course_file", row.id)


async def capability_upload_target(
    session: AsyncSession, *, instructor_id: int, pool_id: str
) -> UploadTarget:
    """역량 파일(capability_file). 역량이 없으면 404, 그 풀 과정이 비활성이면 409."""
    row = await get_capability(session, instructor_id=instructor_id, pool_id=pool_id)
    course = await crud_pool.get_pool_course_any(session, pool_id)
    if course is None or not course.active:
        raise Conflict("사용 중지된 과정에는 파일을 올릴 수 없습니다")
    return await _room(session, "capability_file", row.id)


async def curriculum_upload_target(
    session: AsyncSession, *, instructor_id: int, curriculum_id: str
) -> UploadTarget:
    """커리큘럼 파일(curriculum_file)."""
    row = await get_own_curriculum(
        session, instructor_id=instructor_id, curriculum_id=curriculum_id
    )
    if not row.active:
        raise Conflict("사용 중지된 커리큘럼에는 파일을 올릴 수 없습니다")
    return await _room(session, "curriculum_file", row.id)
