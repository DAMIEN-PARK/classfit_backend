"""pool_course 읽기·쓰기와 id 번호. flush 까지만.

- 행 넣기 insert_pool_course 는 service.pool 의 own·admin·catalog_import 세 모듈만 부른다(단일 진입, Design 5절 13).
  PoolCourse( 생성은 이 파일 한 곳이다(tests/integration/test_db_pool.py 가 센다).
- 목록·강사용 상세의 첫 WHERE 는 주체 범위다(crud.scope.pool_scope · own_course_scope). 쓰기·소유 판정용 읽기는
  범위 없는 get_pool_course_any 다(service 가 404 → 403 → 409 로 판정, T4 결정 i).
- id 번호는 시퀀스 pool_id_seq 에서 받고 그 표에 같은 id 가 있으면 다음 번호로 넘어간다(next_id, 결정 xiii).
  id 글자 모양은 부르는 쪽이 make 로 준다(service.rules.pool.pool_id — crud 는 service 를 모른다).
- 목록은 커서 없이 한 쪽이다(Text PK 라 keyset_page 를 못 쓴다, 결정 xii): first_page 가 LIST_LIMIT + 1 로 읽는다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict
from classfit.crud.flush import flush_or_conflict
from classfit.crud.like import LIKE_ESCAPE, contains_pattern
from classfit.crud.scope import Subject, own_course_scope, pool_scope
from classfit.models import (
    AdvancedCourse,
    Capability,
    Curriculum,
    Instructor,
    PoolCourse,
)
from classfit.models.pool import ID_TRIES, POOL_CONTENT_FIELDS, POOL_FLAGS

SEQUENCE = "pool_id_seq"
LIST_LIMIT = 500  # 한 쪽 상한(결정 xii)
# id 접두 → 같은 id 를 찾아볼 표
_ID_TABLES: dict[str, type[PoolCourse | Curriculum | AdvancedCourse]] = {
    "ax-custom": PoolCourse,
    "own": PoolCourse,
    "cur": Curriculum,
    "adv": AdvancedCourse,
}


async def next_id(
    session: AsyncSession,
    prefix: str,
    instructor_id: int | None = None,
    *,
    make: Callable[[str, int, int | None], str],
) -> str:
    """접두의 새 id. nextval 로 후보를 만들고 그 표에 이미 있으면 다음 번호로, ID_TRIES 번 넘으면 Conflict(409).

    import 가 파일 값(adv-1 …)을 그대로 넣으므로 번호만으로는 겹칠 수 있다(결정 xiii). nextval 은 롤백돼도 소비된다.
    """
    model = _ID_TABLES[prefix]
    for _ in range(ID_TRIES):
        n = await session.scalar(select(func.nextval(SEQUENCE)))
        candidate = make(prefix, int(n), instructor_id)
        if not await session.scalar(select(exists().where(model.id == candidate))):
            return candidate
    raise Conflict("새 id 를 만들지 못했습니다. 다시 시도하세요")


async def insert_pool_course(session: AsyncSession, **fields: Any) -> PoolCourse:
    """풀 과정 1행. 같은 id 면 Conflict(409). 넣은 뒤 다시 읽어 서버 기본값을 채운다."""
    row = PoolCourse(**fields)
    await flush_or_conflict(session, "같은 id 의 풀 과정이 있습니다", row)
    await session.refresh(row)
    return row


async def get_pool_course(
    session: AsyncSession, subject: Subject, pool_id: str
) -> PoolCourse | None:
    """범위 안의 풀 과정 하나(강사는 활성만). 범위 밖이면 None(끝점 404)."""
    stmt = select(PoolCourse).where(pool_scope(subject)).where(PoolCourse.id == pool_id)
    return await session.scalar(stmt)


async def get_pool_course_any(session: AsyncSession, pool_id: str) -> PoolCourse | None:
    """범위 없는 읽기(service 판정용). source 를 가리지 않아 AX id 도 행을 돌려준다."""
    return await session.get(PoolCourse, pool_id)


def list_stmt(
    subject: Subject,
    *,
    source: str | None = None,
    job: str | None = None,
    difficulty: str | None = None,
    q: str | None = None,
    active: bool | None = None,
    reviewed: bool | None = None,
) -> Select[tuple[PoolCourse]]:
    """풀 목록. 첫 WHERE 는 주체 범위다(강사는 활성만). q 는 제목·목표·산출물 부분 일치. 순서 (source, id)."""
    stmt = select(PoolCourse).where(pool_scope(subject))
    if source is not None:
        stmt = stmt.where(PoolCourse.source == source)
    if job is not None:
        stmt = stmt.where(PoolCourse.job_groups.any(job))
    if difficulty is not None:
        stmt = stmt.where(PoolCourse.difficulty == difficulty)
    if q:
        pattern = contains_pattern(q)
        stmt = stmt.where(
            or_(
                PoolCourse.title.ilike(pattern, escape=LIKE_ESCAPE),
                PoolCourse.goal.ilike(pattern, escape=LIKE_ESCAPE),
                PoolCourse.output.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if active is not None:
        stmt = stmt.where(PoolCourse.active.is_(active))
    if reviewed is not None:
        stmt = stmt.where(PoolCourse.reviewed.is_(reviewed))
    return stmt.order_by(PoolCourse.source, PoolCourse.id)


def list_own_stmt(subject: Subject) -> Select[tuple[PoolCourse]]:
    """고유 과정 목록(비활성 포함). 첫 WHERE 는 주체 범위다. 순서 (id)."""
    return (
        select(PoolCourse)
        .where(own_course_scope(subject))
        .where(PoolCourse.source == "own")
        .order_by(PoolCourse.id)
    )


async def first_page[T](
    session: AsyncSession, stmt: Select[tuple[T]], limit: int = LIST_LIMIT
) -> tuple[list[T], bool]:
    """(앞 limit 행, 더 있는지). limit + 1 로 읽어 잘리면 True(next_cursor 는 늘 null, 결정 xii)."""
    rows = list((await session.scalars(stmt.limit(limit + 1))).all())
    return rows[:limit], len(rows) > limit


async def apply_changes(session: AsyncSession, row: Any, fields: dict[str, Any]) -> list[str]:
    """준 칸 중 현재 값과 다른 칸만 쓰고 flush 뒤 다시 읽는다. 바뀐 칸 이름(정렬)을 돌려준다(T2a 꼴).

    풀 과정·커리큘럼·심화가 같이 쓴다. 바뀐 칸이 없으면 아무것도 쓰지 않는다(같은 값 PATCH 는 audit 없음).
    """
    changed = {k: v for k, v in fields.items() if getattr(row, k) != v}
    for name, value in changed.items():
        setattr(row, name, value)
    if changed:
        await session.flush()
        await session.refresh(row)
    return sorted(changed)


async def update_pool_course(
    session: AsyncSession, row: PoolCourse, **fields: Any
) -> list[str]:
    """내용 칸·플래그를 바꾼다. 바뀐 칸 이름(정렬)."""
    return await apply_changes(session, row, fields)


async def set_flags(session: AsyncSession, row: PoolCourse, **flags: Any) -> list[str]:
    """플래그 reviewed·pub·active 와 reviewed_at 만. 바뀐 칸 이름(정렬). 규칙(검토 ⇒ 공개)은 service 몫이다."""
    allowed = {*POOL_FLAGS, "reviewed_at"}
    if unknown := set(flags) - allowed:
        raise ValueError(f"플래그가 아니다: {sorted(unknown)}")
    return await apply_changes(session, row, flags)


def content_fields(row: PoolCourse) -> dict[str, Any]:
    """내용 칸 dict(import 지문용, 결정 iii)."""
    return {name: getattr(row, name) for name in POOL_CONTENT_FIELDS}


async def capable_counts(
    session: AsyncSession, pool_ids: Iterable[str]
) -> dict[str, int]:
    """풀 과정마다 역량을 표시한 강사 수(관리자 목록). 하나도 없으면 키가 없다(부르는 쪽이 0 으로)."""
    ids = list(pool_ids)
    if not ids:
        return {}
    stmt = (
        select(Capability.pool_course_id, func.count())
        .where(Capability.pool_course_id.in_(ids))
        .group_by(Capability.pool_course_id)
    )
    return {pid: n for pid, n in (await session.execute(stmt)).all()}


async def capable_instructors(
    session: AsyncSession, pool_id: str
) -> list[tuple[int, str]]:
    """그 풀 과정에 역량을 표시한 강사 (id, 이름)(관리자 상세). 순서 (강사 id)."""
    stmt = (
        select(Instructor.id, Instructor.name)
        .join(Capability, Capability.instructor_id == Instructor.id)
        .where(Capability.pool_course_id == pool_id)
        .order_by(Instructor.id)
    )
    return [(iid, name) for iid, name in (await session.execute(stmt)).all()]


async def owner_names(
    session: AsyncSession, instructor_ids: Iterable[int | None]
) -> dict[int, str]:
    """강사 id → 이름(관리자 목록·상세의 owner{id, name}). None 은 건너뛴다."""
    ids = sorted({i for i in instructor_ids if i is not None})
    if not ids:
        return {}
    stmt = select(Instructor.id, Instructor.name).where(Instructor.id.in_(ids))
    return {iid: name for iid, name in (await session.execute(stmt)).all()}
