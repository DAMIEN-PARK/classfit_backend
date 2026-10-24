"""관리자 홈(시안 관리자.html:1323 renderHome · 요구정의서 COM-004 · T9b 결정 xiii·xiv·xviii). 읽기만, 잠금 없음.

- 셈 여덟(승인 대기 · 진행 강의 · 미배정 세션 · 미검토 등록 · 열린 설문 · 진단 검토 대기 · 미기록 · 새 사진)은 상세 목록과
  같은 조건이고(crud.home_admin 머리 표), 최근 처리 이력은 HOME_AUDIT_MAX 건이다(시안 LOG.slice(0,10)). 이력 항목에 detail
  은 없다(결정 xiii).
- 실행 문장은 홈 한 번에 정확히 둘이다: 셈 한 문장 + 이력 한 문장(결정 xviii). 인증 SELECT 는 끝점 의존성 몫이라 밖이다.
- 관리자가 아니면 질의 없이 Forbidden 이다 — 끝점이 AdminCaller 라 평소에는 닿지 않는 방어선이다.
- 진행 중 강의 표 · 곧 시작 · 진단 요약 · 사진 미리 보기 · 검토 대기 회차 목록은 싣지 않는다 — 각 목록 끝점 몫이다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Forbidden
from classfit.crud import home_admin as crud_home_admin
from classfit.crud.home_admin import AuditRow, HomeCounts
from classfit.crud.scope import Subject

HOME_AUDIT_MAX = 10
ADMIN_ONLY = "관리자만 볼 수 있습니다"


@dataclass(frozen=True)
class AdminHome:
    """홈 응답. 칸 이름이 응답 칸과 같다(끝점이 from_attributes 로 읽는다)."""

    counts: HomeCounts
    recent_audit: list[AuditRow]


async def admin_home(
    session: AsyncSession, subject: Subject, *, today: dt.date
) -> AdminHome:
    if subject.type != "admin":
        raise Forbidden(ADMIN_ONLY)
    counts = await crud_home_admin.counts(session, subject, today=today)
    recent = await crud_home_admin.recent_audit(session, subject, limit=HOME_AUDIT_MAX)
    return AdminHome(counts=counts, recent_audit=recent)
