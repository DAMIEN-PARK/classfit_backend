"""기본 강의안 복제(T5 결정 x·xi). flush 까지만.

- 복제 = 행 복제다. 원본 파일 행마다 session_attachment 1행(kind·title 같음, description NULL, url 은 link 만,
  origin = 원본 owner_kind) → 파일 종류면 stored_file 1행(sha256·content_type·size 는 원본 그대로,
  owner_kind session_attachment · owner_id 새 첨부 id, key 는 insert_stored_file 이 새로 만든다) → set_file_id.
  바이트는 쓰지도 읽지도 않는다 — 같은 sha 경로를 두 행이 가리킨다. 그래서 파일 저장소가 없어도 복제는 된다.
- 붙는 때: 세션에 강사가 새로 배정될 때, 그 세션에 pool_course_id 가 있고 첨부가 0개일 때만(attach_defaults).
  커리큘럼 시작점은 커리큘럼 기본 자료를 모든 세션에 붙인다(service.courses.starts 가 copy_sources 를 부른다).
- 원본 행은 crud.materials 가 복사 커밋까지 잠근다. 사라진 원본은 skipped_missing 으로 센다(500 아님).
- 사본마다 audit 을 쓰지 않는다. 배정 audit detail 에 개수(materials·skipped_missing)만 둔다.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import attachment as crud_attachment
from classfit.crud import materials as crud_materials
from classfit.crud import stored_file as crud_stored_file
from classfit.crud.materials import MaterialSource, SourceSet
from classfit.models import CourseSession


async def copy_sources(
    session: AsyncSession, *, session_id: int, sources: Sequence[MaterialSource]
) -> int:
    """원본마다 그 세션의 끝에 사본 첨부 1행(파일이면 stored_file 1행). 만든 사본 수."""
    for src in sources:
        row = await crud_attachment.insert_attachment(
            session,
            session_id=session_id,
            kind=src.kind,
            title=src.title,
            description=None,
            url=src.url if src.kind == "link" else None,
            origin=src.origin,
        )
        if src.sha256 is None or src.content_type is None or src.size is None:
            continue
        stored = await crud_stored_file.insert_stored_file(
            session,
            sha256=src.sha256,
            owner_kind=crud_attachment.OWNER_KIND,
            owner_id=row.id,
            content_type=src.content_type,
            size=src.size,
        )
        await crud_attachment.set_file_id(session, row, stored.id)
    return len(sources)


async def attach_defaults(
    session: AsyncSession, *, rows: Sequence[CourseSession], instructor_id: int
) -> tuple[int, int]:
    """새로 배정된 행 중 pool_course_id 가 있고 첨부가 0개인 세션에 그 강사의 기본 강의안을 붙인다.

    (만든 사본 수, 건너뛴 원본 수). 원본은 (풀 과정, 강사)마다 한 번 잠가 읽고, 건너뛴 수도 그 단위로 센다.
    """
    targets = [r for r in rows if r.pool_course_id is not None]
    if not targets:
        return 0, 0
    counts = await crud_attachment.counts_by_session(session, [r.id for r in targets])
    found: dict[str, SourceSet] = {}
    copied = 0
    for row in targets:
        if counts.get(row.id, 0) > 0:
            continue
        pool_id = row.pool_course_id
        assert pool_id is not None
        if pool_id not in found:
            found[pool_id] = await crud_materials.pool_sources(
                session, pool_course_id=pool_id, instructor_id=instructor_id
            )
        copied += await copy_sources(
            session, session_id=row.id, sources=found[pool_id].sources
        )
    return copied, sum(s.skipped_missing for s in found.values())
