"""초대코드 입출력 모양. state 는 오늘 기준 계산값이다(service.rules.status.code_state_at)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

CodeStatus = Literal["active", "paused", "replaced"]
CodeState = Literal["active", "paused", "replaced", "stopped", "expired"]


class InviteCodeOut(BaseModel):
    code: str
    status: CodeStatus
    state: CodeState
    expires_on: dt.date
    max_seats: int | None
    issued_at: dt.datetime


class InviteCodePatchIn(BaseModel):
    """준 칸만 바꾼다. max_seats 에 null 을 주면 정원을 없앤다. expires_on 은 null 을 받지 않는다."""

    expires_on: dt.date | None = None
    max_seats: int | None = Field(default=None, ge=1, le=100_000)

    @model_validator(mode="after")
    def _expires_not_null(self) -> InviteCodePatchIn:
        if "expires_on" in self.model_fields_set and self.expires_on is None:
            raise ValueError("expires_on 은 null 일 수 없습니다")
        return self

    def changes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class NoticeOut(BaseModel):
    text: str
