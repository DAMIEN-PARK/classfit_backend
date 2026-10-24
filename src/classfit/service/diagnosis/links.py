"""자가진단 링크 발급·회수(T9a 결정 vi·x·xi). flush 까지만.

- 둘 다 회사 행 FOR UPDATE(lock_company) 뒤 링크를 다시 읽고 쓴다. 회사당 open 은 하나다.
- 발급: 만료가 지난 open 링크는 먼저 회수하고(revoked · reason expired — 시안 axSync 의 결과를 "만료는 계산" 안에서),
  만료 전 open 이 남아 있으면 409. 토큰은 secrets.token_urlsafe 24바이트 → 32자(이 파일의 new_token 한 곳). 만료일 기본은
  발급일 + 14(Design :44), 주면 발급일 ~ 발급일 + 365. 범위 밖은 끝점이 422 로 먼저 막는다.
- 회수: open(만료 전·후) → revoked · 이미 revoked 면 그대로(멱등, audit 없음) · submitted 는 409.
- audit detail 에는 토큰 앞 8자(token_prefix)만 싣는다. 토큰 전체는 로그·audit·오류 글자에 싣지 않는다(결정 x·xxv).
"""

from __future__ import annotations

import datetime as dt
import re
import secrets

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import company as crud_company
from classfit.crud import diag_link as crud_link
from classfit.models import DiagLink
from classfit.service.rules.diagnosis import expiry_window, link_state

LINK_TOKEN_BYTES = 24  # → 32자 [A-Za-z0-9_-](192비트)
LINK_DEFAULT_DAYS = 14
LINK_MAX_DAYS = 365
TOKEN_PREFIX_LENGTH = 8
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32}")
TARGET = "diag_link"
NO_COMPANY = "회사가 없습니다"
NO_LINK = "진단 링크가 없습니다"
OPEN_LEFT = "발급 중인 링크를 먼저 회수하세요"


def new_token() -> str:
    return secrets.token_urlsafe(LINK_TOKEN_BYTES)


def token_prefix(token: str) -> str:
    """audit·로그에 싣는 토큰 앞 8자."""
    return token[:TOKEN_PREFIX_LENGTH]


def token_shaped(token: str) -> bool:
    """토큰 모양(32자 token_urlsafe 글자)인가. 모양 밖은 DB 를 보지 않고 없는 토큰과 같은 404 다(결정 i)."""
    return TOKEN_RE.fullmatch(token) is not None


def link_window(today: dt.date) -> tuple[dt.date, dt.date]:
    """(만료일 기본값, 만료일 상한) — 발급일 + 14 · + 365. 날짜 끝(9999-12-31)을 넘으면 그 날로 멈춘다."""
    return expiry_window(today, default_days=LINK_DEFAULT_DAYS, max_days=LINK_MAX_DAYS)


async def issue_link(
    session: AsyncSession,
    *,
    company_id: int,
    phase: str,
    recipient: str | None,
    expires_on: dt.date | None,
    today: dt.date,
    actor: str,
) -> DiagLink:
    """open 링크 하나를 발급한다. recipient 가 비면 회사 담당자."""
    company = await crud_company.get_company(session, company_id)
    if company is None:
        raise NotFound(NO_COMPANY)
    default_on, latest_on = link_window(today)
    expires_on = default_on if expires_on is None else expires_on
    if not today <= expires_on <= latest_on:  # 끝점이 422 로 먼저 막는다
        raise ValueError("만료일은 오늘부터 365일 안이다")
    company = await crud_company.lock_company(session, company_id)
    if company is None:
        raise NotFound(NO_COMPANY)
    left = 0
    for row in await crud_link.open_links(session, company_id):
        if link_state(row.status, row.expires_on, today) != "expired":
            left += 1
            continue
        await crud_link.update_link(
            session, row, status="revoked", revoked_at=func.now()
        )
        await crud_audit.insert_audit(
            session,
            actor=actor,
            action="diag_link.revoke",
            target_type=TARGET,
            target_id=str(row.id),
            detail={"token_prefix": token_prefix(row.token), "reason": "expired"},
        )
    if left:
        raise Conflict(OPEN_LEFT)
    row = await crud_link.insert_link(
        session,
        company_id=company_id,
        token=new_token(),
        phase=phase,
        recipient=recipient or company.contact,
        issued_on=today,
        expires_on=expires_on,
    )
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="diag_link.issue",
        target_type=TARGET,
        target_id=str(row.id),
        detail={
            "company_id": company_id,
            "phase": phase,
            "expires_on": expires_on.isoformat(),
            "token_prefix": token_prefix(row.token),
        },
    )
    return row


async def revoke_link(
    session: AsyncSession, *, token: str, actor: str
) -> tuple[DiagLink, bool]:
    """(링크, 이번에 바꿨는가). 없는 토큰·모양 밖 404 · 제출된 링크 409 · 이미 회수면 그대로."""
    if not token_shaped(token):
        raise NotFound(NO_LINK)
    found = await crud_link.get_by_token(session, token)
    if found is None:
        raise NotFound(NO_LINK)
    if await crud_company.lock_company(session, found[0].company_id) is None:
        raise NotFound(NO_LINK)
    found = await crud_link.get_by_token(session, token, fresh=True)
    if found is None:
        raise NotFound(NO_LINK)
    row = found[0]
    if row.status == "submitted":
        raise Conflict(
            "제출된 링크는 회수할 수 없습니다 — 회차를 지우면 응답을 받지 않은 것으로 됩니다"
        )
    if row.status == "revoked":
        return row, False
    row = await crud_link.update_link(
        session, row, status="revoked", revoked_at=func.now()
    )
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action="diag_link.revoke",
        target_type=TARGET,
        target_id=str(row.id),
        detail={"token_prefix": token_prefix(row.token)},
    )
    return row, True
