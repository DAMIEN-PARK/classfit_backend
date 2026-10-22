"""기본 강의안 원본 읽기와 잠금(T5 결정 x·xvii). flush 까지만 — 여기는 읽고 잠그기만 한다(T4 표에 쓰지 않는다).

- 원본은 T4 풀 파일 표 셋이다. 표는 crud.pool_file.file_model(owner_kind) 로 고르고 소유 칸은 model.owner_fk 로 잡는다.
  list_file_rows 는 sha256·content_type 을 주지 않아 쓰지 않는다.
- 배정 강사의 원본 순서: ① 그 강사가 고유 과정의 소유자면 pool_course_file (sort, id) ② 그 강사의 역량
  capability_file (sort, id). 소유자가 아닌 강사에게는 남의 pool_course_file 을 주지 않는다(T4 결정 ix).
- 원본은 복사가 커밋될 때까지 잠근다(codex 1차 #2): ⓐ 역량이면 capability 행 FOR KEY SHARE(역량 삭제·역량 파일
  올리기의 lock_capability FOR UPDATE 와 줄 선다) ⓑ 원본 stored_file 행을 id 오름차순 FOR SHARE(삭제와 충돌).
  잠그려는 순간 이미 지워진 행은 PG 가 돌려주지 않는다 — 고른 id 와 잠근 id 의 차이를 skipped_missing 으로 센다.
- 잠금 ⑤⑥ 의 순서는 (강사, 과정) 묶음마다 capability → 원본 stored_file id 오름차순이다(pool_sources 한 번이 한 묶음).
  일괄 배정·복제처럼 묶음이 여럿이면 묶음 사이 순서는 섞일 수 있으나, 여기 잠금은 모두 공유 잠금이고 배타 쪽(역량 삭제
  lock_capability · 풀 파일 한 개 삭제)은 한 묶음만 건드려 고리가 생기지 않는다(T5 리뷰 Nit 2).
- 세션 행을 넣는 경로는 FK 검사가 잡을 참조 행(curriculum → pool_course)을 강사보다 먼저 id 순으로 잡는다
  (key_share_refs, 결정 xvii ①②). 잠금 꼴: FOR KEY SHARE = with_for_update(read=True, key_share=True),
  FOR SHARE = with_for_update(read=True).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.pool_file import file_model
from classfit.models import Capability, Curriculum, PoolCourse, StoredFile

POOL_COURSE_FILE = "pool_course_file"
CAPABILITY_FILE = "capability_file"
CURRICULUM_FILE = "curriculum_file"


@dataclass(frozen=True)
class MaterialSource:
    """원본 파일 행 하나. link 는 sha256·content_type·size 가 None 이다."""

    origin: str  # 원본 owner_kind(= session_attachment.origin)
    kind: str
    title: str
    url: str | None
    sha256: str | None
    content_type: str | None
    size: int | None


@dataclass(frozen=True)
class SourceSet:
    sources: list[MaterialSource]
    skipped_missing: int  # 잠그려는 순간 사라져 건너뛴 원본 파일 수


async def key_share_refs(
    session: AsyncSession,
    *,
    curriculum_ids: Collection[str] = (),
    pool_course_ids: Collection[str] = (),
) -> None:
    """새 세션이 FK 로 가리킬 참조 행을 curriculum 먼저·pool_course 다음, 각각 id 오름차순 FOR KEY SHARE 로 잡는다."""
    if curriculum_ids:
        await session.execute(
            select(Curriculum.id)
            .where(Curriculum.id.in_(sorted(set(curriculum_ids))))
            .order_by(Curriculum.id)
            .with_for_update(read=True, key_share=True)
        )
    if pool_course_ids:
        await session.execute(
            select(PoolCourse.id)
            .where(PoolCourse.id.in_(sorted(set(pool_course_ids))))
            .order_by(PoolCourse.id)
            .with_for_update(read=True, key_share=True)
        )


async def share_sources(
    session: AsyncSession, stored_file_ids: Collection[int]
) -> set[int]:
    """원본 stored_file 을 id 오름차순 FOR SHARE 로 잡고 잡은 id 집합을 돌려준다. 이미 지워진 행은 빠진다."""
    if not stored_file_ids:
        return set()
    stmt = (
        select(StoredFile.id)
        .where(StoredFile.id.in_(sorted(set(stored_file_ids))))
        .order_by(StoredFile.id)
        .with_for_update(read=True)
    )
    return set((await session.scalars(stmt)).all())


async def _file_rows(
    session: AsyncSession, owner_kind: str, owner_id: Any
) -> list[tuple[str, Any, StoredFile | None]]:
    """(owner_kind, 파일 행, stored_file 행) — (sort, id) 순. file_id 없는 비 link 행(넣다 만 행)은 빠진다."""
    model = file_model(owner_kind)
    owner = getattr(model, model.owner_fk)
    stmt = (
        select(model, StoredFile)
        .outerjoin(StoredFile, StoredFile.id == model.file_id)
        .where(owner == owner_id)
        .order_by(model.sort, model.id)
    )
    return [
        (owner_kind, row, stored)
        for row, stored in (await session.execute(stmt)).all()
        if row.kind == "link" or stored is not None
    ]


def _stored_ids(rows: Sequence[tuple[str, Any, StoredFile | None]]) -> list[int]:
    return [stored.id for _, _, stored in rows if stored is not None]


def _source_set(
    rows: Sequence[tuple[str, Any, StoredFile | None]], held: set[int]
) -> SourceSet:
    """잠근 stored_file(held)과 link 만 MaterialSource 로 만들고, 잠그지 못한(사라진) 파일 수를 센다."""
    sources: list[MaterialSource] = []
    skipped = 0
    for origin, row, stored in rows:
        if stored is not None and stored.id not in held:
            skipped += 1
            continue
        sources.append(
            MaterialSource(
                origin=origin,
                kind=row.kind,
                title=row.title,
                url=row.url,
                sha256=None if stored is None else stored.sha256,
                content_type=None if stored is None else stored.content_type,
                size=None if stored is None else stored.size,
            )
        )
    return SourceSet(sources=sources, skipped_missing=skipped)


async def pool_sources(
    session: AsyncSession, *, pool_course_id: str, instructor_id: int
) -> SourceSet:
    """배정 강사에게 붙일 풀 과정 기본 강의안(① 소유자면 고유 과정 파일 ② 그 강사의 역량 파일)."""
    owner = await session.scalar(
        select(PoolCourse.owner_instructor_id).where(PoolCourse.id == pool_course_id)
    )
    rows: list[tuple[str, Any, StoredFile | None]] = []
    if owner is not None and owner == instructor_id:
        rows += await _file_rows(session, POOL_COURSE_FILE, pool_course_id)
    capability_id = await session.scalar(
        select(Capability.id)
        .where(
            Capability.instructor_id == instructor_id,
            Capability.pool_course_id == pool_course_id,
        )
        .with_for_update(read=True, key_share=True)
    )
    if capability_id is not None:
        rows += await _file_rows(session, CAPABILITY_FILE, capability_id)
    held = await share_sources(session, _stored_ids(rows))
    return _source_set(rows, held)


async def curriculum_sources(session: AsyncSession, curriculum_id: str) -> SourceSet:
    """커리큘럼 기본 자료((sort, id) 순). 소유 행(curriculum)은 부르는 쪽이 이미 FOR UPDATE 로 잡았다."""
    rows = await _file_rows(session, CURRICULUM_FILE, curriculum_id)
    held = await share_sources(session, _stored_ids(rows))
    return _source_set(rows, held)
