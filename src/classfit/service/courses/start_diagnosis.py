"""개설 시작점 ③(확정 진단)의 판정·잠금과 구조 채움(T9a 결정 vii·xi). flush 까지만.

open.open_course() 안에서 starts.load·apply 를 거쳐서만 부른다(단일 진입). service.diagnosis 는 부르지 않는다 —
회차·회사는 crud 로 읽는다(계약 ②).
- 판정 load_diagnosis: 회차 404 → 회사 FOR KEY SHARE(hold_company — 회사 삭제의 FOR UPDATE 와 줄 선다) 거짓이면 404 →
  회차 다시 읽기(fresh) 404 → 확정(final) 아니면 409 → 권장 구성이 없으면 409(확정이 스냅샷을 남기므로 방어).
- 구조 apply_diagnosis: 기획안 :770 "권장 교육 구성의 트랙·대표 과정이 섹션·세션이 됨, 강사 미배정". 섹션 「공통교육」
  (공통 과정마다 세션) + 트랙마다 섹션(트랙 이름의 " (" 앞, 세션 = 대표 과정 + 캡스톤이면 「캡스톤 교육 세션」).
  세션은 제목만 — 설명 없음 · 키워드 없음 · 분 = 새 강의 교시 · 비공개 · 일차 미정 · 강사 미배정 · 풀·커리큘럼 참조 없음
  (과정 이름은 스냅샷 글자로 고정돼 있다 — 풀 과정이 뒤에 바뀌어도 강의는 그대로, CAT-007 꼴).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import company as crud_company
from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud import schedule as crud_schedule
from classfit.models import Course
from classfit.service.rules.reco import reco_sections

NO_ROUND = "진단 회차가 없습니다"


@dataclass(frozen=True)
class DiagnosisSource:
    diagnosis_id: int
    company_id: int  # 새 강의의 회사 연결
    reco: dict[str, Any]  # 확정 때 스냅샷한 권장 구성


async def load_diagnosis(session: AsyncSession, diagnosis_id: int) -> DiagnosisSource:
    """확정 회차의 권장 구성을 판정하고 회사를 잡는다(쓰기 없음)."""
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id)
    if row is None:
        raise NotFound(NO_ROUND)
    if not await crud_company.hold_company(session, row.company_id):
        raise NotFound(NO_ROUND)
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id, fresh=True)
    if row is None:
        raise NotFound(NO_ROUND)
    if row.status != "final":
        raise Conflict("확정한 회차로만 개설합니다 — 회차를 먼저 확정하세요")
    if row.reco is None:
        raise Conflict("권장 교육 구성이 없는 회차입니다")
    return DiagnosisSource(
        diagnosis_id=row.id, company_id=row.company_id, reco=dict(row.reco)
    )


async def apply_diagnosis(
    session: AsyncSession, course: Course, src: DiagnosisSource
) -> dict[str, int]:
    """권장 구성의 섹션·세션을 새 강의에 넣는다. course.open audit detail 에 더할 칸(sections · sessions)."""
    sections = sessions = 0
    for sort, (title, titles) in enumerate(reco_sections(src.reco)):
        section = await crud_schedule.insert_section(
            session, course.id, title=title, sort=sort, description=None
        )
        sections += 1
        for session_title in titles:
            await crud_schedule.insert_session(
                session,
                section.id,
                title=session_title,
                description=None,
                keywords=[],
                minutes=course.slot_min,
                is_open=False,
                day_no=None,
                slot=None,
            )
            sessions += 1
    return {"sections": sections, "sessions": sessions}
