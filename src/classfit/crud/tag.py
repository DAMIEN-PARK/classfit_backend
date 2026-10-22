"""tag 읽기·쓰기와 강사의 태그 읽기. flush 까지만.

- 이름 정규화(앞뒤 공백 제거 + 연속 공백 하나)는 normalize_tag_name 한 곳이다. 아래 함수는 정규화한 이름을 받는다.
- 강사가 보낸 새 분야 이름은 INSERT … ON CONFLICT (kind, name) DO NOTHING 뒤 읽는다. 동시 가입이 같은 새 이름을
  보내도 둘째는 첫째의 커밋을 기다렸다 아무것도 하지 않고 이어지는 읽기가 그 행을 본다(23505 없음, T2b learner 꼴).
- 사용 중지 판정(새로 붙일 수 없음)은 service 몫이다. 여기 읽기는 중지 태그도 돌려준다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict
from classfit.crud.flush import flush_or_conflict
from classfit.crud.like import LIKE_ESCAPE, contains_pattern
from classfit.models import InstructorTag, Tag

DUPLICATE = "같은 이름의 태그가 이미 있습니다"


def normalize_tag_name(name: str) -> str:
    """앞뒤 공백을 지우고 안쪽 연속 공백(탭·줄바꿈 포함)을 빈칸 하나로."""
    return " ".join(name.split())


async def find_tags(
    session: AsyncSession, kind: str, names: Iterable[str]
) -> dict[str, Tag]:
    """이름 → 행(중지 포함). 없는 이름은 키가 없다."""
    wanted = list(dict.fromkeys(names))
    if not wanted:
        return {}
    stmt = select(Tag).where(Tag.kind == kind, Tag.name.in_(wanted))
    return {row.name: row for row in (await session.scalars(stmt)).all()}


async def create_missing_field_tags(
    session: AsyncSession, names: Sequence[str], *, source: str, group: str
) -> dict[str, Tag]:
    """분야 태그를 이름마다 하나로 맞춘다(없으면 group 대분류로 만든다). 이름 → 행(이미 있던 것 포함)."""
    wanted = list(dict.fromkeys(names))
    if not wanted:
        return {}
    stmt = (
        insert(Tag)
        .values(
            [
                {"kind": "field", "name": n, "group_name": group, "source": source}
                for n in wanted
            ]
        )
        .on_conflict_do_nothing(index_elements=["kind", "name"])
    )
    await session.execute(stmt)
    return await find_tags(session, "field", wanted)


async def list_tags(
    session: AsyncSession,
    *,
    kind: str,
    q: str | None,
    active_only: bool,
    limit: int,
) -> tuple[list[Tag], bool]:
    """(items, has_more). limit+1 행을 읽어 잘렸는지 안다. 순서는 (sort, name, id). q 는 이름 부분 일치(대소문자 무시)."""
    if limit < 1:
        raise ValueError("limit 은 1 이상")
    stmt = select(Tag).where(Tag.kind == kind)
    if active_only:
        stmt = stmt.where(Tag.active.is_(True))
    if q:
        stmt = stmt.where(Tag.name.ilike(contains_pattern(q), escape=LIKE_ESCAPE))
    stmt = stmt.order_by(Tag.sort, Tag.name, Tag.id).limit(limit + 1)
    rows = list((await session.scalars(stmt)).all())
    return rows[:limit], len(rows) > limit


async def get_tag(session: AsyncSession, tag_id: int) -> Tag | None:
    return await session.get(Tag, tag_id)


async def insert_tag(
    session: AsyncSession,
    *,
    kind: str,
    name: str,
    group_name: str | None,
    source: str,
) -> Tag:
    """관리자가 더하는 태그. 같은 (kind, name) 이면 Conflict(409)."""
    row = Tag(kind=kind, name=name, group_name=group_name, source=source)
    await flush_or_conflict(session, DUPLICATE, row)
    await session.refresh(row)
    return row


async def update_tag(session: AsyncSession, row: Tag, **fields: Any) -> list[str]:
    """준 칸 중 다른 칸만 쓴다. 바뀐 칸 이름(정렬). 이름을 같은 kind 의 다른 태그 이름으로 바꾸면 Conflict(409).

    겹침은 쓰기 전에 읽어서 막는다(flush_or_conflict 는 이미 바꾼 칸을 SAVEPOINT 밖에서 flush 하므로 못 쓴다).
    그 사이에 끼어든 동시 변경은 유일 제약(uq_tag_kind_name)이 막는다.
    """
    changed = {k: v for k, v in fields.items() if getattr(row, k) != v}
    if "name" in changed:
        clash = await session.scalar(
            select(Tag.id).where(
                Tag.kind == row.kind, Tag.name == changed["name"], Tag.id != row.id
            )
        )
        if clash is not None:
            raise Conflict(DUPLICATE)
    for name, value in changed.items():
        setattr(row, name, value)
    if changed:
        await session.flush()
    return sorted(changed)


async def usage_counts(session: AsyncSession, tag_ids: Iterable[int]) -> dict[int, int]:
    """태그마다 붙은 강사 수(관리자 목록의 used_by). 0 이면 키가 없다(부르는 쪽이 0 으로)."""
    ids = list(tag_ids)
    if not ids:
        return {}
    stmt = (
        select(InstructorTag.tag_id, func.count())
        .where(InstructorTag.tag_id.in_(ids))
        .group_by(InstructorTag.tag_id)
    )
    return {tid: n for tid, n in (await session.execute(stmt)).all()}


async def tags_by_instructor(
    session: AsyncSession, instructor_ids: Iterable[int]
) -> dict[int, list[Tag]]:
    """강사마다 붙은 태그(중지 포함, (sort, name, id) 순). 태그가 없는 강사는 키가 없다."""
    ids = list(instructor_ids)
    if not ids:
        return {}
    stmt = (
        select(InstructorTag.instructor_id, Tag)
        .join(Tag, Tag.id == InstructorTag.tag_id)
        .where(InstructorTag.instructor_id.in_(ids))
        .order_by(InstructorTag.instructor_id, Tag.sort, Tag.name, Tag.id)
    )
    found: dict[int, list[Tag]] = {}
    for iid, tag in (await session.execute(stmt)).all():
        found.setdefault(iid, []).append(tag)
    return found
