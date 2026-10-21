"""관리자 계정 입출력 모양. 응답에 비밀번호 해시를 두지 않는다."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from classfit.schemas.auth import no_control_chars

# 앞뒤 공백 제거 뒤 길이를 잰다. 소문자 정규화는 crud.admin 한 곳이다
LoginId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=64),
    AfterValidator(no_control_chars),
]


class AdminCreateIn(BaseModel):
    login_id: LoginId
    password: str = Field(min_length=12, max_length=1024)


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login_id: str
    created_at: datetime
