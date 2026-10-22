"""document_type · instructor_document 읽기·쓰기. flush 까지만.

- 서류 파일은 stored_file 한 행이다(owner_kind instructor_document, owner_id = 강사 id, T3 결정 ix).
- 교체는 새 stored_file 행 → file_id 바꿈 → 옛 stored_file 행 삭제 순서다(service.files.documents). file_id FK 가
  NO ACTION 이라 거꾸로면 23503 이다. 지우기는 서류 행 → 그 stored_file 행 순서다. 바이트는 지우지 않는다(gc 몫).
- 같은 (강사, 종류)의 동시 교체는 서류 행을 FOR UPDATE 로 읽어 줄 세운다(둘째가 첫째의 새 파일을 옛 파일로 보고 지운다).
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.models import DocumentType, InstructorDocument, StoredFile

# (종류, 낸 서류 또는 None, 그 파일 행 또는 None)
DocumentRow = tuple[DocumentType, InstructorDocument | None, StoredFile | None]


async def get_document_type(session: AsyncSession, type_id: str) -> DocumentType | None:
    return await session.get(DocumentType, type_id)


async def list_document_types(session: AsyncSession) -> list[DocumentType]:
    stmt = select(DocumentType).order_by(DocumentType.sort, DocumentType.id)
    return list((await session.scalars(stmt)).all())


async def get_document(
    session: AsyncSession, instructor_id: int, type_id: str, *, for_update: bool = False
) -> InstructorDocument | None:
    stmt = select(InstructorDocument).where(
        InstructorDocument.instructor_id == instructor_id,
        InstructorDocument.type_id == type_id,
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def get_document_file(
    session: AsyncSession, instructor_id: int, type_id: str
) -> tuple[InstructorDocument, StoredFile] | None:
    """그 강사의 그 종류 서류와 파일 행(관리자 열람 끝점이 바이트를 줄 때). 안 냈으면 None."""
    stmt = (
        select(InstructorDocument, StoredFile)
        .join(StoredFile, StoredFile.id == InstructorDocument.file_id)
        .where(
            InstructorDocument.instructor_id == instructor_id,
            InstructorDocument.type_id == type_id,
        )
    )
    found = (await session.execute(stmt)).first()
    return None if found is None else (found[0], found[1])


async def list_documents(
    session: AsyncSession, instructor_id: int
) -> list[DocumentRow]:
    """종류 전부와 그 강사가 낸 서류·파일(안 냈으면 None). 순서는 종류의 (sort, id)."""
    stmt = (
        select(DocumentType, InstructorDocument, StoredFile)
        .outerjoin(
            InstructorDocument,
            (InstructorDocument.type_id == DocumentType.id)
            & (InstructorDocument.instructor_id == instructor_id),
        )
        .outerjoin(StoredFile, StoredFile.id == InstructorDocument.file_id)
        .order_by(DocumentType.sort, DocumentType.id)
    )
    return [(t, d, f) for t, d, f in (await session.execute(stmt)).all()]


async def upsert_document(
    session: AsyncSession, instructor_id: int, type_id: str, file_id: int
) -> tuple[InstructorDocument, bool, int | None]:
    """(행, 새로 만들었는지, 옛 file_id). 있으면 잠그고 file_id·submitted_at 을 바꾼다.

    없던 (강사, 종류)를 동시에 처음 내면 둘째는 유일 위반이라 Conflict(409)다.
    """
    row = await get_document(session, instructor_id, type_id, for_update=True)
    if row is None:
        row = InstructorDocument(
            instructor_id=instructor_id, type_id=type_id, file_id=file_id
        )
        await flush_or_conflict(session, "같은 종류의 서류를 동시에 올렸습니다", row)
        await session.refresh(row)
        return row, True, None
    old_file_id = row.file_id
    row.file_id = file_id
    row.submitted_at = func.now()
    await session.flush()
    await session.refresh(row)
    return row, False, old_file_id


async def delete_stored_file(session: AsyncSession, file_id: int) -> bool:
    """파일 행 하나를 지운다. 지웠으면 True."""
    stmt = delete(StoredFile).where(StoredFile.id == file_id).returning(StoredFile.id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def delete_document(session: AsyncSession, row: InstructorDocument) -> None:
    """서류 행 → 그 파일 행 순서로 지운다(file_id FK 가 NO ACTION)."""
    file_id = row.file_id
    await session.execute(
        delete(InstructorDocument).where(InstructorDocument.id == row.id)
    )
    await delete_stored_file(session, file_id)
