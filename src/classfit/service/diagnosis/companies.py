"""회사 만들기·고치기·지우기와 목록·상세 읽기(T9a 결정 iii·x·xi·xii·xxiv). flush 까지만.

- 만들기는 잠그지 않는다(새 행 하나). 고치기는 회사 행 FOR UPDATE(lock_company — 새로 읽는다) 뒤 비교·쓰기다. 잠그지
  않고 읽은 행을 flush 하면 그 사이 삭제가 커밋됐을 때 UPDATE 0행 StaleDataError 500 이 된다(codex 구현 리뷰 1차 ④) —
  잠근 뒤 행이 없으면 404. 바뀐 칸만 쓰고, 바뀐 것이 없으면 audit 도 없다.
- 지우기는 회사 행 FOR UPDATE 뒤 활성(보관하지 않은) 연결 강의 수를 세어 1 이상이면 409. 그다음 연결 강의(전부 보관)를
  id 오름차순으로 잠그고(강의 행 잠금을 기다릴 수 있다 — company → course 순, 결정 xi ⓐ · 강의를 오름차순으로 잡는
  T8 양식 삭제와 같은 차례, codex 1차 ③) 연결을 풀고 회사를 지운다. 회차·링크는 CASCADE 다.
- 목록·상세는 여러 문장으로 모은다. 회차 요약은 .get 으로 꺼내 그 사이 지워진 회차·회사가 있어도 500 이 아니다.
  요약의 level 은 17지표 전이면 None 이다(shown_level, 결정 v).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import company as crud_company
from classfit.crud import diag_link as crud_link
from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud import page as crud_page
from classfit.crud.scope import Subject
from classfit.models import Company, DiagLink, Diagnosis
from classfit.service.rules.diagnosis import link_state, score, shown_level

TARGET = "company"
NO_COMPANY = "회사가 없습니다"


@dataclass(frozen=True)
class RoundBrief:
    """회사 요약의 회차 하나(last_round · latest_final_round)."""

    id: int
    round_no: int
    phase: str
    mode: str
    status: str
    diagnosed_on: dt.date
    total: int
    level: int | None  # 17지표 전이면 None


@dataclass(frozen=True)
class RoundSummary:
    """상세의 회차 목록 한 줄."""

    id: int
    round_no: int
    phase: str
    mode: str
    status: str
    diagnosed_on: dt.date
    answered: int
    total: int
    level: int | None
    finalized_at: dt.datetime | None


@dataclass(frozen=True)
class LinkSummary:
    """상세의 링크 목록 한 줄. state 는 계산값 open·expired·submitted·revoked."""

    id: int
    token: str
    phase: str
    recipient: str | None
    issued_on: dt.date
    expires_on: dt.date
    state: str
    submitted_at: dt.datetime | None
    revoked_at: dt.datetime | None
    diagnosis_id: int | None


@dataclass(frozen=True)
class CompanyView:
    """목록 한 줄(CompanyOut). last_round 는 round_no 최대 회차, latest_final_round 는 final 가운데 최대."""

    company: Company
    last_round: RoundBrief | None
    latest_final_round: RoundBrief | None


@dataclass(frozen=True)
class CompanyDetail(CompanyView):
    """상세(CompanyDetailOut). courses 는 연결 강의 (id, 제목) — 보관 포함."""

    rounds: list[RoundSummary]
    links: list[LinkSummary]
    courses: list[tuple[int, str]]


def _brief(row: Diagnosis | None) -> RoundBrief | None:
    if row is None:
        return None
    result = score(row.answers)
    return RoundBrief(
        id=row.id,
        round_no=row.round_no,
        phase=row.phase,
        mode=row.mode,
        status=row.status,
        diagnosed_on=row.diagnosed_on,
        total=result.total,
        level=shown_level(result),
    )


def _summary(row: Diagnosis) -> RoundSummary:
    result = score(row.answers)
    return RoundSummary(
        id=row.id,
        round_no=row.round_no,
        phase=row.phase,
        mode=row.mode,
        status=row.status,
        diagnosed_on=row.diagnosed_on,
        answered=result.answered,
        total=result.total,
        level=shown_level(result),
        finalized_at=row.finalized_at,
    )


def link_summary(row: DiagLink, today: dt.date) -> LinkSummary:
    """링크 행 → 응답 한 줄(발급·회수 응답 LinkOut 과 상세 links 가 같은 모양이다)."""
    return LinkSummary(
        id=row.id,
        token=row.token,
        phase=row.phase,
        recipient=row.recipient,
        issued_on=row.issued_on,
        expires_on=row.expires_on,
        state=link_state(row.status, row.expires_on, today),
        submitted_at=row.submitted_at,
        revoked_at=row.revoked_at,
        diagnosis_id=row.diagnosis_id,
    )


async def create_company(
    session: AsyncSession, *, fields: Mapping[str, Any], actor: str
) -> Company:
    """fields 는 CompanyIn 칸(name·contact·phone·industry·size·depts·memo)."""
    row = await crud_company.insert_company(session, **fields)
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="company.create",
        target_type=TARGET,
        target_id=str(row.id),
    )
    return row


async def patch_company(
    session: AsyncSession,
    *,
    company_id: int,
    fields: Mapping[str, Any],
    actor: str,
) -> Company:
    """준 칸 가운데 지금 값과 다른 칸만 쓴다. 없으면(그 사이 지워졌으면) 404."""
    row = await crud_company.lock_company(session, company_id)
    if row is None:
        raise NotFound(NO_COMPANY)
    changes = {k: v for k, v in fields.items() if getattr(row, k) != v}
    if changes:
        row = await crud_company.update_company(session, row, **changes)
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="company.update",
            target_type=TARGET,
            target_id=str(company_id),
            detail={"fields": sorted(changes)},
        )
    return row


async def delete_company(session: AsyncSession, *, company_id: int, actor: str) -> None:
    """활성 연결 강의가 있으면 409. 지우면 회차·링크도 지워지고 보관 강의의 연결은 풀린다."""
    if await crud_company.get_company(session, company_id) is None:
        raise NotFound(NO_COMPANY)
    if await crud_company.lock_company(session, company_id) is None:
        raise NotFound(NO_COMPANY)
    active = await crud_company.active_course_count(session, company_id)
    if active:
        raise Conflict(
            f"진행 중인 연결 강의가 {active}건 있어 지울 수 없습니다 — 강의를 보관하거나 지운 뒤 다시 하세요",
            active_courses=active,
        )
    rounds = len(await crud_diagnosis.list_rounds(session, company_id))
    links = len(await crud_link.list_links(session, company_id))
    await crud_company.lock_linked_courses(session, company_id)
    deleted, unlinked = await crud_company.delete_company(session, company_id)
    if not deleted:  # 잠근 행이라 생기지 않는다(방어)
        raise NotFound(NO_COMPANY)
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="company.delete",
        target_type=TARGET,
        target_id=str(company_id),
        detail={"rounds": rounds, "links": links, "unlinked_courses": unlinked},
    )


async def company_detail(
    session: AsyncSession, *, company_id: int, today: dt.date
) -> CompanyDetail:
    """회사 + 회차 목록(round_no 순) + 링크 목록(발급 역순) + 연결 강의 + 회차 요약 둘."""
    company = await crud_company.get_company(session, company_id)
    if company is None:
        raise NotFound(NO_COMPANY)
    rounds = await crud_diagnosis.list_rounds(session, company_id)
    links = await crud_link.list_links(session, company_id)
    courses = await crud_company.linked_courses(session, company_id)
    last, final = await crud_company.round_summaries(session, [company_id])
    return CompanyDetail(
        company=company,
        last_round=_brief(last.get(company_id)),
        latest_final_round=_brief(final.get(company_id)),
        rounds=[_summary(r) for r in rounds],
        links=[link_summary(r, today) for r in links],
        courses=courses,
    )


async def company_list(
    session: AsyncSession,
    subject: Subject,
    *,
    q: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[CompanyView], str | None, bool]:
    """(items, next_cursor, has_more) — (created_at, id) 내림차순 키셋. 깨진 커서는 ValueError(끝점이 422 로)."""
    rows, next_cursor, has_more = await crud_page.keyset_page(
        session, crud_company.list_stmt(subject, q), cursor, limit
    )
    last, final = await crud_company.round_summaries(session, [r.id for r in rows])
    items = [
        CompanyView(
            company=row,
            last_round=_brief(last.get(row.id)),
            latest_final_round=_brief(final.get(row.id)),
        )
        for row in rows
    ]
    return items, next_cursor, has_more
