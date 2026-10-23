"""교육 기록 입출력 모양(T7 계획 결정 iii·iv·vi·x·xi·xxi·xxii).

- 저장 본문 RecordIn 은 여섯 칸이다: held_on(실시일, 필수) · start_time·end_time(시간대 없는 "HH:MM", 둘 다 있거나 둘 다
  없음, 시작 < 끝) · attendees(0..10000, 숫자만 — 개인 출석부가 아니다) · content(앞뒤 공백을 지운 뒤 1..5000자, NUL 금지,
  줄바꿈 허용) · note(앞뒤 공백을 지운 뒤 5000자까지, 비면 null). 그 밖의 키는 422 extra_forbidden 이다. 모양 밖은
  DB CHECK 에 닿기 전에 422 다. 둘 다 다듬은 값으로 바뀐 칸을 비교한다(공백만 다른 본문은 바뀐 칸이 아니다, R4).
- 상태 none(기록 없음) · done(강사 저장) · ok(관리자 확인·저장)와 주체 종류는 service.rules.record 와 같은 글자를 여기에
  다시 선언한다(schemas 는 service 를 import 하지 않는다 — 계약 ①). 끝점이 RecordFields(**body.model_dump()) 로 바꾼다.
- 사람 칸은 강사 이름 하나(recorded_by_name — 관리자가 쓴 기록은 null 이고 역할만 recorded_by, 결정 xxi).
- 기록 목록의 세션 항목은 계획(일차·날짜·일정표 시각 plan_start·plan_end)과 기록·사진이다. 사진은 세션마다 올린 순 앞
  20장과 photos_more 이고, summary.photos 는 전체 장수다(결정 x). 관리자 항목은 담당 강사 id·이름과 seen 사진이다.
- 계획대로 기록·일괄 확인 응답은 {day_no, status, changed, session_ids} 다(REC-003 처리 건수와 대상).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from classfit.models.record import ATTENDEES_MAX
from classfit.schemas.course import Clock, _no_nul, _ordered
from classfit.schemas.photo import ActorKind, AdminPhotoOut, MyPhotoOut

RecordStatus = Literal["none", "done", "ok"]
CONTENT_MAX = 5000

Content = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=CONTENT_MAX),
    AfterValidator(_no_nul),
]


def _no_nul_or_none(value: str) -> str | None:
    return _no_nul(value) or None


# 비고: Content 와 같은 strip 꼴, 다듬어 비면 None
Note = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=CONTENT_MAX),
    AfterValidator(_no_nul_or_none),
]


class RecordIn(BaseModel):
    """기록 저장 본문(강사·관리자 같은 모양)."""

    model_config = ConfigDict(extra="forbid")

    held_on: dt.date
    start_time: Clock | None = None
    end_time: Clock | None = None
    attendees: int | None = Field(default=None, ge=0, le=ATTENDEES_MAX)
    content: Content
    note: Note | None = None

    @model_validator(mode="after")
    def _times(self) -> RecordIn:
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("start_time·end_time 은 둘 다 주거나 둘 다 비웁니다")
        _ordered(
            self.start_time,
            self.end_time,
            "start_time 은 end_time 보다 앞이어야 합니다",
        )
        return self


class SessionRecordOut(BaseModel):
    session_id: int
    status: RecordStatus  # 행이 있으면 done · ok
    held_on: dt.date
    start_time: dt.time | None
    end_time: dt.time | None
    attendees: int | None
    content: str
    note: str | None
    recorded_by: ActorKind
    recorded_by_name: str | None  # 기록한 강사 이름(관리자가 썼으면 null)
    recorded_at: dt.datetime  # 내용을 마지막으로 저장한 시각
    confirmed_at: dt.datetime | None


class RecordSessionOut(BaseModel):
    """강사 기록 목록의 세션 하나(내 세션만)."""

    session_id: int
    section_id: int
    section_title: str
    title: str
    day_no: int | None
    date: dt.date | None  # 일차 날짜(일차 미정이면 null)
    plan_start: str | None  # 일정표와 같은 계산의 "HH:MM", 못 정하면 null
    plan_end: str | None
    status: RecordStatus
    record: SessionRecordOut | None
    photos: list[MyPhotoOut]  # 올린 순 앞 20장
    photos_more: bool


class AdminRecordSessionOut(RecordSessionOut):
    """관리자 기록 목록의 세션 하나(미배정 포함 모든 세션)."""

    instructor_id: int | None
    instructor_name: str | None
    photos: list[AdminPhotoOut]  # type: ignore[assignment]  # 관리자는 editable 대신 seen


class RecordSummaryOut(BaseModel):
    sessions: int
    recorded: int  # done ∨ ok
    confirmed: int  # ok
    missing: int  # 일차 날짜 ≤ 오늘 ∧ 기록 없음
    photos: int  # 목록 세션의 전체 사진 장수(앞 20장 상한과 무관)


class MyCourseRecordsOut(BaseModel):
    course_id: int
    summary: RecordSummaryOut
    sessions: list[RecordSessionOut]


class AdminCourseRecordsOut(BaseModel):
    course_id: int
    summary: RecordSummaryOut
    sessions: list[AdminRecordSessionOut]


class RecordDayOut(BaseModel):
    day_no: int
    status: Literal["done", "ok"]  # 이번 요청이 대상에 준 상태
    changed: int
    session_ids: list[int]  # 바뀐 세션, 섹션 순서 → 교시 → id
