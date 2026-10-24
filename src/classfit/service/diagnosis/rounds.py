"""진단 회차 만들기·고치기·권장 구성 저장·확정·지우기(T9a 결정 iv·viii·x·xi). flush 까지만.

- 다섯 다 회사 행 FOR UPDATE(lock_company) → 회차 다시 읽기(get_diagnosis fresh) → 상태 판정 → 쓰기 순서다(결정 xi).
- 고치기(D2·D3): draft·review 만. 준 칸 가운데 지금 값과 다른 칸만 쓰고(JSON 칸은 통째 비교), 없으면 audit 도 없다.
  바뀐 칸에 링크 회차의 잠긴 칸(제출일 diagnosed_on)이 들면 FrozenField — 같은 값이면 바뀐 칸이 아니다(D2).
- 확정(D5~D7): 17지표 전부 답해야 하고(아니면 409 · extra missing), 이미 final 이면 409. 권장 구성은 저장한 것 ∨ 그 순간
  초안을 스냅샷한다(개설 ③ 의 입력을 고정).
- 지우기(D9): draft·review 만. 링크 회차면 그 링크를 revoked 로(응답을 받지 않은 것으로 — 기획안 :832). 번호는 당기지
  않는다. final 은 고치기·권장 구성·확정·지우기 모두 409(DIA-007 — 새 회차로).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import company as crud_company
from classfit.crud import diagnosis as crud_diagnosis
from classfit.models import Diagnosis
from classfit.service.diagnosis import reports
from classfit.service.diagnosis.links import token_prefix
from classfit.service.rules.diagnosis import (
    can_edit,
    frozen_fields,
    missing_keys,
    score,
    shown_level,
)
from classfit.service.rules.reco import build_reco

TARGET = "diagnosis"
NO_COMPANY = "회사가 없습니다"
NO_ROUND = "진단 회차가 없습니다"
FINAL_LOCKED = "확정한 회차는 고칠 수 없습니다 — 새 회차로 진단하세요"


class FrozenField(ValueError):
    """링크 회차의 잠긴 칸을 다른 값으로 바꾸려 했다 — 끝점이 422 frozen_field 로 바꾼다(결정 iv D2)."""

    def __init__(self, field: str) -> None:
        super().__init__(f"{field} 은 바꿀 수 없습니다")
        self.field = field


async def create_round(
    session: AsyncSession,
    *,
    company_id: int,
    phase: str,
    diagnosed_on: dt.date,
    actor: str,
) -> Diagnosis:
    """방문 회차(draft · visit). 번호는 회사 잠금 뒤 최대 + 1."""
    if await crud_company.get_company(session, company_id) is None:
        raise NotFound(NO_COMPANY)
    if await crud_company.lock_company(session, company_id) is None:
        raise NotFound(NO_COMPANY)
    round_no = await crud_diagnosis.next_round_no(session, company_id)
    row = await crud_diagnosis.insert_diagnosis(
        session,
        company_id=company_id,
        round_no=round_no,
        phase=phase,
        mode="visit",
        status="draft",
        diagnosed_on=diagnosed_on,
        created_by=actor,
        respondent=None,
        answers={},
        evidence={},
        field={},
        matrix={},
    )
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="diagnosis.create",
        target_type=TARGET,
        target_id=str(row.id),
        detail={
            "company_id": company_id,
            "round_no": round_no,
            "phase": phase,
            "mode": "visit",
        },
    )
    return row


async def patch_round(
    session: AsyncSession,
    *,
    diagnosis_id: int,
    fields: Mapping[str, Any],
    actor: str,
) -> Diagnosis:
    """fields 는 DiagnosisPatchIn 의 준 칸(answers·evidence·field·matrix·phase·diagnosed_on)."""
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id)
    if row is None:
        raise NotFound(NO_ROUND)
    if await crud_company.lock_company(session, row.company_id) is None:
        raise NotFound(NO_ROUND)
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id, fresh=True)
    if row is None:
        raise NotFound(NO_ROUND)
    if not can_edit(row.status):
        raise Conflict(FINAL_LOCKED)
    changes = {k: v for k, v in fields.items() if getattr(row, k) != v}
    for name in sorted(frozen_fields(row.mode)):
        if name in changes:
            raise FrozenField(name)
    if "answers" in changes:
        missing_keys(
            changes["answers"]
        )  # 키·값 밖이면 ValueError(스키마가 422 로 먼저 막는다)
    if changes:
        row = await crud_diagnosis.update_diagnosis(session, row, **changes)
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="diagnosis.update",
            target_type=TARGET,
            target_id=str(diagnosis_id),
            detail={"fields": sorted(changes)},
        )
    return row


async def save_reco(
    session: AsyncSession,
    *,
    diagnosis_id: int,
    reco: dict[str, Any],
    actor: str,
) -> Diagnosis:
    """권장 구성 전체를 저장한다(D8). 같은 값이면 쓰지 않는다."""
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id)
    if row is None:
        raise NotFound(NO_ROUND)
    if await crud_company.lock_company(session, row.company_id) is None:
        raise NotFound(NO_ROUND)
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id, fresh=True)
    if row is None:
        raise NotFound(NO_ROUND)
    if not can_edit(row.status):
        raise Conflict(FINAL_LOCKED)
    if row.reco != reco:
        row = await crud_diagnosis.update_diagnosis(session, row, reco=reco)
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="diagnosis.reco",
            target_type=TARGET,
            target_id=str(diagnosis_id),
        )
    return row


async def finalize_round(
    session: AsyncSession, *, diagnosis_id: int, admin_id: int, actor: str
) -> Diagnosis:
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id)
    if row is None:
        raise NotFound(NO_ROUND)
    company = await crud_company.lock_company(session, row.company_id)
    if company is None:
        raise NotFound(NO_ROUND)
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id, fresh=True)
    if row is None:
        raise NotFound(NO_ROUND)
    if row.status == "final":
        raise Conflict("이미 확정한 회차입니다 — 새 회차로 진단하세요")
    missing = missing_keys(row.answers)
    if missing:
        raise Conflict(f"{len(missing)}개 지표가 미응답입니다", missing=missing)
    result = score(row.answers)
    reco = row.reco
    if reco is None:
        reco = build_reco(
            score=result,
            answers=row.answers,
            field=row.field,
            matrix=row.matrix,
            depts=company.depts,
            candidates=await reports.candidate_titles(session),
        )
    row = await crud_diagnosis.finalize_row(session, row, admin_id=admin_id, reco=reco)
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="diagnosis.finalize",
        target_type=TARGET,
        target_id=str(diagnosis_id),
        detail={
            "round_no": row.round_no,
            "answered": result.answered,
            "total": result.total,
            "level": shown_level(result),
        },
    )
    return row


async def delete_round(session: AsyncSession, *, diagnosis_id: int, actor: str) -> None:
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id)
    if row is None:
        raise NotFound(NO_ROUND)
    if await crud_company.lock_company(session, row.company_id) is None:
        raise NotFound(NO_ROUND)
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id, fresh=True)
    if row is None:
        raise NotFound(NO_ROUND)
    if not can_edit(row.status):
        raise Conflict("확정한 회차는 지울 수 없습니다")
    company_id, round_no, status = row.company_id, row.round_no, row.status
    deleted, link = await crud_diagnosis.delete_diagnosis(session, diagnosis_id)
    if not deleted:  # 잠근 회사 아래라 생기지 않는다(방어)
        raise NotFound(NO_ROUND)
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="diagnosis.delete",
        target_type=TARGET,
        target_id=str(diagnosis_id),
        detail={"company_id": company_id, "round_no": round_no, "status": status},
    )
    if link is not None:
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="diag_link.revoke",
            target_type="diag_link",
            target_id=str(link.id),
            detail={
                "token_prefix": token_prefix(link.token),
                "reason": "round_deleted",
            },
        )
