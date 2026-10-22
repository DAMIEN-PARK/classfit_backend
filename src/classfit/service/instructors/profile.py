"""강사 본인의 프로필 고치기(patch_profile)와 재신청(reapply). flush 까지만.

- patch_profile 은 끝점이 넘긴 바뀐 칸 dict(준 칸만)를 받는다. tags 가 있으면 먼저 중지 태그를 본다(있으면 InactiveTags,
  아직 아무 행도 쓰지 않았다) → 새 분야 태그 → 칸 쓰기 → 태그 맞추기. 실제로 바뀐 칸 이름만 돌려준다.
- 분야 0개·글자 길이는 끝점의 스키마가 422 로 막는다. 상태와 무관하게 대기·반려 강사도 고칠 수 있다(T3 결정 v).
- reapply 는 반려 → 대기 하나다(T3 결정 xii). 강사 행을 잠근 뒤 status 의 전이 적용을 쓴다: 사유 NULL ·
  audit instructor.reapply(이전 사유는 반려 audit 의 detail 에만 남는다). 반려가 아니면 Conflict(409).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import instructor as crud_instructor
from classfit.models import Instructor
from classfit.service.instructors.signup import resolve_field_tags
from classfit.service.instructors.status import apply_transition

PROFILE_FIELDS = frozenset({"name", "phone", "org", "intro", "career"})


async def patch_profile(
    session: AsyncSession, row: Instructor, changes: dict[str, Any]
) -> list[str]:
    """(실제로 바뀐 칸 이름, 정렬). 같은 값이면 쓰지 않는다. tags 는 이름 목록이다."""
    fields = dict(changes)
    names = fields.pop("tags", None)
    unknown = set(fields) - PROFILE_FIELDS
    if unknown:
        raise ValueError(f"고칠 수 없는 칸: {sorted(unknown)}")
    tag_ids = None if names is None else await resolve_field_tags(session, names)
    if "career" in fields:
        fields["career"] = list(fields["career"])
    changed = await crud_instructor.update_instructor(session, row, **fields)
    if tag_ids is not None and await crud_instructor.replace_tags(
        session, row.id, tag_ids
    ):
        changed.append("tags")
    return sorted(changed)


async def reapply(
    session: AsyncSession, *, instructor_id: int, actor: str
) -> Instructor:
    """반려 → 대기. 강사가 없으면 NotFound(404), 반려가 아니면 Conflict(409, current_status)."""
    row = await crud_instructor.lock_instructor(session, instructor_id)
    if row is None:
        raise NotFound("강사가 없습니다")
    return await apply_transition(session, row, action="reapply", actor=actor)
