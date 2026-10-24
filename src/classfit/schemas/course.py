"""강의·일정 입출력 모양.

- 본문 모양 오류는 422 다. 저장 상태와의 충돌(그 강의에 없는 일차 등)은 service 가 409 로 낸다(T2a 계획 결정 v).
- PATCH 는 준 칸만 바꾼다(model_fields_set). null 을 받지 않는 칸에 null 을 주면 422.
- 시각은 시간대 없는 "HH:MM" 이다. 한 줄 글자는 제어 문자를, 여러 줄 글자는 NUL 을 422 로 막는다(psycopg DataError → 500 방지).
- status 는 저장값이 아니라 오늘 기준 계산값이다(service.rules.status.course_status_at).
"""

from __future__ import annotations

import datetime as dt
import itertools
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from classfit.models.pool import POOL_ID_MAX
from classfit.schemas.auth import no_control_chars
from classfit.schemas.invite_code import InviteCodeOut

CourseStatus = Literal["prep", "running", "ended"]


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("NUL 문자를 쓸 수 없습니다")
    return value


def _naive(value: dt.time) -> dt.time:
    if value.tzinfo is not None:
        raise ValueError("시간대 없는 시각(HH:MM)만 받습니다")
    return value


Line = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(no_control_chars),
]
Word = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
    AfterValidator(no_control_chars),
]
LongText = Annotated[str, StringConstraints(max_length=5000), AfterValidator(_no_nul)]
Clock = Annotated[dt.time, AfterValidator(_naive)]
# 풀 과정·커리큘럼 글자 id(T4 경로 변수 검사 app/endpoints/pool.py _TEXT_ID 와 같은 꼴)
TextId = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=POOL_ID_MAX, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    ),
]
DayNo = Annotated[int, Field(ge=1, le=60)]
Slot = Annotated[int, Field(ge=1, le=60)]
# 본문의 행 id(BIGINT). 2**63 이상은 DB 가 범위 오류를 내 422 대신 500 이 되므로 모양에서 막는다(core/cursor.py _MAX_ID 와 같은 까닭)
DB_ID_LIMIT = 2**63
DbId = Annotated[int, Field(ge=1, lt=DB_ID_LIMIT)]


class _Patch(BaseModel):
    """준 칸만 바꾸는 본문."""

    def changes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}


def _not_null(model: BaseModel, *names: str) -> None:
    for name in names:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"{name} 은 null 일 수 없습니다")


def _ordered(earlier: Any, later: Any, message: str) -> None:
    if earlier is not None and later is not None and earlier >= later:
        raise ValueError(message)


# ── 강의


class CourseOpenIn(BaseModel):
    """개설(기획안 A3 시작점 ①②③④). day_count ≥ 1 이면 기간은 일정이 정하므로 end_on 을 받지 않는다.

    start 와 원본 칸의 짝: blank 는 원본 없음 · clone 은 source_course_id 만 · curriculum 은 curriculum_id 만(T5 결정 iii) ·
    diagnosis(③ 확정 진단)는 diagnosis_id 만이고 회사는 회차에서 온다(company_id 를 같이 주면 422). ①②④ 는 company_id 를
    선택으로 받는다(CRS-003, T9a 결정 vii). 기본 정보·일정 칸은 네 시작점 모두 본문이 정한다(서버는 원본에서 값을 채우지
    않는다). 판별 유니온은 오류 loc 에 태그가 끼어 쓰지 않는다.
    """

    start: Literal["blank", "clone", "curriculum", "diagnosis"]
    source_course_id: DbId | None = None
    curriculum_id: TextId | None = None
    diagnosis_id: DbId | None = None
    company_id: DbId | None = None
    title: Line
    client_name: Line
    course_type: Word | None = None
    cohort: Word | None = None
    method: Word
    hours_per_person: int = Field(ge=0, le=10_000)
    start_on: dt.date
    end_on: dt.date | None = None
    day_count: int = Field(ge=0, le=40)
    day_start: Clock | None = None
    day_end: Clock | None = None
    slot_min: int = Field(default=50, ge=1, le=600)
    break_min: int = Field(default=10, ge=0, le=240)
    intro: LongText | None = None
    notice: LongText | None = None

    @model_validator(mode="after")
    def _source(self) -> CourseOpenIn:
        wanted = {
            "blank": (False, False, False),
            "clone": (True, False, False),
            "curriculum": (False, True, False),
            "diagnosis": (False, False, True),
        }[self.start]
        given = (
            self.source_course_id is not None,
            self.curriculum_id is not None,
            self.diagnosis_id is not None,
        )
        if given != wanted:
            raise ValueError(
                "start 가 blank 면 원본이 없고, clone 이면 source_course_id 만,"
                " curriculum 이면 curriculum_id 만, diagnosis 면 diagnosis_id 만 줍니다"
            )
        if self.start == "diagnosis" and self.company_id is not None:
            raise ValueError(
                "diagnosis 는 회사를 회차에서 가져오므로 company_id 를 주지 않습니다"
            )
        return self

    @model_validator(mode="after")
    def _period(self) -> CourseOpenIn:
        if self.day_count == 0:
            if self.end_on is None:
                raise ValueError("day_count 가 0 이면 end_on 이 필요합니다")
            if self.end_on < self.start_on:
                raise ValueError("end_on 은 start_on 보다 앞일 수 없습니다")
            return self
        if self.end_on is not None:
            raise ValueError(
                "day_count 가 1 이상이면 end_on 은 일정에서 정해지므로 주지 않습니다"
            )
        if self.day_start is None or self.day_end is None:
            raise ValueError("day_count 가 1 이상이면 day_start·day_end 가 필요합니다")
        _ordered(
            self.day_start, self.day_end, "day_start 는 day_end 보다 앞이어야 합니다"
        )
        return self


