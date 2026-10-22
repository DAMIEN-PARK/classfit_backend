"""instructor·instructor_tag 읽기·쓰기. flush 까지만.

- 행 넣기 insert_instructor 는 service.instructors.signup 의 signup() 만 부른다(단일 진입, Design 5절 13).
  Instructor( 생성은 이 파일 한 곳이다(tests/integration/test_db_instructor.py 가 센다).
- 이메일은 정규화(schemas.enter.normalize_email)해 넘긴다. 비교는 식 유일 색인과 같은 SQL lower() 로 한다.
- 목록·단건 조회의 첫 WHERE 는 주체 범위다(crud.scope.instructor_scope).
- 상태 전이·재신청·로그인 상태 판정은 lock_instructor 로 행을 잠근 뒤 한다(T3 결정 vi·viii, Design 5절 6).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.crud.like import LIKE_ESCAPE, contains_pattern
from classfit.crud.scope import Subject, instructor_scope
from classfit.models import DocumentType, Instructor, InstructorDocument, InstructorTag


def _by_email(email: str) -> Select[tuple[Instructor]]:
    return select(Instructor).where(func.lower(Instructor.email) == func.lower(email))


async def insert_instructor(session: AsyncSession, **fields: Any) -> Instructor:
    """가입 1행. 약관 동의 시각은 DB now() 다. 같은 이메일(소문자 비교)이면 Conflict(409).

    넣은 뒤 다시 읽어 서버 기본값(created_at · career · status …)을 채운다(async 라 게으른 읽기가 없다).
    """
    row = Instructor(terms_agreed_at=func.now(), **fields)
    await flush_or_conflict(session, "이미 가입된 이메일입니다", row)
    await session.refresh(row)
    return row


async def get_instructor(
    session: AsyncSession, subject: Subject, instructor_id: int
) -> Instructor | None:
    """범위 안의 강사 하나. 관리자는 누구든, 강사는 자기 자신만, 그 밖은 None."""
    stmt = (
        select(Instructor)
        .where(instructor_scope(subject))
        .where(Instructor.id == instructor_id)
    )
    return await session.scalar(stmt)


async def find_by_email(session: AsyncSession, email: str) -> Instructor | None:
    return await session.scalar(_by_email(email))


async def lock_instructor(
    session: AsyncSession, instructor_id: int
) -> Instructor | None:
    """강사 행을 SELECT … FOR UPDATE 로 잠그고 새로 읽는다. 없으면 None(T2b lock_course 꼴).

    동시 approve·reject 가 둘 다 전이표를 통과하지 않게, 로그인과 정지가 엇갈려 정지 뒤 산 세션이 남지 않게 줄 세운다.
    populate_existing: 잠금을 기다린 사이 커밋된 상태를 identity map 의 옛 값이 가리지 않게 덮어 읽는다.
    """
    stmt = (
        select(Instructor)
        .where(Instructor.id == instructor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def update_instructor(
    session: AsyncSession, row: Instructor, **fields: Any
) -> list[str]:
    """준 칸 중 현재 값과 다른 칸만 쓰고 flush. 실제로 바뀐 칸 이름(정렬)을 돌려준다(T2a update_invite_code 꼴).

    updated_at 은 onupdate 로 바뀌고 만료되니 응답에 쓰려면 다시 읽는다.
    """
    changed = {k: v for k, v in fields.items() if getattr(row, k) != v}
    for name, value in changed.items():
        setattr(row, name, value)
    if changed:
        await session.flush()
    return sorted(changed)


async def set_status(
    session: AsyncSession, row: Instructor, status: str, *, reject_reason: str | None
) -> Instructor:
    """상태와 반려 사유를 함께 쓴다. 반려 ⇔ 사유는 CHECK reject_reason 이 막는다."""
    row.status = status
    row.reject_reason = reject_reason
    await session.flush()
    return row


def list_stmt(
    subject: Subject, status: str | None, q: str | None
) -> Select[tuple[Instructor]]:
    """강사 목록(crud.page.keyset_page 에 넘긴다). 첫 WHERE 는 주체 범위다.

    q 는 이름·소속·이메일 부분 일치(대소문자 무시, % _ 는 글자 그대로)다.
    """
    stmt = select(Instructor).where(instructor_scope(subject))
    if status is not None:
        stmt = stmt.where(Instructor.status == status)
    if q:
        pattern = contains_pattern(q)
        stmt = stmt.where(
            or_(
                Instructor.name.ilike(pattern, escape=LIKE_ESCAPE),
                Instructor.org.ilike(pattern, escape=LIKE_ESCAPE),
                Instructor.email.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    return stmt


async def replace_tags(
    session: AsyncSession, instructor_id: int, tag_ids: Sequence[int]
) -> bool:
    """강사의 태그를 tag_ids 로 맞춘다(차집합만 넣고 지운다). 바뀌었으면 True."""
    wanted = set(tag_ids)
    current = set(
        (
            await session.scalars(
                select(InstructorTag.tag_id).where(
                    InstructorTag.instructor_id == instructor_id
                )
            )
        ).all()
    )
    gone, added = current - wanted, wanted - current
    if gone:
        await session.execute(
            delete(InstructorTag).where(
                InstructorTag.instructor_id == instructor_id,
                InstructorTag.tag_id.in_(gone),
            )
        )
    if added:
        await session.execute(
            insert(InstructorTag)
            .values([{"instructor_id": instructor_id, "tag_id": t} for t in added])
            .on_conflict_do_nothing()
        )
    return bool(gone or added)


async def document_counts(
    session: AsyncSession, instructor_ids: Iterable[int]
) -> dict[int, int]:
    """강사마다 낸 필수 서류 수(목록의 n/3). 하나도 없으면 키가 없다(부르는 쪽이 0 으로)."""
    ids = list(instructor_ids)
    if not ids:
        return {}
    stmt = (
        select(InstructorDocument.instructor_id, func.count())
        .join(DocumentType, DocumentType.id == InstructorDocument.type_id)
        .where(InstructorDocument.instructor_id.in_(ids), DocumentType.required)
        .group_by(InstructorDocument.instructor_id)
    )
    return {iid: n for iid, n in (await session.execute(stmt)).all()}
