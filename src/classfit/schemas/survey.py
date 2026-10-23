"""만족도 설문 입출력 모양(T8 계획 결정 iii·v·vi·vii·viii·ix·xi·xxv·xxvi).

- 사람 칸이 없다(Design 1절 만족도 공개 범위) — 이름·이메일·등록 id·제출 시각(submitted_at)은 어떤 응답에도 없다.
- 상태는 저장값이 아니라 오늘 기준 계산값이다(service.rules.survey.status_at). 상태 셋·문항 유형 다섯은 그 글자를 여기에
  다시 선언한다(schemas 는 service 를 import 하지 않는다 — 계약 ①). 수강생 조회 상태는 설문 없음 none 이 하나 더 있다.
- 문항은 아홉 칸이다(key · type · text · area · required · star · is_overall · options · custom). 빠진 칸은 기본값으로
  채워 늘 아홉 키로 저장·응답한다. 여기는 모양(키·타입·길이)만 잰다. 교차 규칙(key 유일 · star·is_overall 은 scale 만 ·
  is_overall 은 많아야 하나 · options·custom 은 선택형만 · 답 문항 하나 이상)은 service 가 rules.survey.question_errors
  로 재고 끝점이 422 로 바꾼다.
- 배포 본문은 열기·닫기 모드다(open {mode, date?} · close {mode, date?}, 기본 now · end_plus_14). mode 가 date 면
  date 가 있어야 하고, 아니면 없어야 한다. "오늘 이상"·"열림일 이상" 은 잠근 강의마다 service 가 잰다(결정 vi).
- 배포 설문 PATCH 는 문항·열림일·닫힘일 가운데 하나 이상이고 null 을 받지 않는다. 마감·다시 열기는 동작 경로다.
- 설문 목록 항목 SurveyOut 과 결과 머리 SurveyHeadOut 은 같은 칸에서 시각 둘(created_at · closed_at)만 다르다 —
  결과 머리에는 시각 칸이 없다(결정 xi).
- 제출 본문 SubmitIn 은 끝점이 app.deps.limited_json 으로 파싱 전에 크기를 막고 읽는다(결정 ix). 답 값의 모양은
  rules.survey.answer_errors 가 잰다. survey_id·questions_hash 는 수강생이 본 설문판이다.
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

from classfit.models.survey import KEY_PATTERN, NAME_MAX, OPTIONS_MAX, QUESTIONS_MAX
from classfit.schemas.auth import no_control_chars
from classfit.schemas.course import DbId, Line, _not_null, _Patch

SurveyStatus = Literal["scheduled", "open", "closed"]
LearnerSurveyStatus = Literal["none", "scheduled", "open", "closed"]
QuestionType = Literal["scale", "single", "multi", "text", "info"]
OpenMode = Literal["now", "course_end", "date"]
CloseMode = Literal["end_plus_14", "open_plus_7", "date"]

TEXT_MAX = 300
AREA_MAX = 30
OPTION_MAX = 100
COURSE_IDS_MAX = 50
# rules.survey.questions_hash 의 모양(sha256 앞 16자)
HASH_PATTERN = r"^[0-9a-f]{16}$"


def _distinct(values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError("선택지가 겹칩니다")
    return values


def _dedupe(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))


QuestionKey = Annotated[str, StringConstraints(pattern=KEY_PATTERN)]
QuestionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TEXT_MAX),
    AfterValidator(no_control_chars),
]
Area = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=AREA_MAX),
    AfterValidator(no_control_chars),
]
Option = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=OPTION_MAX),
    AfterValidator(no_control_chars),
]
Options = Annotated[
    list[Option],
    Field(min_length=2, max_length=OPTIONS_MAX),
    AfterValidator(_distinct),
]
TemplateName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX),
    AfterValidator(no_control_chars),
]


# ── 문항


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: QuestionKey
    type: QuestionType
    text: QuestionText
    area: Area | None = None
    required: bool | None = None  # 안 주면 답 문항은 true, 안내문(info)은 false
    star: bool = False
    is_overall: bool = False
    options: Options | None = None
    custom: bool = False

    @model_validator(mode="after")
    def _required(self) -> QuestionIn:
        if self.required is None:
            self.required = self.type != "info"
        return self


Questions = Annotated[list[QuestionIn], Field(min_length=1, max_length=QUESTIONS_MAX)]


class QuestionOut(BaseModel):
    key: str
    type: QuestionType
    text: str
    area: str | None
    required: bool
    star: bool
    is_overall: bool
    options: list[str] | None
    custom: bool


# ── 양식


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TemplateName
    note: Line | None = None
    questions: Questions


class TemplatePatchIn(_Patch):
    model_config = ConfigDict(extra="forbid")

    name: TemplateName | None = None
    note: Line | None = None
    questions: Questions | None = None

    @model_validator(mode="after")
    def _shape(self) -> TemplatePatchIn:
        _not_null(self, "name", "questions")
        return self


class TemplateOut(BaseModel):
    id: int
    name: str
    note: str | None
    is_default: bool
    questions: list[QuestionOut]
    deployed: int  # 이 양식으로 배포한 설문 수
    created_at: dt.datetime
    updated_at: dt.datetime


class TemplateListOut(BaseModel):
    items: list[TemplateOut]


# ── 배포


def _mode_date(mode: str, date: dt.date | None) -> None:
    if (mode == "date") != (date is not None):
        raise ValueError("mode 가 date 면 date 를 주고, 아니면 주지 않습니다")


class OpenSpecIn(BaseModel):
    """now 오늘 · course_end 그 강의 종료일(지났으면 오늘) · date 지정일(오늘 이상)."""

    model_config = ConfigDict(extra="forbid")

    mode: OpenMode = "now"
    date: dt.date | None = None

    @model_validator(mode="after")
    def _date(self) -> OpenSpecIn:
        _mode_date(self.mode, self.date)
        return self


class CloseSpecIn(BaseModel):
    """end_plus_14 종료일 + survey_close_days(열림일보다 앞이면 열림일 + 7) · open_plus_7 · date 지정일(열림일 이상)."""

    model_config = ConfigDict(extra="forbid")

    mode: CloseMode = "end_plus_14"
    date: dt.date | None = None

    @model_validator(mode="after")
    def _date(self) -> CloseSpecIn:
        _mode_date(self.mode, self.date)
        return self


class DeployIn(BaseModel):
    """강의마다 설문 한 행(한 트랜잭션, 하나라도 409 면 전부 0행). course_ids 는 겹침을 지운다."""

    model_config = ConfigDict(extra="forbid")

    course_ids: Annotated[
        list[DbId],
        Field(min_length=1, max_length=COURSE_IDS_MAX),
        AfterValidator(_dedupe),
    ]
    template_id: DbId
    open: OpenSpecIn = Field(default_factory=OpenSpecIn)
    close: CloseSpecIn = Field(default_factory=CloseSpecIn)


class SurveyPatchIn(_Patch):
    """문항(응답 0건일 때만) · 열림일(예약일 때만) · 닫힘일(예약·열림일 때만) — 판정은 service."""

    model_config = ConfigDict(extra="forbid")

    questions: Questions | None = None
    open_on: dt.date | None = None
    close_on: dt.date | None = None

    @model_validator(mode="after")
    def _shape(self) -> SurveyPatchIn:
        if not self.model_fields_set:
            raise ValueError(
                "바꿀 칸(questions·open_on·close_on)이 하나 이상 있어야 합니다"
            )
        _not_null(self, "questions", "open_on", "close_on")
        return self


class SurveyOut(BaseModel):
    """관리자 목록·배포·마감 응답. closed_at 은 관리자가 닫았거나 밀려난 시각, locked 는 응답 1건 이상(문항 잠금)."""

    id: int
    course_id: int
    course_title: str
    client_name: str
    template_id: int | None  # 원본 양식을 지우면 null(이름·문항 스냅샷은 남는다)
    template_name: str
    status: SurveyStatus
    open_on: dt.date
    close_on: dt.date
    closed_at: dt.datetime | None
    reopened_at: dt.datetime | None
    current: bool  # 그 강의의 현재 설문(밀려난 설문은 false)
    responses: int
    total: int  # 그 강의 등록 수(조회 시점)
    locked: bool
    created_at: dt.datetime


class DeployOut(BaseModel):
    items: list[SurveyOut]  # 강의 id 순


class SurveyHeadOut(BaseModel):
    """결과 머리(A5·I7). 시각 칸이 없다."""

    survey_id: int
    course_id: int
    course_title: str
    client_name: str
    template_name: str
    status: SurveyStatus
    open_on: dt.date
    close_on: dt.date
    reopened_at: dt.datetime | None
    current: bool
    responses: int
    total: int
    locked: bool


# ── 수강생


class LearnerSurveyQuestionsOut(BaseModel):
    id: int
    open_on: dt.date
    close_on: dt.date
    questions_hash: str  # 제출이 되돌려 보낸다
    questions: list[QuestionOut]


class LearnerSurveyOut(BaseModel):
    """status 가 open 일 때만 survey(문항)를 싣는다. responded 는 현재 설문에 내 등록의 응답이 있는지."""

    status: LearnerSurveyStatus
    survey: LearnerSurveyQuestionsOut | None
    responded: bool
    prefill_dept: str | None  # 내 등록의 부서(입장 때 값)


class SubmitIn(BaseModel):
    """답은 {문항 key: 값}. 수강생이 본 설문판(survey_id · questions_hash)에 묶는다 — 다르면 409 survey_changed."""

    model_config = ConfigDict(extra="forbid")

    survey_id: DbId
    questions_hash: Annotated[str, StringConstraints(pattern=HASH_PATTERN)]
    answers: Annotated[
        dict[QuestionKey, Any], Field(min_length=1, max_length=QUESTIONS_MAX)
    ]


class SubmitOut(BaseModel):
    survey_id: int
    responded: bool
