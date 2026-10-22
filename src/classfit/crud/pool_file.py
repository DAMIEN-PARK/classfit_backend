"""풀 파일 표 셋(pool_course_file · capability_file · curriculum_file) 읽기·쓰기. flush 까지만.

- 셋은 칸이 같다(models.pool._PoolFileCols). owner_kind 글자(= 표 이름 = stored_file.owner_kind)로 표를 고른다.
  소유 행을 가리키는 칸 이름은 표마다 다르다(model.owner_fk: pool_course_id · capability_id · curriculum_id).
- 넣기는 파일 행 → stored_file(owner_id = 파일 행 id) → set_file_id 순서다(service.files.pool_files).
- 지우기는 파일 행 → 그 파일 행이 소유한 stored_file 행 순서다. file_id FK 가 NO ACTION 이라 거꾸로면 23503 이다
  (crud.attachment._delete_where 꼴). 바이트는 지우지 않는다(scripts.file_gc 몫).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from classfit.models import CapabilityFile, CurriculumFile, PoolCourseFile, StoredFile

PoolFile = PoolCourseFile | CapabilityFile | CurriculumFile
FILE_MODELS: dict[str, type[PoolFile]] = {
    m.__tablename__: m for m in (PoolCourseFile, CapabilityFile, CurriculumFile)
}
FILE_OWNER_KINDS = tuple(FILE_MODELS)
# (파일 행, 파일 key, 파일 크기). link 행은 key·size 가 None
FileRow = tuple[PoolFile, str | None, int | None]


def file_model(owner_kind: str) -> type[PoolFile]:
    """owner_kind 의 파일 표. 모르는 글자면 ValueError(부르는 쪽 버그)."""
    try:
        return FILE_MODELS[owner_kind]
    except KeyError:
        raise ValueError(f"풀 파일 종류가 아니다: {owner_kind}") from None


def _owner_col(model: type[PoolFile]) -> InstrumentedAttribute[Any]:
    col: InstrumentedAttribute[Any] = getattr(model, model.owner_fk)
    return col


def owner_of(row: PoolFile) -> Any:
    """파일 행이 가리키는 소유 행 id(고유 과정·커리큘럼은 글자, 역량은 정수)."""
    return getattr(row, row.owner_fk)


async def insert_file_row(
    session: AsyncSession,
    owner_kind: str,
    owner_id: Any,
    *,
    kind: str,
    title: str,
    url: str | None = None,
) -> PoolFile:
    """그 소유자의 끝에 붙인다(sort = 지금 최댓값 + 1, 처음이면 0). pdf 는 url 없이 넣고 set_file_id 로 잇는다."""
    model = file_model(owner_kind)
    top = await session.scalar(
        select(func.max(model.sort)).where(_owner_col(model) == owner_id)
    )
    row = model(
        **{model.owner_fk: owner_id},
        kind=kind,
        title=title,
        url=url,
        sort=0 if top is None else top + 1,
    )
    session.add(row)
    await session.flush()
    return row


async def set_file_id(session: AsyncSession, row: PoolFile, file_id: int) -> PoolFile:
    row.file_id = file_id
    await session.flush()
    return row


async def get_file_row(
    session: AsyncSession, owner_kind: str, file_row_id: int
) -> PoolFile | None:
    return await session.get(file_model(owner_kind), file_row_id)


async def count_file_rows(session: AsyncSession, owner_kind: str, owner_id: Any) -> int:
    """그 소유자의 파일 행 수(pdf·link 합산, POOL_FILES_MAX 판정용)."""
    model = file_model(owner_kind)
    stmt = select(func.count()).select_from(model).where(_owner_col(model) == owner_id)
    return await session.scalar(stmt) or 0


async def list_file_rows(
    session: AsyncSession, owner_kind: str, owner_ids: Iterable[Any]
) -> list[FileRow]:
    """소유자들의 파일 행과 파일 key·size. 순서는 (소유자, sort, id)."""
    ids = list(owner_ids)
    if not ids:
        return []
    model = file_model(owner_kind)
    owner = _owner_col(model)
    stmt = (
        select(model, StoredFile.key, StoredFile.size)
        .outerjoin(StoredFile, StoredFile.id == model.file_id)
        .where(owner.in_(ids))
        .order_by(owner, model.sort, model.id)
    )
    return [(f, key, size) for f, key, size in (await session.execute(stmt)).all()]


async def _delete_where(
    session: AsyncSession, owner_kind: str, which: ColumnElement[bool]
) -> int:
    """which 에 걸린 파일 행을 지우고, 그 행들이 소유한 stored_file 행도 지운다. 지운 파일 행 수."""
    model = file_model(owner_kind)
    gone = (
        (await session.execute(delete(model).where(which).returning(model.id)))
        .scalars()
        .all()
    )
    if gone:
        await session.execute(
            delete(StoredFile).where(
                StoredFile.owner_kind == owner_kind, StoredFile.owner_id.in_(gone)
            )
        )
    return len(gone)


async def delete_file_row(
    session: AsyncSession, owner_kind: str, file_row_id: int
) -> bool:
    """파일 행 하나와 그 stored_file 행. 지웠으면 True."""
    model = file_model(owner_kind)
    return await _delete_where(session, owner_kind, model.id == file_row_id) > 0


async def delete_files_of(session: AsyncSession, owner_kind: str, owner_id: Any) -> int:
    """한 소유자의 파일 행 전부와 그 stored_file 행(소유 행을 지우기 전에). 지운 파일 행 수."""
    model = file_model(owner_kind)
    return await _delete_where(session, owner_kind, _owner_col(model) == owner_id)
