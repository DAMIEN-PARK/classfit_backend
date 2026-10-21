"""인증 입출력 모양."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AdminLoginIn(BaseModel):
    login_id: str = Field(min_length=1, max_length=64)
    password: str = Field(
        min_length=1, max_length=1024
    )  # 상한: argon2 대조에 거대한 입력을 넣지 않게


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
