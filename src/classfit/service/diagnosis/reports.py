"""진단 리포트와 권장 구성 후보(T9a 결정 v·viii). 읽기만 — GET 이 상태를 만들지 않는다.

- 리포트: 산식(rules.diagnosis.score) · 지표 행(점수 · 증빙 수) · 비교 대상(앞 회차 가운데 review ∨ final ∧ 17지표 —
  읽을 때마다 고른다, 스냅샷 없음) · 권장 구성(저장한 것 ∨ 그 순간 초안, reco_saved). level 은 17지표 전이면 None.
  회차와 회사(부서)는 한 문장으로 읽는다.
- 후보 candidate_titles: T4 공개 ∧ 활성 AX 풀 과정(crud.catalog.published_ax_courses — 이 함수에서만 부른다)을 직무군마다
  job_groups 교집합으로 걸러 앞 CANDIDATES_MAX 제목(id 순). 강사 고유 과정은 후보가 아니다(기획안 :844·:1022).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.crud import catalog as crud_catalog
from classfit.crud import diagnosis as crud_diagnosis
from classfit.models.diagnosis import CANDIDATES_MAX
from classfit.service.rules.diagnosis import (
    AREAS,
    delta,
    item_points,
    score,
    shown_level,
)
from classfit.service.rules.reco import DEPT_GROUPS, build_reco

NO_ROUND = "진단 회차가 없습니다"


@dataclass(frozen=True)
class ReportArea:
    no: str
    name: str
    n: int
    done: int
    pts: int


@dataclass(frozen=True)
class ReportItem:
    key: str
    area_no: str
    name: str
    level: int | None  # 답(1..5), 미응답 None
    pts: int  # 미응답 0
    evidence_count: int  # 체크한 증빙 수(점수에 들지 않는다)


@dataclass(frozen=True)
class Previous:
    """비교 대상 회차와 증감(이번 − 비교 대상)."""

    diagnosis_id: int
    round_no: int
    phase: str
    status: str
    diagnosed_on: dt.date
    total: int
    level: int | None
    areas: list[int]  # 영역 점수 넷
    delta_total: int
    delta_areas: list[int]


@dataclass(frozen=True)
class Report:
    diagnosis_id: int
    company_id: int
    round_no: int
    phase: str
    mode: str
    status: str
    diagnosed_on: dt.date
    complete: bool
    answered: int
    total: int
    level: int | None
    areas: list[ReportArea]
    items: list[ReportItem]
    previous: Previous | None
    reco: dict[str, Any]
    reco_saved: bool


async def candidate_titles(session: AsyncSession) -> dict[str, list[str]]:
    """직무군 key → 대표 과정 후보 제목(앞 3개). 후보가 없는 직무군은 빈 목록."""
    courses = await crud_catalog.published_ax_courses(session)
    return {
        group.key: [
            c.title for c in courses if set(c.job_groups) & set(group.job_groups)
        ][:CANDIDATES_MAX]
        for group in DEPT_GROUPS
    }


def _evidence_count(evidence: dict[str, Any], key: str) -> int:
    return sum(1 for checked in evidence.get(key) or [] if checked)


async def report_of(session: AsyncSession, *, diagnosis_id: int) -> Report:
    found = await crud_diagnosis.get_with_company(session, diagnosis_id)
    if found is None:
        raise NotFound(NO_ROUND)
    row, company = found
    result = score(row.answers)
    level = shown_level(result)  # 17지표 전부 답했을 때만 — complete 와 같은 뜻
    points = item_points(row.answers)
    items = [
        ReportItem(
            key=item.key,
            area_no=area.no,
            name=item.name,
            level=row.answers.get(item.key),
            pts=points.get(item.key, 0),
            evidence_count=_evidence_count(row.evidence, item.key),
        )
        for area in AREAS
        for item in area.items
    ]
    previous = None
    prev = await crud_diagnosis.previous_complete(session, row.company_id, row.round_no)
    if prev is not None:
        prev_result = score(prev.answers)
        delta_total, delta_areas = delta(result, prev_result)
        previous = Previous(
            diagnosis_id=prev.id,
            round_no=prev.round_no,
            phase=prev.phase,
            status=prev.status,
            diagnosed_on=prev.diagnosed_on,
            total=prev_result.total,
            level=shown_level(prev_result),
            areas=[a.pts for a in prev_result.areas],
            delta_total=delta_total,
            delta_areas=delta_areas,
        )
    reco = row.reco
    if reco is None:
        reco = build_reco(
            score=result,
            answers=row.answers,
            field=row.field,
            matrix=row.matrix,
            depts=company.depts,
            candidates=await candidate_titles(session),
        )
    return Report(
        diagnosis_id=row.id,
        company_id=row.company_id,
        round_no=row.round_no,
        phase=row.phase,
        mode=row.mode,
        status=row.status,
        diagnosed_on=row.diagnosed_on,
        complete=level is not None,
        answered=result.answered,
        total=result.total,
        level=level,
        areas=[
            ReportArea(no=area.no, name=area.name, n=a.n, done=a.done, pts=a.pts)
            for area, a in zip(AREAS, result.areas, strict=True)
        ],
        items=items,
        previous=previous,
        reco=reco,
        reco_saved=row.reco is not None,
    )
