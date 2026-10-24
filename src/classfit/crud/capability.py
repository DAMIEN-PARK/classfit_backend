"""capability(강사 역량) 읽기·쓰기. flush 까지만.

- 역량은 강사 × 풀 과정마다 한 행이다(U instructor_id·pool_course_id). 만들기는 INSERT … ON CONFLICT DO NOTHING 뒤
  읽기라 같은 PUT 이 동시에 와도 23505 가 나지 않는다(T2b get_or_create_learner 꼴, T4 결정 x).
- 목록의 첫 WHERE 는 주체 범위다(crud.scope.capability_scope). service 판정용 읽기는 범위 없는 get_capability_any 다.
- 지우기는 역량 파일 행 → 그 stored_file 행 → 역량 행 순서다(crud.attachment._delete_where 꼴, Design 5절 11).
- 역량 지우기와 그 역량 파일 올리기는 lock_capability 로 역량 행을 먼저 잠근다(잠금 순서 역량 행 → 파일 행 →
  stored_file). 안 잠그면 둘이 겹칠 때 새 파일 행이 지워진 역량을 가리켜 FK 23503 → 500 이 난다(리뷰 Nit 4).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.pool_file import delete_files_of
from classfit.crud.scope import Subject, capability_scope
from classfit.models import Capability, PoolCourse

FILE_KIND = "capability_file"


def _one(instructor_id: int, pool_course_id: str) -> Select[tuple[Capability]]:
    return select(Capability).where(
        Capability.instructor_id == instructor_id,
        Capability.pool_course_id == pool_course_id,
    )


async def get_or_create_capability(
    session: AsyncSession, instructor_id: int, pool_course_id: str
) -> tuple[Capability, bool]:
    """(행, 새로 만들었는지). 있으면 그대로 읽는다."""
    stmt = (
        insert(Capability)
        .values(instructor_id=instructor_id, pool_course_id=pool_course_id)
        .on_conflict_do_nothing(index_elements=["instructor_id", "pool_course_id"])
        .returning(Capability.id)
    )
    created = (await session.execute(stmt)).scalar_one_or_none() is not None
    row = (
        await session.scalars(
            _one(instructor_id, pool_course_id).execution_options(
                populate_existing=True
            )
        )
    ).one()
    return row, created


async def lock_capability(
    session: AsyncSession, instructor_id: int, pool_course_id: str
) -> Capability | None:
    """역량 행을 SELECT … FOR UPDATE 로 잠그고 새로 읽는다. 없으면(그 사이 지워졌으면) None(lock_curriculum 꼴).

    populate_existing: 잠금을 기다린 사이 커밋된 값을 identity map 의 옛 값이 가리지 않게 덮어 읽는다.
    """
    stmt = (
        _one(instructor_id, pool_course_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def get_capability_any(
    session: AsyncSession, instructor_id: int, pool_course_id: str
) -> Capability | None:
    """범위 없는 읽기(service 판정용)."""
    return await session.scalar(_one(instructor_id, pool_course_id))


def list_stmt(subject: Subject) -> Select[tuple[Capability, PoolCourse]]:
    """역량 목록과 그 풀 과정(제목·활성 표시용). 첫 WHERE 는 주체 범위다. 순서 (pool_course_id, id)."""
    return (
        select(Capability, PoolCourse)
        .join(PoolCourse, PoolCourse.id == Capability.pool_course_id)
        .where(capability_scope(subject))
        .order_by(Capability.pool_course_id, Capability.id)
    )


async def list_capabilities(
    session: AsyncSession, subject: Subject, limit: int
) -> tuple[list[tuple[Capability, PoolCourse]], bool]:
    """(앞 limit 쌍, 더 있는지). 한 쪽 규칙(결정 xii)."""
    rows = [
        (c, p)
        for c, p in (await session.execute(list_stmt(subject).limit(limit + 1))).all()
    ]
    return rows[:limit], len(rows) > limit


async def capable_pool_ids(
    session: AsyncSession, instructor_id: int, pool_ids: list[str] | None = None
) -> set[str]:
    """그 강사가 역량을 표시한 풀 과정 id(강사용 풀 목록의 capable). pool_ids 를 주면 그 안에서만."""
    stmt = select(Capability.pool_course_id).where(
        Capability.instructor_id == instructor_id
    )
    if pool_ids is not None:
        if not pool_ids:
            return set()
        stmt = stmt.where(Capability.pool_course_id.in_(pool_ids))
    return set((await session.scalars(stmt)).all())


async def update_memo(session: AsyncSession, row: Capability, memo: Any) -> bool:
    """메모가 다르면 쓰고 flush 뒤 다시 읽는다. 바꿨으면 True."""
    if row.memo == memo:
        return False
    row.memo = memo
    await session.flush()
    await session.refresh(row)
    return True


async def delete_capability(session: AsyncSession, row: Capability) -> int:
    """역량 파일 행 → 그 stored_file 행 → 역량 행 순서로 지운다(같은 트랜잭션). 지운 파일 행 수."""
    files = await delete_files_of(session, FILE_KIND, row.id)
    await session.execute(delete(Capability).where(Capability.id == row.id))
    return files
