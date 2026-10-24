"""공개 진단 링크 입출력 모양(T9a 계획 결정 vi·xii·xiii). 인증 없는 끝점이라 입력을 좁게 받는다.

- 공개 응답에 담당자·연락처·받는 분·토큰·메모·부서·점수·레벨·회차 번호가 없다(T9a 결정 xii). 문항에는 증빙 문구가 없다.
- 제출 본문은 17지표 전부가 필수다 — 빠지면 422 violations ["body", "answers"] 의 msg 에 미응답 키를 적는다. 증빙은 받지
  않는다(모르는 키는 422 — 증빙은 관리자가 검토하며 채운다).
- 응답자는 이름 필수 · 직책 ≤ 50 · 이메일은 입장 스키마와 같은 정규화다(앞뒤 공백 제거 · 소문자 · 254자 — schemas.enter.Email).
- 제출 응답은 {phase, submitted_at} 뿐이다(점수·요약 없음 — 결과는 관리자가 검토·확정한 뒤 전한다, 기획안 :835).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from classfit.models.diagnosis import ANSWER_KEYS
from classfit.schemas.course import Line, Word
from classfit.schemas.diagnosis import Answers, FieldIn, Matrix, Phase
from classfit.schemas.enter import Email


def _all_answered(value: dict[str, int]) -> dict[str, int]:
    missing = [key for key in ANSWER_KEYS if key not in value]
    if missing:
        raise ValueError(f"17지표를 모두 답해야 합니다 — 미응답 {', '.join(missing)}")
    return value


class RespondentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Line
    title: Word | None = None
    email: Email | None = None


class AxSubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: Annotated[Answers, AfterValidator(_all_answered)]
    field: FieldIn = Field(default_factory=FieldIn)
    matrix: Matrix = Field(default_factory=dict)
    respondent: RespondentIn


class AxItemOut(BaseModel):
    key: str
    name: str
    question: str
    levels: list[str]


class AxAreaOut(BaseModel):
    no: str
    name: str
    desc: str
    items: list[AxItemOut]


class AxOptionsOut(BaseModel):
    """현장 활용 선택지(시안 FIELD · select)와 역량표의 직군·역량 이름."""

    ratio: list[str]
    freq: list[str]
    tools: list[str]
    uses: list[str]
    works: list[str]
    wfreq: list[str]
    roles: list[str]
    competencies: list[str]


class AxLinkOut(BaseModel):
    company_name: str
    phase: Phase
    expires_on: dt.date
    areas: list[AxAreaOut]
    options: AxOptionsOut


class AxSubmittedOut(BaseModel):
    phase: Phase
    submitted_at: dt.datetime
