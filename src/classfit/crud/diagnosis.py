"""diagnosis(진단 회차) 읽기·쓰기(T9a 결정 iii·iv·v). flush 까지만.

- 쓰기는 전부 회사 행 잠금(crud.company.lock_company) 아래에서 부른다. 회차 행은 따로 잠그지 않는다 — 그 행을 바꾸는
  모든 경로가 같은 회사 잠금 아래다(결정 xi). 잠근 뒤에는 get_diagnosis(…, fresh=True) 로 다시 읽는다.
- 번호 next_round_no 는 그 회사 최대 + 1 이다(중간은 당기지 않고, 마지막을 지우면 그 번호를 다시 받는다).
- 회차 삭제 delete_diagnosis 는 그 회차를 가리키는 링크를 먼저 revoked 로 바꾸고 diagnosis_id 를 푼 뒤 지운다
  (응답을 받지 않은 것으로 — 기획안 :832). submitted_at 은 이력으로 남는다.
- 비교 대상 previous_complete 는 앞 회차 가운데 review ∨ final 이고 17지표를 전부 답한 가장 최근 회차다(기획안 :834).
  읽을 때마다 고른다(스냅샷 없음 — 결정 v).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import DiagLink, Diagnosis
from classfit.models.diagnosis import ANSWER_KEYS

COMPLETED_STATUSES = (
    "review",
    "final",
)  # 비교 대상이 될 수 있는 상태(작성 중 draft 는 뺀다)


async def insert_diagnosis(
    session: AsyncSession,
    *,
    company_id: int,
    round_no: int,
    phase: str,
    mode: str,
    status: str,
    diagnosed_on: dt.date,
    created_by: str,
    respondent: dict[str, Any] | None,
    answers: dict[str, Any],
    evidence: dict[str, Any],
    field: dict[str, Any],
    matrix: dict[str, Any],
) -> Diagnosis:
    row = Diagnosis(
        company_id=company_id,
        round_no=round_no,
        phase=phase,
        mode=mode,
        status=status,
        diagnosed_on=diagnosed_on,
        created_by=created_by,
        respondent=respondent,
        answers=answers,
        evidence=evidence,
        field=field,
        matrix=matrix,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_diagnosis(
    session: AsyncSession, diagnosis_id: int, *, fresh: bool = False
) -> Diagnosis | None:
    """범위 없는 getter(404 판정용). fresh 는 회사를 잠근 뒤 다시 읽을 때(populate_existing)."""
    stmt = select(Diagnosis).where(Diagnosis.id == diagnosis_id)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def next_round_no(session: AsyncSession, company_id: int) -> int:
    """그 회사의 다음 회차 번호(최대 + 1, 없으면 1). 회사를 잠근 뒤에만 부른다."""
    stmt = select(func.coalesce(func.max(Diagnosis.round_no), 0)).where(
        Diagnosis.company_id == company_id
    )
    return int(await session.scalar(stmt) or 0) + 1


async def list_rounds(session: AsyncSession, company_id: int) -> list[Diagnosis]:
    stmt = (
        select(Diagnosis)
        .where(Diagnosis.company_id == company_id)
        .order_by(Diagnosis.round_no)
    )
    return list((await session.scalars(stmt)).all())


async def previous_complete(
    session: AsyncSession, company_id: int, round_no: int
) -> Diagnosis | None:
    """앞 회차 가운데 review ∨ final ∧ 17지표 전부 답한 가장 최근 회차. 없으면 None."""
    answered = (
        select(func.count())
        .select_from(func.jsonb_object_keys(Diagnosis.answers).alias("answer_key"))
        .scalar_subquery()
    )
    stmt = (
        select(Diagnosis)
        .where(
            Diagnosis.company_id == company_id,
            Diagnosis.round_no < round_no,
            Diagnosis.status.in_(COMPLETED_STATUSES),
            answered == len(ANSWER_KEYS),
        )
        .order_by(Diagnosis.round_no.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def update_diagnosis(
    session: AsyncSession, row: Diagnosis, **fields: Any
) -> Diagnosis:
    """칸을 바꾸고 flush 한 뒤 다시 읽는다(updated_at 이 만료된다)."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    await session.refresh(row)
    return row


async def finalize_row(
    session: AsyncSession, row: Diagnosis, *, admin_id: int, reco: dict[str, Any]
) -> Diagnosis:
    """확정: status final · finalized_at 지금 · 확정자 · 권장 구성 스냅샷."""
    row.status = "final"
    row.finalized_at = func.now()
    row.finalized_by_id = admin_id
    row.reco = reco
    await session.flush()
    await session.refresh(row)
    return row


async def delete_diagnosis(
    session: AsyncSession, diagnosis_id: int
) -> tuple[bool, DiagLink | None]:
    """(지웠는가, 회수한 링크). 그 회차를 가리키는 링크가 있으면 revoked 로 바꾸고 diagnosis_id 를 먼저 푼다."""
    link = await session.scalar(
        select(DiagLink)
        .where(DiagLink.diagnosis_id == diagnosis_id)
        .execution_options(populate_existing=True)
    )
    if link is not None:
        link.diagnosis_id = None
        link.status = "revoked"
        link.revoked_at = func.now()
        await session.flush()
        await session.refresh(link)
    deleted = await session.execute(
        delete(Diagnosis).where(Diagnosis.id == diagnosis_id).returning(Diagnosis.id)
    )
    return deleted.scalar_one_or_none() is not None, link
