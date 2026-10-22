"""입장 입출력 모양(T2b 계획 결정 i·iii·iv·vi). 인증 없는 끝점이라 입력을 좁게 받는다.

- 코드는 글자 그대로 받는다. 정규화(앞뒤 공백·대문자)와 형식 판정(혼동 문자 먼저, 6자가 아닌 길이는 malformed)은
  service.rules.invite 가 한다. CODE_INPUT_MAX 는 입력 크기 상한일 뿐이라 넉넉히 둔다(넘으면 일반 422).
- 이메일은 앞뒤 공백을 지우고 소문자로 바꾼 뒤 254자 · 정규식 ^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$ · 제어 문자 없음을 본다.
  pydantic.EmailStr 은 email-validator 의존성이 필요해 쓰지 않는다.
- 이름은 1~50자, 부서는 0~50자 자유 글자다. 비우면(공백뿐 포함) 안 준 것과 같다. 새 등록에 이름이 없으면 service 가 422 로 막는다.
- 응답에 다른 사람의 개인 칸은 없다. EnterOut.name 은 그 등록의 자기 이름이다.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from classfit.schemas.auth import no_control_chars

EMAIL_MAX = 254
CODE_INPUT_MAX = 256
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

CourseStatus = Literal["prep", "running", "ended"]
EnterState = Literal["active", "preparing", "ended", "expired", "paused", "full"]


def normalize_email(value: str) -> str:
    """앞뒤 공백 제거 + 소문자. 모양이 틀리면 422."""
    email = no_control_chars(value.strip().lower())
    if len(email) > EMAIL_MAX:
        raise ValueError(f"이메일은 {EMAIL_MAX}자까지입니다")
    if not _EMAIL.fullmatch(email):
        raise ValueError("이메일 모양이 아닙니다")
    return email


def _optional_text(limit: int) -> Callable[[str | None], str | None]:
    """앞뒤 공백 제거 · 제어 문자 422 · limit 자까지. 비면 None(안 준 것과 같다)."""

    def check(value: str | None) -> str | None:
        if value is None:
            return None
        text = no_control_chars(value.strip())
        if len(text) > limit:
            raise ValueError(f"{limit}자까지입니다")
        return text or None

    return check


Code = Annotated[str, Field(max_length=CODE_INPUT_MAX)]
Email = Annotated[str, Field(max_length=1024), AfterValidator(normalize_email)]
Name = Annotated[str | None, AfterValidator(_optional_text(50))]


class EnterLookupIn(BaseModel):
    code: Code


class EnterIn(BaseModel):
    code: Code
    email: Email
    name: Name = Field(default=None, max_length=1024)
    dept: Name = Field(default=None, max_length=1024)


class EnterCourseOut(BaseModel):
    """입장 화면의 강의 카드. status 는 오늘 기준 계산값이다."""

    title: str
    start_on: dt.date
    end_on: dt.date
    status: CourseStatus


class EnterLookupOut(BaseModel):
    course: EnterCourseOut
    state: EnterState
    accepts_new: bool  # 새 이메일의 등록을 받는지. 막혀도 기존 등록자는 재입장한다
    notice: str | None  # 준비 중이면 "준비 중인 강의입니다. 시작일 YYYY-MM-DD"


class EnterOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: dt.datetime
    course_id: int
    name: str  # 이 강의 등록의 이름. 재입장은 처음 값이다
    reentered: bool
    notice: str | None
