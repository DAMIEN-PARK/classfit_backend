"""심화 과정 입출력 모양(T4 계획 결정 xvii). 관리자만 쓴다.

- 시안 hr:'18시간' 은 정수 hours 로 받는다(ADVANCED_HOURS_RANGE 1~200). 특징 features 는 5개까지(표 CHECK 와 같다).
- PATCH 는 준 칸만 바꾸고 pub·active 도 여기서 켜고 끈다. 삭제는 없다(사용 중지 = active 거짓, 기획안 :780).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
)

from classfit.models.advanced import (
    ADVANCED_CONTENT_FIELDS,
    ADVANCED_FEATURES_MAX,
    ADVANCED_HOURS_RANGE,
)
from classfit.schemas.attachment import Title
from classfit.schemas.auth import no_control_chars
from classfit.schemas.pool import PatchModel, Text, not_null


def _line(max_length: int) -> Any:
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length),
        AfterValidator(no_control_chars),
    ]


Audience = _line(100)
Tool = _line(50)
Hours = Annotated[int, Field(ge=ADVANCED_HOURS_RANGE[0], le=ADVANCED_HOURS_RANGE[1])]
Features = Annotated[list[_line(100)], Field(max_length=ADVANCED_FEATURES_MAX)]


class AdvancedIn(BaseModel):
    title: Title
    audience: Audience
    tool: Tool
    hours: Hours
    goal: Text = None
    features: Features = []

    def fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in ADVANCED_CONTENT_FIELDS}


class AdvancedPatchIn(PatchModel):
    title: Title | None = None
    audience: Audience | None = None
    tool: Tool | None = None
    hours: Hours | None = None
    goal: Text = None
    features: Features | None = None
    pub: bool | None = None
    active: bool | None = None

    @field_validator("title", "audience", "tool", "hours", "features", "pub", "active")
    @classmethod
    def _content_not_null(cls, value: Any) -> Any:
        return not_null(value)


class AdvancedOut(BaseModel):
    id: str
    title: str
    audience: str
    tool: str
    hours: int
    goal: str | None
    features: list[str]
    pub: bool
    active: bool
    created_at: dt.datetime
