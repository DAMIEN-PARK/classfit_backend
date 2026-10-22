"""강사 역량(가능 표시, 기획안 I3 :560, T4 결정 x). flush 까지만.

- PUT 하나가 만들기와 메모 갱신을 다 한다: 풀 과정이 없으면 NotFound → 비활성이면 Conflict → get-or-create
  (ON CONFLICT DO NOTHING) → 메모. 소유 판정은 없다 — AX·남의 고유 과정에도 표시할 수 있다.
  audit 은 새로 만들었으면 capability.create, 메모만 바뀌었으면 capability.update, 그대로면 없다.
- 지우기는 행을 지운다: 역량 파일 행 → 그 stored_file 행 → 역량 행(crud 한 함수) → audit capability.delete.
- 관리자 확인·보완 요청·관리자 추천은 1차 제외다(spec A2-8 · A3-5 · DEC-015).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import capability as crud_capability
from classfit.crud import pool as crud_pool
from classfit.crud.audit import insert_audit
from classfit.models import Capability
from classfit.service.pool.common import instructor_actor

TARGET = "capability"


async def put_capability(
    session: AsyncSession, *, instructor_id: int, pool_id: str, memo: str | None
) -> tuple[Capability, bool]:
    """(역량 행, 새로 만들었는지). 끝점은 새로 만들었으면 201, 아니면 200."""
    course = await crud_pool.get_pool_course_any(session, pool_id)
    if course is None:
        raise NotFound("풀 과정이 없습니다")
    if not course.active:
        raise Conflict("사용 중지된 과정에는 역량을 표시할 수 없습니다")
    row, created = await crud_capability.get_or_create_capability(
        session, instructor_id, pool_id
    )
    memo_changed = await crud_capability.update_memo(session, row, memo)
    if created or memo_changed:
        await insert_audit(
            session,
            actor=instructor_actor(instructor_id),
            action="capability.create" if created else "capability.update",
            target_type=TARGET,
            target_id=str(row.id),
            detail={"pool_id": pool_id},
        )
    return row, created


async def get_capability(
    session: AsyncSession, *, instructor_id: int, pool_id: str
) -> Capability:
    """본인의 그 풀 과정 역량. 없으면 NotFound."""
    row = await crud_capability.get_capability_any(session, instructor_id, pool_id)
    if row is None:
        raise NotFound("역량이 없습니다")
    return row


async def remove_capability(
    session: AsyncSession, *, instructor_id: int, pool_id: str
) -> None:
    """역량과 그 파일 행·stored_file 행을 지운다. 없으면 NotFound."""
    row = await get_capability(session, instructor_id=instructor_id, pool_id=pool_id)
    capability_id = row.id
    files = await crud_capability.delete_capability(session, row)
    await insert_audit(
        session,
        actor=instructor_actor(instructor_id),
        action="capability.delete",
        target_type=TARGET,
        target_id=str(capability_id),
        detail={"pool_id": pool_id, "files": files},
    )
