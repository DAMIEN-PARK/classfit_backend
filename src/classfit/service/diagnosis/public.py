"""공개 자가진단 응답 — 토큰이 주체다(Design :59 · T9a 결정 vi). 세션·인증 없음. flush 까지만.

- 판정 순서: 모양 밖·없는 토큰 404(같은 글자 — 존재를 흘리지 않는다) → 상태 410(Gone, extra reason = expired·revoked·
  submitted — 끝점이 problem type 을 고른다). 만료일 당일은 유효하다.
- 읽기(link_view)는 문항·선택지만 준다 — 증빙 문구·답·회사 담당자·연락처·받는 분·토큰·메모가 없다(기획안 :835).
- 제출(submit)은 미리 판정 → 회사 행 FOR UPDATE → 링크 다시 읽기 → 다시 판정(같은 토큰 두 제출은 하나만) → review 회차
  (mode link · 증빙 비움 · 진단일 = 오늘 = 제출일) → 링크 submitted · 회차 연결 → audit(actor link:<앞 8자>). 돌려주는
  링크의 phase·submitted_at 만 응답에 싣는다 — 점수·레벨·회차 번호를 싣지 않는다(r3 170 · 기획안 :835).
- 토큰 전체를 로그·audit·오류 본문에 싣지 않는다(결정 x·xxv).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Gone, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import company as crud_company
from classfit.crud import diag_link as crud_link
from classfit.crud import diagnosis as crud_diagnosis
from classfit.models import DiagLink
from classfit.service.diagnosis.links import NO_LINK, TARGET, token_prefix, token_shaped
from classfit.service.rules.diagnosis import (
    COMPETENCIES,
    FIELD_OPTIONS,
    ROLES,
    is_complete,
    link_state,
    public_areas,
)

GONE_MESSAGES = {
    "expired": "만료된 진단 링크입니다",
    "revoked": "회수된 진단 링크입니다",
    "submitted": "이미 제출된 진단입니다",
}


@dataclass(frozen=True)
class LinkView:
    """공개 GET 응답(AxLinkOut)."""

    company_name: str
    phase: str
    expires_on: dt.date
    areas: list[dict[str, Any]]  # 증빙 없는 문항(rules.diagnosis.public_areas)
    options: dict[str, list[str]]


def options() -> dict[str, list[str]]:
    """현장 활용 현황 선택지 + 직군·역량 이름(응답 화면이 그린다)."""
    return {
        **{name: list(values) for name, values in FIELD_OPTIONS.items()},
        "roles": list(ROLES),
        "competencies": list(COMPETENCIES),
    }


def _gone(row: DiagLink, today: dt.date) -> None:
    state = link_state(row.status, row.expires_on, today)
    if state != "open":
        raise Gone(GONE_MESSAGES[state], reason=state)


async def link_view(session: AsyncSession, *, token: str, today: dt.date) -> LinkView:
    if not token_shaped(token):
        raise NotFound(NO_LINK)
    found = await crud_link.get_by_token(session, token)
    if found is None:
        raise NotFound(NO_LINK)
    row, company = found
    _gone(row, today)
    return LinkView(
        company_name=company.name,
        phase=row.phase,
        expires_on=row.expires_on,
        areas=public_areas(),
        options=options(),
    )


async def submit(
    session: AsyncSession,
    *,
    token: str,
    answers: Mapping[str, int],
    field: Mapping[str, Any],
    matrix: Mapping[str, int],
    respondent: Mapping[str, Any],
    today: dt.date,
) -> DiagLink:
    """제출 — review 회차를 만들고 링크를 닫는다. 돌려주는 링크의 phase·submitted_at 이 응답이다."""
    if not token_shaped(token):
        raise NotFound(NO_LINK)
    found = await crud_link.get_by_token(session, token)
    if found is None:
        raise NotFound(NO_LINK)
    _gone(found[0], today)  # 잠그기 전 미리
    if await crud_company.lock_company(session, found[0].company_id) is None:
        raise NotFound(NO_LINK)
    found = await crud_link.get_by_token(session, token, fresh=True)
    if found is None:
        raise NotFound(NO_LINK)
    link = found[0]
    _gone(link, today)  # 잠근 뒤 다시 — 같은 토큰의 두 제출은 하나만
    if not is_complete(answers):  # 스키마가 422 로 먼저 막는다(방어)
        raise ValueError("17지표를 전부 답해야 제출한다")
    round_no = await crud_diagnosis.next_round_no(session, link.company_id)
    row = await crud_diagnosis.insert_diagnosis(
        session,
        company_id=link.company_id,
        round_no=round_no,
        phase=link.phase,
        mode="link",
        status="review",
        diagnosed_on=today,
        created_by="link",
        respondent=dict(respondent),
        answers=dict(answers),
        evidence={},
        field=dict(field),
        matrix=dict(matrix),
    )
    link = await crud_link.update_link(
        session,
        link,
        status="submitted",
        submitted_at=func.now(),
        diagnosis_id=row.id,
    )
    prefix = token_prefix(token)
    await crud_audit.insert_audit(
        session,
        actor=f"link:{prefix}",
        action="diag_link.submit",
        target_type=TARGET,
        target_id=str(link.id),
        detail={
            "company_id": link.company_id,
            "diagnosis_id": row.id,
            "round_no": round_no,
            "token_prefix": prefix,
        },
    )
    return link