COURSE_NOT_NULL = (
    "title",
    "client_name",
    "method",
    "hours_per_person",
    "start_on",
    "end_on",
    "slot_min",
    "break_min",
)


class CoursePatchIn(_Patch):
    title: Line | None = None
    client_name: Line | None = None
    course_type: Word | None = None
    cohort: Word | None = None
    method: Word | None = None
    hours_per_person: int | None = Field(default=None, ge=0, le=10_000)
    start_on: dt.date | None = None
    end_on: dt.date | None = None
    slot_min: int | None = Field(default=None, ge=1, le=600)
    break_min: int | None = Field(default=None, ge=0, le=240)
    intro: LongText | None = None
    notice: LongText | None = None

    @model_validator(mode="after")
    def _period(self) -> CoursePatchIn:
        _not_null(self, *COURSE_NOT_NULL)
        if (
            self.start_on is not None
            and self.end_on is not None
            and self.end_on < self.start_on
        ):
            raise ValueError("end_on 은 start_on 보다 앞일 수 없습니다")
        return self


class StatusSetIn(BaseModel):
    status: CourseStatus


class CourseOut(BaseModel):
    id: int
    title: str
    client_name: str
    course_type: str | None
    cohort: str | None
    method: str
    hours_per_person: int
    start_on: dt.date
    end_on: dt.date
    slot_min: int
    break_min: int
    intro: str | None
    notice: str | None
    status: CourseStatus
    status_manual: bool
    archived_at: dt.datetime | None
    created_at: dt.datetime
    company_id: int | None


class CourseOpenedOut(BaseModel):
    course: CourseOut
    invite_code: InviteCodeOut


# ── 일정


class DayIn(BaseModel):
    date: dt.date
    start_time: Clock
    end_time: Clock
    lunch_start: Clock | None = None
    lunch_end: Clock | None = None

    @model_validator(mode="after")
    def _hours(self) -> DayIn:
        _ordered(
            self.start_time,
            self.end_time,
            "start_time 은 end_time 보다 앞이어야 합니다",
        )
        if (self.lunch_start is None) != (self.lunch_end is None):
            raise ValueError("lunch_start·lunch_end 는 둘 다 주거나 둘 다 비웁니다")
        _ordered(
            self.lunch_start,
            self.lunch_end,
            "lunch_start 는 lunch_end 보다 앞이어야 합니다",
        )
        return self


class DaysPutIn(BaseModel):
    """일차 전체를 바꾼다. 주는 순서대로 1..n 일차가 된다. 날짜는 겹침 없이 오름차순이어야 한다."""

    days: list[DayIn] = Field(max_length=60)

    @model_validator(mode="after")
    def _ascending(self) -> DaysPutIn:
        dates = [d.date for d in self.days]
        if any(a >= b for a, b in itertools.pairwise(dates)):
            raise ValueError("days 의 날짜는 겹침 없이 오름차순이어야 합니다")
        return self


