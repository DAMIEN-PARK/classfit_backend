"""인증 입출력 모양."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def no_control_chars(value: str) -> str:
    """NUL·제어 문자는 422 로 막는다(그대로 두면 psycopg DataError → 500)."""
    if _CONTROL.search(value):
        raise ValueError("제어 문자를 쓸 수 없습니다")
    return value


class AdminLoginIn(BaseModel):
    login_id: Annotated[
        str, Field(min_length=1, max_length=64), AfterValidator(no_control_chars)
    ]
    password: str = Field(
        min_length=1, max_length=1024
    )  # 상한: argon2 대조에 거대한 입력을 넣지 않게


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
