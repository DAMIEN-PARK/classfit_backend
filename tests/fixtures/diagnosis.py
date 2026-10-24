"""T9a 시험 도우미: 진단 상수·답 사전 · 응답 키 집합 · CRUD 전용 도우미(4단계) / service 도우미(5단계).

- 답 사전 ANSWERS_* 는 golden 사례와 같은 값이다(단위 시험은 golden.json 을 읽고, 계약·통합 시험은 이 상수를 쓴다).
- 키 집합은 응답을 정확히(==) 잴 때 쓴다(T9a 결정 xii). PUBLIC_FORBIDDEN 은 공개 응답 어디에도 없어야 할 키다.
- CRUD 전용 도우미(make_company · insert_round · insert_link)는 service 없이 상태를 바로 박는다 — 표 제약 시험과 시험 준비용.
  운영 경로(잠금·audit)를 재는 시험은 5단계의 service 도우미를 쓴다.
- 회사·사람 이름은 A사·B사 · "담당자 가" 꼴이고 이메일은 example.com 이다.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app import deps
from classfit.crud import company as crud_company
from classfit.crud import diag_link as crud_link
from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud import schedule as crud_schedule
from classfit.models import Company, CourseSession, DiagLink, Diagnosis, Section
from classfit.models.diagnosis import ANSWER_KEYS

TODAY = date(2026, 11, 3)  # T2b 동시성 시험과 같은 날(화)
LINK_DAYS = 14

ANSWERS_ALL_1 = dict.fromkeys(ANSWER_KEYS, 1)  # golden dg-all-1 → 160 · L2
ANSWERS_ALL_5 = dict.fromkeys(ANSWER_KEYS, 5)  # golden dg-all-5 → 800 · L5
ANSWERS_MIXED = {k: (i % 5) + 1 for i, k in enumerate(ANSWER_KEYS)}  # dg-mixed-450-l3
ANSWERS_9 = {
    k: (i % 5) + 1 for i, k in enumerate(ANSWER_KEYS[:9])
}  # dg-partial-9 → 220
# 현장 활용 현황 11칸(시안 blankD().field 의 키 그대로)
FIELD_SAMPLE: dict[str, Any] = {
    "ratio": "10~30%",
    "freq": "주 1회",
    "tools": ["ChatGPT", "기타"],
    "toolsEtc": "사내 챗봇",
    "uses": ["문서·보고서 작성", "번역"],
    "works": ["문서·매뉴얼 검색", "보고서·품의서 작성", "데이터 입력·정리"],
    "work": "기술문의 응대",
    "wfreq": "매일",
    "whours": "40시간",
    "wnow": "메일로 답한다",
    "wpain": "같은 질문이 반복된다",
}
# 직군 3 × 역량 4. 경영진만 평균 3.5, 전체 평균은 3 아래 — 난이도는 최댓값으로 중 · 심화
MATRIX_SAMPLE: dict[str, int] = {
    **{f"0-{c}": v for c, v in enumerate((4, 3, 4, 3))},
    **{f"1-{c}": v for c, v in enumerate((1, 2, 1, 2))},
    **{f"2-{c}": v for c, v in enumerate((1, 2, 1, 2))},
}
RESPONDENT = {"name": "응답자 가", "title": "대표", "email": "Rep@Example.com"}
RESPONDENT_EMAIL = "rep@example.com"  # 저장·응답은 소문자(T2b Email 정규화)
COMPANY_BODY: dict[str, Any] = {
    "name": "A사",
    "contact": "담당자 가",
    "size": "s10_49",
    "depts": ["영업", "생산"],  # 직무군 cs · prod
}
# 첫 일치 규칙으로 직무군 여덟이 실제로 다 나오는 부서 20개(앞 여덟이 eng·cs·buy·prod·qa·vis·film·mgt)
DEPTS_20 = [
    "설계팀",
    "영업1팀",
    "구매",
    "생산2공장",
    "품질보증",
    "SW팀",
    "필름팀",
    "총무",
    "설계2팀",
    "제어팀",
    "영업2팀",
    "고객지원",
    "구매2팀",
    "자재관리",
    "생산1공장",
    "제조팀",
    "품질관리",
    "QC팀",
    "인사팀",
    "회계팀",
]
# 개설 ③ 본문의 나머지(start·diagnosis_id 는 부르는 쪽이 더한다). 일차 0 이라 세션이 전부 일정표 undated 에 보인다
UNDATED_BODY: dict[str, Any] = {
    "title": "A사 AX 교육",
    "client_name": "A사",
    "method": "집체",
    "hours_per_person": 12,
    "start_on": "2026-11-02",
    "end_on": "2026-11-04",
    "day_count": 0,
    "slot_min": 120,
    "break_min": 0,
}
# 공통 3 · 트랙 2(괄호 뒤 떼기의 증인 "고객 접점 · 수주 (영업·CS)") · 과정 2씩 · 캡스톤 → 섹션 3 · 세션 9
RECO_SAMPLE: dict[str, Any] = {
    "leader": {
        "target": "리더 10명",
        "hours": "4시간",
        "items": ["AX 방향 이해", "적용 과제 정의"],
    },
    "common": {
        "hours": "6시간",
        "items": ["AI 보안 기초", "AI 도구 업무활용", "부서 소통 세션"],
        "focus": "AI 인프라 및 기술 보강",
    },
    "tracks": [
        {
            "key": "cs",
            "name": "고객 접점 · 수주 (영업·CS)",
            "depts": ["영업"],
            "courses": ["견적 자료 구조화", "CS 사례 매뉴얼"],
            "candidates_missing": False,
        },
        {
            "key": "prod",
            "name": "생산기술 · 제조",
            "depts": ["생산"],
            "courses": ["작업표준서 초안", "예방보전 점검표"],
            "candidates_missing": False,
        },
    ],
    "hoursPer": "직무응용 10시간",
    "difficulty": "하 · 기초",
    "capstone": True,
    "poc": {
        "method": "LLM 해석형 (문서·문의 처리)",
        "items": ["기술문의 응대 자동화"],
        "next": "과제 정의서 → 시제품",
    },
    "next": ["결과 공유 미팅"],
}

# ── 응답 키 집합(결정 xii)
ROUND_BRIEF_KEYS = frozenset(
    {"id", "round_no", "phase", "mode", "status", "diagnosed_on", "total", "level"}
)
COMPANY_KEYS = frozenset(
    {
        "id",
        "name",
        "contact",
        "phone",
        "industry",
        "size",
        "depts",
        "memo",
        "last_round",
        "latest_final_round",
        "created_at",
        "updated_at",
    }
)
DETAIL_KEYS = COMPANY_KEYS | {"rounds", "links", "courses"}
ROUND_KEYS = frozenset(
    {
        "id",
        "round_no",
        "phase",
        "mode",
        "status",
        "diagnosed_on",
        "answered",
        "total",
        "level",
        "finalized_at",
    }
)
LINK_KEYS = frozenset(
    {
        "id",
        "token",
        "phase",
        "recipient",
        "issued_on",
        "expires_on",
        "state",
        "submitted_at",
        "revoked_at",
        "diagnosis_id",
    }
)
LINKED_COURSE_KEYS = frozenset({"id", "title"})
DIAGNOSIS_KEYS = frozenset(
    {
        "id",
        "company_id",
        "round_no",
        "phase",
        "mode",
        "status",
        "diagnosed_on",
        "created_by",
        "respondent",
        "answers",
        "evidence",
        "field",
        "matrix",
        "reco",
        "finalized_at",
        "finalized_by_id",
        "created_at",
        "updated_at",
    }
)
REPORT_KEYS = frozenset(
    {
        "diagnosis_id",
        "company_id",
        "round_no",
        "phase",
        "mode",
        "status",
        "diagnosed_on",
        "complete",
        "answered",
        "total",
        "level",
        "areas",
        "items",
        "previous",
        "reco",
        "reco_saved",
    }
)
AREA_KEYS = frozenset({"no", "name", "n", "done", "pts"})
ITEM_KEYS = frozenset({"key", "area_no", "name", "level", "pts", "evidence_count"})
PREVIOUS_KEYS = frozenset(
    {
        "diagnosis_id",
        "round_no",
        "phase",
        "status",
        "diagnosed_on",
        "total",
        "level",
        "areas",
        "delta_total",
        "delta_areas",
    }
)
TRACK_KEYS = frozenset({"key", "name", "depts", "courses", "candidates_missing"})
AX_KEYS = frozenset({"company_name", "phase", "expires_on", "areas", "options"})
AX_AREA_KEYS = frozenset({"no", "name", "desc", "items"})
AX_ITEM_KEYS = frozenset({"key", "name", "question", "levels"})
AX_OPTION_KEYS = frozenset(
    {"ratio", "freq", "tools", "uses", "works", "wfreq", "roles", "competencies"}
)
SUBMITTED_KEYS = frozenset({"phase", "submitted_at"})
# 공개 응답(GET·POST·410·404·422·405 본문) 어디에도 없어야 할 키(재귀 — tests/fixtures/enter.py json_keys)
PUBLIC_FORBIDDEN = frozenset(
    {
        "contact",
        "phone",
        "recipient",
        "email",
        "memo",
        "depts",
        "token",
        "total",
        "level",
        "round_no",
        "answers",
        "evidence",
    }
)


def make_token(tag: str) -> str:
    """시험용 링크 토큰 — 32자 [0-9a-f](token_urlsafe 글자 안). tag 마다 다르다."""
    return hashlib.sha256(f"t9a-link-{tag}".encode()).hexdigest()[:32]


# ── CRUD 전용(4단계 — service 없음)


async def make_company(session: AsyncSession, **over: Any) -> Company:
    """회사 한 행(COMPANY_BODY + over). 잠금·audit 없이 crud 로 넣는다."""
    return await crud_company.insert_company(session, **{**COMPANY_BODY, **over})


async def insert_round(
    session: AsyncSession,
    company_id: int,
    *,
    round_no: int,
    answers: dict[str, int] | None = None,
    status: str = "draft",
    mode: str = "visit",
    phase: str = "pre",
    diagnosed_on: date = TODAY,
    respondent: dict[str, Any] | None = None,
    reco: dict[str, Any] | None = None,
    admin_id: int = 1,
) -> Diagnosis:
    """회차 한 행을 상태 그대로 박는다. final 이면 draft 로 넣고 finalize_row 로 확정(CHECK 두 방향)."""
    row = await crud_diagnosis.insert_diagnosis(
        session,
        company_id=company_id,
        round_no=round_no,
        phase=phase,
        mode=mode,
        status="draft" if status == "final" else status,
        diagnosed_on=diagnosed_on,
        created_by="link" if mode == "link" else f"admin:{admin_id}",
        respondent=respondent,
        answers=dict(answers or {}),
        evidence={},
        field={},
        matrix={},
    )
    if status == "final":
        row = await crud_diagnosis.finalize_row(
            session, row, admin_id=admin_id, reco=reco or RECO_SAMPLE
        )
    elif reco is not None:
        row = await crud_diagnosis.update_diagnosis(session, row, reco=reco)
    return row


async def insert_link(
    session: AsyncSession,
    company_id: int,
    *,
    token: str,
    status: str = "open",
    phase: str = "pre",
    issued_on: date = TODAY,
    expires_on: date | None = None,
    recipient: str | None = None,
    diagnosis_id: int | None = None,
) -> DiagLink:
    """링크 한 행을 상태 그대로 박는다(open 으로 넣은 뒤 submitted·revoked 로)."""
    row = await crud_link.insert_link(
        session,
        company_id=company_id,
        token=token,
        phase=phase,
        recipient=recipient,
        issued_on=issued_on,
        expires_on=expires_on or issued_on + timedelta(days=LINK_DAYS),
    )
    if status == "submitted":
        row = await crud_link.update_link(
            session,
            row,
            status="submitted",
            submitted_at=func.now(),
            diagnosis_id=diagnosis_id,
        )
    elif status == "revoked":
        row = await crud_link.update_link(
            session, row, status="revoked", revoked_at=func.now()
        )
    return row


def set_today(app: FastAPI, d: date) -> None:
    """계약 시험의 오늘(app.deps.today 주입)."""
    app.dependency_overrides[deps.today] = lambda: d


async def sections_of(
    session: AsyncSession, course_id: int
) -> list[tuple[Section, list[CourseSession]]]:
    """그 강의의 (섹션, 세션들) — 섹션 (sort, id) 순, 세션 id 순."""
    sessions = await crud_schedule.list_sessions(session, course_id)
    return [
        (
            section,
            sorted(
                (s for s in sessions if s.section_id == section.id), key=lambda s: s.id
            ),
        )
        for section in await crud_schedule.list_sections(session, course_id)
    ]
