"""진단 회차 목록(T9b 결정 xxvii — 승인자 결정 2026-10-24 기획안 대조 Q4 ⓑ · 기획안 A1 :726-727). 읽기만, 잠금 없음.

- 문장은 crud.diagnosis.list_stmt(첫 WHERE company_scope — 관리자 전부 · 그 밖 0행) 하나이고 status 로 거른다. 관리자 홈의
  진단 검토 대기 셈(crud.home_admin)이 같은 문장을 센다(COM-004 — 요약 건수 = 상세 목록).
- 쪽은 (created_at, id) 내림차순 키셋이다(새로 받은 것부터 — 링크 회차의 created_at 은 제출 트랜잭션 시각). 깨진 커서는
  keyset_page 의 ValueError 그대로다(끝점이 먼저 decode_cursor 로 422 를 낸다 — T9a 회사 목록 꼴).
- 한 쪽의 회사 이름·링크 제출 시각은 crud.diagnosis.list_heads 한 문장이다. 쪽을 읽은 뒤 회차(회사 삭제면 CASCADE)가
  지워지고 커밋되면 그 회차는 건너뛴다 — 쪽이 limit 보다 짧을 수 있고 next_cursor·has_more 는 keyset_page 값 그대로다
  (T8 service.surveys.views.admin_list 꼴, KeyError 500 없음).
- 항목에는 응답자 이름만 싣는다(직함·이메일, 회사 연락처, 답·증빙·현장·역량·권장 구성 없음). 총점·레벨은
  rules.diagnosis.score · shown_level 이다(17지표 전이면 레벨 None — T9a RoundSummary 와 같은 계산).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud import page as crud_page
from classfit.crud.scope import Subject
from classfit.models import Diagnosis
from classfit.service.rules import diagnosis as rules_diagnosis


@dataclass(frozen=True)
class RoundListItem:
    """목록 한 줄(DiagnosisListItemOut). respondent_name·submitted_at 은 링크 회차만 있다(방문은 None)."""

    id: int
    company_id: int
    company_name: str
    round_no: int
    phase: str
    mode: str
    status: str
    diagnosed_on: dt.date
    respondent_name: str | None
    submitted_at: dt.datetime | None
    total: int
    level: int | None


def _item(
    row: Diagnosis, company_name: str, submitted_at: dt.datetime | None
) -> RoundListItem:
    result = rules_diagnosis.score(row.answers)
    respondent = row.respondent or {}
    name = respondent.get("name")
    return RoundListItem(
        id=row.id,
        company_id=row.company_id,
        company_name=company_name,
        round_no=row.round_no,
        phase=row.phase,
        mode=row.mode,
        status=row.status,
        diagnosed_on=row.diagnosed_on,
        respondent_name=str(name) if name is not None else None,
        submitted_at=submitted_at,
        total=result.total,
        level=rules_diagnosis.shown_level(result),
    )


async def round_list(
    session: AsyncSession,
    subject: Subject,
    *,
    status: str,
    cursor: str | None,
    limit: int,
) -> tuple[list[RoundListItem], str | None, bool]:
    """(items, next_cursor, has_more)."""
    rows, next_cursor, has_more = await crud_page.keyset_page(
        session, crud_diagnosis.list_stmt(subject, status), cursor, limit
    )
    heads = await crud_diagnosis.list_heads(session, [r.id for r in rows])
    items = [
        _item(row, *heads[row.id])
        for row in rows
        if row.id in heads  # 그 사이 지워진 회차는 건너뛴다
    ]
    return items, next_cursor, has_more
