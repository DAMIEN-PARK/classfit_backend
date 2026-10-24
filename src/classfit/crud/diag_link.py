"""diag_link(자가진단 링크) 읽기·쓰기(T9a 결정 iii·vi). flush 까지만.

- 쓰기는 전부 회사 행 잠금(crud.company.lock_company) 아래에서 부른다. 링크 행은 따로 잠그지 않는다.
- 회사당 open 링크는 부분 유일 색인 uq_diag_link_company_open 이 하나로 지킨다(마지막 보루). insert_link 는 flush_or_conflict
  로 그 위반(과 토큰 충돌)을 409 로 바꾼다.
- 만료는 저장하지 않는다 — open 인지와 만료일로 service.rules.diagnosis.link_state 가 계산한다.
- 토큰 전체는 여기서 로그·오류 글자에 싣지 않는다(결정 x·xxv).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.models import Company, DiagLink

OPEN_TAKEN = "발급 중인 링크를 먼저 회수하세요"


async def insert_link(
    session: AsyncSession,
    *,
    company_id: int,
    token: str,
    phase: str,
    recipient: str | None,
    issued_on: dt.date,
    expires_on: dt.date,
) -> DiagLink:
    """open 링크 한 행. 그 회사에 open 링크가 있으면(부분 유일 색인) 또는 토큰이 겹치면 Conflict."""
    row = DiagLink(
        company_id=company_id,
        token=token,
        phase=phase,
        recipient=recipient,
        issued_on=issued_on,
        expires_on=expires_on,
        status="open",
    )
    await flush_or_conflict(session, OPEN_TAKEN, row)
    await session.refresh(row)
    return row


async def get_by_token(
    session: AsyncSession, token: str, *, fresh: bool = False
) -> tuple[DiagLink, Company] | None:
    """(링크, 그 회사). 없으면 None. fresh 는 회사를 잠근 뒤 다시 읽을 때(populate_existing)."""
    stmt = (
        select(DiagLink, Company)
        .join(Company, Company.id == DiagLink.company_id)
        .where(DiagLink.token == token)
    )
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    found = (await session.execute(stmt)).first()
    return (found[0], found[1]) if found is not None else None


async def open_links(session: AsyncSession, company_id: int) -> list[DiagLink]:
    """그 회사의 open 링크(만료 지난 것 포함). 회사를 잠근 뒤 부르므로 늘 새로 읽는다(populate_existing)."""
    stmt = (
        select(DiagLink)
        .where(DiagLink.company_id == company_id, DiagLink.status == "open")
        .order_by(DiagLink.id)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def list_links(session: AsyncSession, company_id: int) -> list[DiagLink]:
    """그 회사의 링크 전부, 발급 역순(id 내림차순)."""
    stmt = (
        select(DiagLink)
        .where(DiagLink.company_id == company_id)
        .order_by(DiagLink.id.desc())
    )
    return list((await session.scalars(stmt)).all())


async def update_link(session: AsyncSession, row: DiagLink, **fields: Any) -> DiagLink:
    """칸을 바꾸고 flush 한 뒤 다시 읽는다(updated_at·submitted_at·revoked_at = now() 가 만료된다)."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    await session.refresh(row)
    return row
