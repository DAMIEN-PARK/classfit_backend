"""진단 회차·권장 구성·링크 발급 입출력 모양(T9a 계획 결정 iv·v·viii·xii·xiii).

- 답 키는 시안 `ai-ii` 글자("0-0"~"3-3", 17개 — models.diagnosis.ANSWER_KEYS)이고 값은 1~5 다. 역량 키는 "r-c"(직군 0~2 ·
  역량 0~3, 12개 — MATRIX_KEYS)다. 키 집합 밖은 422 다. 답·증빙·현장·역량은 칸마다 통째 교체다(부분 답은 키를 빼고 준다).
- 현장 활용은 시안 blankD().field 의 11칸이다(글자 ≤ 200 · 목록 ≤ 20 · 항목 ≤ 50자, 전부 선택 — 빠진 칸은 빈 값).
- 회차 PATCH 는 하나 이상이고 null 을 받지 않는다. 링크 회차의 진단일(= 제출일)은 지금 값과 다른 값이면 service 가
  FrozenField 를 던지고 끝점이 422 frozen_field 로 바꾼다(같은 값은 바뀐 칸이 아니다).
- 권장 구성은 시안 buildReco 의 키 그대로다(leader · common · tracks · hoursPer · difficulty · capstone · poc · next). 글자 ≤ 500 ·
  목록 ≤ 20 · 트랙 ≤ 20 · 트랙 과정 ≤ 20 이고 모르는 키는 422 다. 공통 항목·트랙 이름·트랙 과정은 개설 ③ 의 섹션·세션
  제목이 되므로 섹션·세션 제목과 같은 한 줄 글자(1~200)다. 트랙 key 는 글자(≤ 50)일 뿐이다 — 직무군 키 8은 초안 생성만 쓴다.
- 리포트 산식·레벨 경계는 service/rules/diagnosis.py 한 곳이다. level 은 17지표를 다 답하기 전이면 null 이다.
- 상태·구분 글자는 models.diagnosis 상수와 같은 값을 여기에 다시 선언한다(schemas 는 service 를 import 하지 않는다 — 계약 ①).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from classfit.models.diagnosis import (
    ANSWER_KEYS,
    DEPTS_MAX,
    MATRIX_KEYS,
    TRACK_COURSES_MAX,
    TRACKS_MAX,
)
from classfit.schemas.auth import no_control_chars
from classfit.schemas.course import Line, Word, _not_null, _Patch

Phase = Literal["pre", "post"]
DiagMode = Literal["visit", "link"]
DiagStatus = Literal["draft", "review", "final"]
LinkState = Literal["open", "expired", "submitted", "revoked"]

FIELD_TEXT_MAX = 200
FIELD_ITEM_MAX = 50
LIST_MAX = 20
RECO_TEXT_MAX = 500
_ANSWER_KEYS = frozenset(ANSWER_KEYS)
_MATRIX_KEYS = frozenset(MATRIX_KEYS)


def _answer_key(value: str) -> str:
    if value not in _ANSWER_KEYS:
        raise ValueError('지표 키는 "0-0"~"3-3"(영역-지표) 17개 가운데 하나입니다')
    return value


def _matrix_key(value: str) -> str:
    if value not in _MATRIX_KEYS:
        raise ValueError('역량 키는 "r-c"(직군 0~2 · 역량 0~3)입니다')
    return value


def _distinct(values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError("같은 값이 두 번 있습니다")
    return values


AnswerKey = Annotated[str, AfterValidator(_answer_key)]
MatrixKey = Annotated[str, AfterValidator(_matrix_key)]
Level5 = Annotated[int, Field(ge=1, le=5)]
Answers = dict[AnswerKey, Level5]
# 지표마다 증빙 두 칸(시안 ev[2]) — 확인한 것만 참
Evidence = Annotated[list[bool], Field(min_length=2, max_length=2)]
Matrix = dict[MatrixKey, Level5]
FieldText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=FIELD_TEXT_MAX),
    AfterValidator(no_control_chars),
]
FieldItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=FIELD_ITEM_MAX),
    AfterValidator(no_control_chars),
]
FieldItems = Annotated[list[FieldItem], Field(max_length=LIST_MAX)]
RecoText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=RECO_TEXT_MAX),
    AfterValidator(no_control_chars),
]
RecoItems = Annotated[list[RecoText], Field(max_length=LIST_MAX)]
Depts = Annotated[list[Word], Field(max_length=DEPTS_MAX), AfterValidator(_distinct)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 회차


class FieldIn(_Strict):
    """현장 활용(시안 blankD().field). 키 이름은 시안 글자 그대로라 toolsEtc 만 낙타 꼴이다."""

    ratio: FieldText = ""
    freq: FieldText = ""
    tools: FieldItems = []
    toolsEtc: FieldText = ""
    uses: FieldItems = []
    works: FieldItems = []
    work: FieldText = ""
    wfreq: FieldText = ""
    whours: FieldText = ""
    wnow: FieldText = ""
    wpain: FieldText = ""


class DiagnosisCreateIn(_Strict):
    """방문 회차 생성. 진단일을 비우면 오늘이다."""

    phase: Phase
    diagnosed_on: dt.date | None = None


DIAGNOSIS_PATCH_FIELDS = (
    "answers",
    "evidence",
    "field",
    "matrix",
    "phase",
    "diagnosed_on",
)


class DiagnosisPatchIn(_Strict, _Patch):
    answers: Answers | None = None
    evidence: dict[AnswerKey, Evidence] | None = None
    field: FieldIn | None = None
    matrix: Matrix | None = None
    phase: Phase | None = None
    diagnosed_on: dt.date | None = None

    @model_validator(mode="after")
    def _some(self) -> DiagnosisPatchIn:
        if not self.model_fields_set:
            raise ValueError("바꿀 칸이 하나 이상 있어야 합니다")
        _not_null(self, *DIAGNOSIS_PATCH_FIELDS)
        return self


class RespondentOut(BaseModel):
    name: str
    title: str | None
    email: str | None


class DiagnosisOut(BaseModel):
    id: int
    company_id: int
    round_no: int
    phase: Phase
    mode: DiagMode
    status: DiagStatus
    diagnosed_on: dt.date
    created_by: str
    respondent: RespondentOut | None
    answers: dict[str, int]
    evidence: dict[str, list[bool]]
    field: dict[str, Any]
    matrix: dict[str, int]
    reco: dict[str, Any] | None
    finalized_at: dt.datetime | None
    finalized_by_id: int | None
    created_at: dt.datetime
    updated_at: dt.datetime


# ── 권장 구성(시안 buildReco 모양)


class LeaderIn(_Strict):
    target: RecoText
    hours: RecoText
    items: RecoItems


class CommonIn(_Strict):
    hours: RecoText
    items: Annotated[list[Line], Field(max_length=LIST_MAX)]  # 「공통교육」 세션 제목
    focus: RecoText


class TrackIn(_Strict):
    key: Word
    name: Line
    depts: Depts
    courses: Annotated[list[Line], Field(max_length=TRACK_COURSES_MAX)]
    candidates_missing: bool


class PocIn(_Strict):
    method: RecoText
    items: RecoItems
    next: RecoText


class RecoIn(_Strict):
    """PATCH …/reco 본문 — 권장 구성 전체(통째 교체)."""

    leader: LeaderIn
    common: CommonIn
    tracks: Annotated[list[TrackIn], Field(max_length=TRACKS_MAX)]
    hoursPer: RecoText
    difficulty: RecoText
    capstone: bool
    poc: PocIn
    next: RecoItems


# ── 리포트


class AreaOut(BaseModel):
    no: str
    name: str
    n: int
    done: int
    pts: int


class ItemOut(BaseModel):
    key: str
    area_no: str
    name: str
    level: int | None  # 미응답 None
    pts: int  # 미응답 0
    evidence_count: int


class PreviousOut(BaseModel):
    """비교 대상 = 앞 회차 가운데 17지표를 다 답한 가장 최근 확정·검토 대기 회차(읽는 시점 계산)."""

    diagnosis_id: int
    round_no: int
    phase: Phase
    status: DiagStatus
    diagnosed_on: dt.date
    total: int
    level: int | None
    areas: list[int]  # 영역 점수 넷
    delta_total: int
    delta_areas: list[int]


class ReportOut(BaseModel):
    diagnosis_id: int
    company_id: int
    round_no: int
    phase: Phase
    mode: DiagMode
    status: DiagStatus
    diagnosed_on: dt.date
    complete: bool
    answered: int
    total: int
    level: int | None
    areas: list[AreaOut]
    items: list[ItemOut]
    previous: PreviousOut | None
    reco: dict[str, Any]
    reco_saved: bool


# ── 링크 발급


class LinkIssueIn(_Strict):
    """받는 분을 비우면 회사 담당자다. 만료일을 비우면 오늘 + 14, 주면 오늘 ~ 오늘 + 365(끝점이 오늘과 대조)."""

    phase: Phase
    recipient: Line | None = None
    expires_on: dt.date | None = None