class DayPatchIn(_Patch):
    date: dt.date | None = None
    start_time: Clock | None = None
    end_time: Clock | None = None
    lunch_start: Clock | None = None
    lunch_end: Clock | None = None

    @model_validator(mode="after")
    def _hours(self) -> DayPatchIn:
        _not_null(self, "date", "start_time", "end_time")
        _ordered(
            self.start_time,
            self.end_time,
            "start_time 은 end_time 보다 앞이어야 합니다",
        )
        _ordered(
            self.lunch_start,
            self.lunch_end,
            "lunch_start 는 lunch_end 보다 앞이어야 합니다",
        )
        return self


class SectionIn(BaseModel):
    title: Line
    sort: int = Field(default=0, ge=0, le=10_000)
    description: LongText | None = None


class SectionPatchIn(_Patch):
    title: Line | None = None
    sort: int | None = Field(default=None, ge=0, le=10_000)
    description: LongText | None = None

    @model_validator(mode="after")
    def _shape(self) -> SectionPatchIn:
        _not_null(self, "title", "sort")
        return self


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    sort: int
    description: str | None


class SessionIn(BaseModel):
    """세션 넣기. slot 은 day_no 가 있어야 한다. time_start·time_end 는 예외 시각(둘 다 또는 둘 다 없음)."""

    title: Line
    description: LongText | None = None
    day_no: DayNo | None = None
    slot: Slot | None = None
    minutes: int | None = Field(default=None, ge=1, le=1440)
    time_start: Clock | None = None
    time_end: Clock | None = None
    keywords: list[Word] = Field(default_factory=list, max_length=20)
    is_open: bool = False

    @model_validator(mode="after")
    def _shape(self) -> SessionIn:
        if self.slot is not None and self.day_no is None:
            raise ValueError("slot 은 day_no 가 있어야 합니다")
        if (self.time_start is None) != (self.time_end is None):
            raise ValueError("time_start·time_end 는 둘 다 주거나 둘 다 비웁니다")
        _ordered(
            self.time_start,
            self.time_end,
            "time_start 는 time_end 보다 앞이어야 합니다",
        )
        return self


class SessionPatchIn(_Patch):
    title: Line | None = None
    description: LongText | None = None
    day_no: DayNo | None = None
    slot: Slot | None = None
    minutes: int | None = Field(default=None, ge=1, le=1440)
    time_start: Clock | None = None
    time_end: Clock | None = None
    keywords: list[Word] | None = Field(default=None, max_length=20)
    is_open: bool | None = None
    # 담당 강사(T5 결정 vii). null 은 배정 해제다. 승인 강사만(409), 없는 강사 404
    instructor_id: DbId | None = None

    @model_validator(mode="after")
    def _shape(self) -> SessionPatchIn:
        _not_null(self, "title", "keywords", "is_open")
        given = self.model_fields_set
        if (
            {"slot", "day_no"} <= given
            and self.slot is not None
            and self.day_no is None
        ):
            raise ValueError("slot 은 day_no 가 있어야 합니다")
        _ordered(
            self.time_start,
            self.time_end,
            "time_start 는 time_end 보다 앞이어야 합니다",
        )
        return self


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    title: str
    description: str | None
    day_no: int | None
    slot: int | None
    minutes: int | None
    time_start: dt.time | None
    time_end: dt.time | None
    keywords: list[str]
    is_open: bool
    pool_course_id: str | None = None
    curriculum_id: str | None = None
    instructor_id: int | None = None


class ScheduleSessionOut(BaseModel):
    """일정표의 세션 한 칸. start·end 는 계산한 "HH:MM"(service.rules.schedule.session_time), 못 정하면 null.

    담당 강사는 id·이름(T5 결정 xiv), 미배정이면 둘 다 null.
    """

    id: int
    section_id: int
    title: str
    slot: int | None
    start: str | None
    end: str | None
    instructor_id: int | None = None
    instructor_name: str | None = None


class ScheduleDayOut(BaseModel):
    day_no: int
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    lunch_start: dt.time | None
    lunch_end: dt.time | None
    sessions: list[ScheduleSessionOut]


class ScheduleOut(BaseModel):
    days: list[ScheduleDayOut]
    undated: list[ScheduleSessionOut]  # 일차 미정 세션
