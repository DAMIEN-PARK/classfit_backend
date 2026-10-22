"""learner 읽기·쓰기. flush 까지만.

이메일은 schemas 가 정규화(앞뒤 공백 제거 + 소문자)해 넘긴다. 비교는 식 유일 색인과 같은 SQL lower() 로 한다.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import Learner


def _by_email(email: str) -> Select[tuple[Learner]]:
    return select(Learner).where(func.lower(Learner.email) == func.lower(email))


async def find_learner(session: AsyncSession, email: str) -> Learner | None:
    return await session.scalar(_by_email(email))


async def get_or_create_learner(session: AsyncSession, email: str) -> Learner:
    """그 이메일의 learner. 없으면 만든다.

    INSERT … ON CONFLICT (lower(email)) DO NOTHING 뒤 읽는다. 다른 강의에 같은 이메일이 동시에 첫 등록해도
    둘째는 첫째의 커밋을 기다렸다 아무것도 하지 않고, 이어지는 읽기가 그 행을 본다(23505 없음).
    """
    stmt = (
        insert(Learner)
        .values(email=email)
        .on_conflict_do_nothing(index_elements=[func.lower(Learner.email)])
    )
    await session.execute(stmt)
    return (await session.scalars(_by_email(email))).one()
