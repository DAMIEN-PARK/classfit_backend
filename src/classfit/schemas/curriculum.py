"""커리큘럼 입출력 모양(T4 계획 결정 v·vi·xv).

- 하루 격자는 start_time~end_time 을 slot_min 교시 + break_min 쉬는 시간으로 나눈다. 교시 수는
  service.rules.pool.slots_per_day 가 정하고 응답의 slots_per_day 칸에 싣는다(강사.html:670 scSlots).
- 차시표 PUT 은 통째 교체다. 빈 칸(제목 없음)은 보내지 않는다. 여기서는 모양(1 이상·제목 1~200·200개까지)만 보고,
  격자 밖·(day, slot) 중복·시각 순서는 service 가 422 로 막는다(loc ["body", "slots", i, "day"|"slot"] ·
  ["body", "slots", i] · PATCH 는 ["body", <칸>]).
- 시각은 시간대 없는 "HH:MM" 이다(T2a Clock). PATCH 는 준 칸만 바꾸고 null 을 받지 않는 칸에 null 이면 422.
- 관리자는 플래그 셋(reviewed·pub·active)만 고친다(결정 xviii).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from classfit.models.curriculum import CURRICULUM_CONTENT_FIELDS, CURRICULUM_DAYS_MAX
from classfit.schemas.attachment import Title
from classfit.schemas.course import Clock, LongText
from classfit.schemas.pool import (
    Difficulty,
    JobGroups,
    OwnerOut,
    PatchModel,
    PoolFileOut,
    Text,
    not_null,
)

SLOTS_MAX = 200

Days = Annotated[int, Field(ge=1, le=CURRICULUM_DAYS_MAX)]
SlotMin = Annotated[int, Field(ge=10, le=180)]
BreakMin = Annotated[int, Field(ge=0, le=60)]


def _ordered(start: dt.time | None, end: dt.time | None) -> None:
    if start is not None and end is not None and start >= end:
        raise ValueError("start_time 은 end_time 보다 앞이어야 합니다")


class CurriculumIn(BaseModel):
    title: Title
    job_groups: JobGroups
    difficulty: Difficulty
    days: Days
    start_time: Clock
    end_time: Clock
    slot_min: SlotMin
    break_min: BreakMin
    goal: Text = None
    output: Text = None

    @model_validator(mode="after")
    def _hours(self) -> CurriculumIn:
        _ordered(self.start_time, self.end_time)
        return self

    def fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in CURRICULUM_CONTENT_FIELDS}


class CurriculumPatchIn(PatchModel):
    """두 시각을 함께 주면 여기서, 한쪽만 주면 저장값과 합쳐 service 가 순서를 본다."""

    title: Title | None = None
    job_groups: JobGroups | None = None
    difficulty: Difficulty | None = None
    days: Days | None = None
    start_time: Clock | None = None
    end_time: Clock | None = None
    slot_min: SlotMin | None = None
    break_min: BreakMin | None = None
    goal: Text = None
    output: Text = None

    @field_validator(
        "title",
        "job_groups",
        "difficulty",
        "days",
        "start_time",
        "end_time",
        "slot_min",
        "break_min",
    )
    @classmethod
    def _content_not_null(cls, value: Any) -> Any:
        return not_null(value)

    @model_validator(mode="after")
    def _hours(self) -> CurriculumPatchIn:
        _ordered(self.start_time, self.end_time)
        return self


class SlotIn(BaseModel):
    day: int = Field(ge=1)
    slot: int = Field(ge=1)
    title: Title
    description: LongText | None = None

    def fields(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "slot": self.slot,
            "title": self.title,
            "description": self.description or None,
        }


class SlotsPutIn(BaseModel):
    slots: list[SlotIn] = Field(max_length=SLOTS_MAX)


class CurriculumFlagsPatchIn(PatchModel):
    """관리자 플래그. reviewed → pub → active 순으로 적용한다(결정 v)."""

    reviewed: bool | None = None
    pub: bool | None = None
    active: bool | None = None

    @field_validator("reviewed", "pub", "active")
    @classmethod
    def _flags_not_null(cls, value: Any) -> Any:
        return not_null(value)


class SlotOut(BaseModel):
    day: int
    slot: int
    title: str
    description: str | None


class CurriculumOut(BaseModel):
    id: str
    title: str
    job_groups: list[str]
    difficulty: str
    days: int
    start_time: dt.time
    end_time: dt.time
    slot_min: int
    break_min: int
    slots_per_day: int
    goal: str | None
    output: str | None
    slots: list[SlotOut]  # (day, slot) 순
    files: list[PoolFileOut]
    reviewed: bool
    reviewed_at: dt.datetime | None
    pub: bool
    active: bool


class CurriculumAdminItemOut(CurriculumOut):
    owner: OwnerOut
