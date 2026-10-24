"""회사 입출력 모양(T9a 계획 결정 iii·xii·xiii·xxiv). 관리자만 본다.

- 회사명·담당자는 필수 한 줄 글자(1~200 · 제어 문자 422)다. 전화 ≤ 50 · 업종 ≤ 100 · 메모 ≤ 5000.
- 규모는 5구간 코드다(lt10 · s10_49 · s50_99 · s100_299 · ge300 — 시안 SIZE_ALL, models.diagnosis.COMPANY_SIZES).
- 부서는 ≤ 20 · 같은 이름 두 번은 422 다(DB CHECK 와 같은 상한 — 권장 구성의 트랙 입력).
- PATCH 는 준 칸만 바꾸고 하나 이상이다. null 은 phone·industry·size·memo 만 지운다(name·contact·depts 의 null 은 422).
- 회차 요약 둘: last_round(round_no 최대 · 상태 불문 — 목록 화면) · latest_final_round(final 가운데 round_no 최대 — 개설 ③ 의
  회사 고르기). level 은 17지표를 다 답하기 전이면 null 이다.
- 링크 state 는 계산값이다(open · expired · submitted · revoked — 만료는 저장하지 않는다). 담당자·연락처·응답자·링크 토큰은
  관리자 화면만 싣는다(공개 응답 모양은 schemas/ax.py).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)

from classfit.schemas.auth import no_control_chars
from classfit.schemas.course import Line, LongText, Word, _not_null, _Patch
from classfit.schemas.diagnosis import Depts, DiagMode, DiagStatus, LinkState, Phase

CompanySize = Literal["lt10", "s10_49", "s50_99", "s100_299", "ge300"]

INDUSTRY_MAX = 100
Industry = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=INDUSTRY_MAX),
    AfterValidator(no_control_chars),
]


class CompanyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Line
    contact: Line
    phone: Word | None = None
    industry: Industry | None = None
    size: CompanySize | None = None
    depts: Depts = []
    memo: LongText | None = None


class CompanyPatchIn(_Patch):
    model_config = ConfigDict(extra="forbid")

    name: Line | None = None
    contact: Line | None = None
    phone: Word | None = None
    industry: Industry | None = None
    size: CompanySize | None = None
    depts: Depts | None = None
    memo: LongText | None = None

    @model_validator(mode="after")
    def _some(self) -> CompanyPatchIn:
        if not self.model_fields_set:
            raise ValueError("바꿀 칸이 하나 이상 있어야 합니다")
        _not_null(self, "name", "contact", "depts")
        return self


class RoundBriefOut(BaseModel):
    """회사 요약의 회차 하나(last_round · latest_final_round 공용)."""

    id: int
    round_no: int
    phase: Phase
    mode: DiagMode
    status: DiagStatus
    diagnosed_on: dt.date
    total: int
    level: int | None


class CompanyOut(BaseModel):
    id: int
    name: str
    contact: str
    phone: str | None
    industry: str | None
    size: CompanySize | None
    depts: list[str]
    memo: str | None
    last_round: RoundBriefOut | None
    latest_final_round: RoundBriefOut | None
    created_at: dt.datetime
    updated_at: dt.datetime


class RoundSummaryOut(BaseModel):
    id: int
    round_no: int
    phase: Phase
    mode: DiagMode
    status: DiagStatus
    diagnosed_on: dt.date
    answered: int
    total: int
    level: int | None
    finalized_at: dt.datetime | None


class LinkOut(BaseModel):
    """진단 링크(관리자). token 은 관리자가 링크를 다시 복사하는 원본이다(audit·로그에는 앞 8자만)."""

    id: int
    token: str
    phase: Phase
    recipient: str | None
    issued_on: dt.date
    expires_on: dt.date
    state: LinkState
    submitted_at: dt.datetime | None
    revoked_at: dt.datetime | None
    diagnosis_id: int | None


class LinkedCourseOut(BaseModel):
    id: int
    title: str


class CompanyDetailOut(CompanyOut):
    """회사 상세 — 회차(round_no 순) · 링크(발급 역순) · 연결 강의(보관 포함)."""

    rounds: list[RoundSummaryOut]
    links: list[LinkOut]
    courses: list[LinkedCourseOut]
