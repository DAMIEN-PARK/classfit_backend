"""강의 배정(0007, Design 부록 A T5): 새 칸·FK·CHECK origin · 강사 강의 범위 · 기본 강의안 원본 순서. 라이브 PG.

alembic check 는 CHECK 를 비교하지 않으므로 여기서 잰다(23514). 행은 crud·service 로 직접 만든다(HTTP 픽스처 없음).
시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(nextval 은 롤백돼도 돌아오지 않는다 — T4 대조 실험 13).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import course as crud_course
from classfit.crud import schedule as crud_schedule
from classfit.crud.attachment import insert_attachment
from classfit.crud.materials import curriculum_sources, pool_sources
from classfit.crud.pool_file import FILE_OWNER_KINDS, insert_file_row
from classfit.crud.scope import OWNER_KINDS, course_scope
from classfit.models import Course
from classfit.models.attachment import ATTACHMENT_ORIGINS
from tests.fixtures.assign import (
    PDF,
    capability_files,
    course_with_section,
    curriculum_with_slots,
    own_course_files,
    pool_session,
)
from tests.fixtures.instructors import make_instructor
from tests.fixtures.pool import make_pool_course

FK_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
PDF_SHA = hashlib.sha256(PDF).hexdigest()
NEW_COLUMNS = {
    ("session", "pool_course_id"),
    ("session", "curriculum_id"),
    ("session", "instructor_id"),
    ("course", "curriculum_src_id"),
    ("session_attachment", "origin"),
}


@dataclass(frozen=True)
class _Subject:
    type: str
    id: int
    course_id: int | None = None


async def _instructor(
    session: AsyncSession, email: str, status: str = "approved"
) -> int:
    return await make_instructor(
        session, Settings(_env_file=None), email=email, status=status
    )


async def _sqlstate(session: AsyncSession, stmt: str, **params: object) -> str:
    """stmt 를 SAVEPOINT 안에서 돌리고 위반 sqlstate 를 돌려준다. 바깥 시험 트랜잭션은 산다."""
    with pytest.raises(IntegrityError) as caught:
        async with session.begin_nested():
            await session.execute(text(stmt), params)
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


async def test_assign_migration_columns_and_fk(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT table_name, column_name, is_nullable, column_default"
                " FROM information_schema.columns"
                " WHERE table_schema = 'public'"
                " AND (table_name, column_name) IN ("
                "('session', 'pool_course_id'), ('session', 'curriculum_id'),"
                " ('session', 'instructor_id'), ('course', 'curriculum_src_id'),"
                " ('session_attachment', 'origin'))"
            )
        )
    ).all()
    assert {(t, c) for t, c, _, _ in rows} == NEW_COLUMNS
    assert all(
        nullable == "YES" and default is None for _, _, nullable, default in rows
    ), rows

    course, section = await course_with_section(db_session)
    row = await crud_schedule.insert_session(
        db_session, section.id, title="세션", keywords=[], is_open=False
    )
    for column, value in (
        ("instructor_id", 999_999_999),
        ("pool_course_id", "ax-none"),
        ("curriculum_id", "cur-none"),
    ):
        assert (
            await _sqlstate(
                db_session,
                f"UPDATE session SET {column} = :v WHERE id = :id",
                v=value,
                id=row.id,
            )
            == FK_VIOLATION
        ), column
    assert (
        await _sqlstate(
            db_session,
            "UPDATE course SET curriculum_src_id = 'cur-none' WHERE id = :id",
            id=course.id,
        )
        == FK_VIOLATION
    )

    attachment = await insert_attachment(
        db_session,
        session_id=row.id,
        kind="link",
        title="링크",
        description=None,
        url="https://example.com/a",
    )
    assert attachment.origin is None  # 보통 첨부
    for origin in ATTACHMENT_ORIGINS:  # 값 집합 안은 된다
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE session_attachment SET origin = :o WHERE id = :id"),
                {"o": origin, "id": attachment.id},
            )
    assert (
        await _sqlstate(
            db_session,
            "UPDATE session_attachment SET origin = 'session_attachment' WHERE id = :id",
            id=attachment.id,
        )
        == CHECK_VIOLATION
    )
    assert set(ATTACHMENT_ORIGINS) == set(FILE_OWNER_KINDS)

    indexes = set(
        (
            await db_session.scalars(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'session'")
            )
        ).all()
    )
    assert "ix_session_instructor_id" in indexes


async def test_assign_course_scope_instructor_branch(db_session: AsyncSession) -> None:
    x = await _instructor(db_session, "scope-x@example.com")
    y = await _instructor(db_session, "scope-y@example.com")
    z = await _instructor(db_session, "scope-z@example.com")
    mine, mine_section = await course_with_section(db_session, title="X 강의")
    other, other_section = await course_with_section(db_session, title="Y 강의")
    empty, _ = await course_with_section(db_session, title="배정 없음")
    ids = {mine.id, other.id, empty.id}

    x_session = await crud_schedule.insert_session(
        db_session, mine_section.id, title="X 세션", keywords=[], is_open=True
    )
    await crud_schedule.insert_session(
        db_session, mine_section.id, title="미배정", keywords=[], is_open=True
    )
    y_session = await crud_schedule.insert_session(
        db_session, other_section.id, title="Y 세션", keywords=[], is_open=True
    )
    await crud_schedule.set_instructor(db_session, [x_session], x)
    await crud_schedule.set_instructor(db_session, [y_session], y)

    async def visible(subject: _Subject) -> set[int]:
        stmt = select(Course.id).where(course_scope(subject)).where(Course.id.in_(ids))
        return set((await db_session.scalars(stmt)).all())

    assert await visible(_Subject("admin", 1)) == ids
    assert await visible(_Subject("learner", 1, other.id)) == {other.id}
    assert await visible(_Subject("instructor", x)) == {mine.id}
    assert await visible(_Subject("instructor", y)) == {other.id}
    assert await visible(_Subject("instructor", z)) == set()
    assert await visible(_Subject("learner", 1, None)) == set()
    assert await visible(_Subject("system", x)) == set()
    assert await crud_course.in_scope(db_session, _Subject("instructor", x), mine.id)
    assert not await crud_course.in_scope(
        db_session, _Subject("instructor", x), other.id
    )

    # 강의 범위 안이어도 강사의 첨부 판정은 거짓이다(T6 몫, 결정 xii)
    attachment = await insert_attachment(
        db_session,
        session_id=x_session.id,
        kind="link",
        title="링크",
        description=None,
        url="https://example.com/a",
    )
    check = OWNER_KINDS["session_attachment"]
    assert not await check(db_session, _Subject("instructor", x), attachment.id)
    assert await check(db_session, _Subject("admin", 1), attachment.id)

    # 배정을 바꾸면 범위가 따라간다
    await crud_schedule.set_instructor(db_session, [x_session], None)
    assert await visible(_Subject("instructor", x)) == set()


async def test_default_material_sources_order(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await _instructor(db_session, "src-owner@example.com")
    other = await _instructor(db_session, "src-other@example.com")
    course = await make_pool_course(db_session, source="own", owner_instructor_id=owner)
    await own_course_files(
        db_session, tmp_path, pool_id=course.id, kinds=("pdf", "link")
    )
    # file_id 없는 pdf 행(넣다 만 행)은 원본이 아니다
    await insert_file_row(
        db_session, "pool_course_file", course.id, kind="pdf", title="빈 행"
    )
    await capability_files(
        db_session, tmp_path, instructor_id=owner, pool_id=course.id, kinds=("pdf",)
    )
    await capability_files(
        db_session,
        tmp_path,
        instructor_id=other,
        pool_id=course.id,
        kinds=("link", "pdf"),
    )

    def shape(sources: list) -> list[tuple[str, str, str, str | None, str | None]]:
        return [(s.origin, s.kind, s.title, s.url, s.sha256) for s in sources]

    url = "https://example.com/guide"
    got = await pool_sources(db_session, pool_course_id=course.id, instructor_id=owner)
    assert got.skipped_missing == 0
    assert shape(got.sources) == [
        ("pool_course_file", "pdf", "강의안 1", None, PDF_SHA),
        ("pool_course_file", "link", "참고 자료 2", url, None),
        ("capability_file", "pdf", "강의안 1", None, PDF_SHA),
    ]
    pdf = got.sources[0]
    assert (pdf.content_type, pdf.size) == ("application/pdf", len(PDF))
    assert (got.sources[1].content_type, got.sources[1].size) == (None, None)

    # 소유자가 아니면 남의 고유 과정 파일을 주지 않는다(T4 결정 ix)
    got = await pool_sources(db_session, pool_course_id=course.id, instructor_id=other)
    assert got.skipped_missing == 0
    assert shape(got.sources) == [
        ("capability_file", "link", "참고 자료 1", url, None),
        ("capability_file", "pdf", "강의안 2", None, PDF_SHA),
    ]

    # 역량도 소유도 없으면 비어 있다
    third = await _instructor(db_session, "src-third@example.com")
    got = await pool_sources(db_session, pool_course_id=course.id, instructor_id=third)
    assert (got.sources, got.skipped_missing) == ([], 0)

    curriculum_id = await curriculum_with_slots(
        db_session,
        tmp_path,
        instructor_id=owner,
        slots=[{"day": 1, "slot": 1, "title": "차시"}],
        kinds=("link", "pdf", "link"),
    )
    got = await curriculum_sources(db_session, curriculum_id)
    assert got.skipped_missing == 0
    assert shape(got.sources) == [
        ("curriculum_file", "link", "참고 자료 1", url, None),
        ("curriculum_file", "pdf", "강의안 2", None, PDF_SHA),
        ("curriculum_file", "link", "참고 자료 3", url, None),
    ]

    # 풀 세션 픽스처는 과정을 가리키는 미배정 세션을 만든다
    _, section = await course_with_section(db_session)
    row = await pool_session(db_session, section_id=section.id, pool_id=course.id)
    assert (row.pool_course_id, row.instructor_id, row.title) == (
        course.id,
        None,
        course.title,
    )
