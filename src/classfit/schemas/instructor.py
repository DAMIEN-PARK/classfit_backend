"""강사 입출력 모양(T3 계획 결정 i·iii·iv·vi·vii·ix·x).

- 이메일은 T2b schemas.enter.Email 하나로 정규화한다(앞뒤 공백 제거 + 소문자 + 254자 + 정규식).
- 가입 본문의 약관 동의 둘은 true 만 받는다. 판본(terms_version)은 서버 설정이 찍는다(결정 iii).
- 글자 칸은 앞뒤 공백을 지우고 제어 문자를 422 로 막는다(psycopg DataError → 500 방지). 비밀번호는 고치지 않는다.
- 소속 org 는 가입에서 필수 키이되 null 을 받는다(null = 무소속). PATCH 는 준 칸만 바꾸고, null 을 받지 않는 칸에 null 이면 422.
- 분야 태그는 이름 목록 1~20개다. 이름 정규화(연속 공백 하나)와 사용 중지 판정은 crud·service 몫이다.
- 응답에 비밀번호 해시·코드 해시는 없다. memo 는 관리자 상세에만, 서류 href 는 강사 본인 응답에만 있다(결정 x).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
)

from classfit.schemas.auth import no_control_chars
from classfit.schemas.enter import Email

InstructorStatus = Literal["pending", "approved", "rejected", "suspended"]

PASSWORD_MIN = 8
PASSWORD_MAX = 1024
TAGS_MAX = 20
CAREER_MAX = 20


def _blank_is_none(value: str | None) -> str | None:
    return value or None


def _text(max_length: int, min_length: int = 1) -> StringConstraints:
    return StringConstraints(
        strip_whitespace=True, min_length=min_length, max_length=max_length
    )


Name = Annotated[str, _text(50), AfterValidator(no_control_chars)]
Phone = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[+0-9\- ]{7,20}$")
]
Org = Annotated[str, _text(100), AfterValidator(no_control_chars)]
Intro = Annotated[
    Annotated[str, _text(200, 0), AfterValidator(no_control_chars)] | None,
    AfterValidator(_blank_is_none),
]
CareerItem = Annotated[str, _text(100), AfterValidator(no_control_chars)]
Career = Annotated[list[CareerItem], Field(max_length=CAREER_MAX)]
TagName = Annotated[str, _text(30), AfterValidator(no_control_chars)]
Tags = Annotated[list[TagName], Field(min_length=1, max_length=TAGS_MAX)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{6}$")]
Password = Annotated[str, Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)]
Reason = Annotated[str, _text(500), AfterValidator(no_control_chars)]
Memo = Annotated[
    Annotated[str, _text(2000, 0), AfterValidator(no_control_chars)] | None,
    AfterValidator(_blank_is_none),
]


class EmailCodeRequestIn(BaseModel):
    email: Email


class EmailCodeRequestOut(BaseModel):
    """받은 이메일(정규화 뒤)만 돌려준다. 코드는 응답·outbox 어디에도 없다."""

    email: str


class InstructorSignupIn(BaseModel):
    email: Email
    code: Code
    password: Password
    name: Name
    phone: Phone
    org: Org | None  # 필수 키. null = 무소속
    intro: Intro = None
    career: Career = []
    tags: Tags
    terms_agreed: Literal[True]
    privacy_agreed: Literal[True]


class InstructorLoginIn(BaseModel):
    email: Email
    # 상한: argon2 대조에 거대한 입력을 넣지 않게. 최소 길이는 보지 않는다(틀린 비밀번호와 같은 401)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)


class InstructorPatchIn(BaseModel):
    """준 칸만 바꾼다. org·intro 는 null 로 비울 수 있고, 나머지는 null 이면 422."""

    name: Name | None = None
    phone: Phone | None = None
    org: Org | None = None
    intro: Intro = None
    career: Career | None = None
    tags: Tags | None = None

    @field_validator("name", "phone", "career", "tags")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        # 기본값(None)은 검증하지 않으므로 이 검사는 손님이 null 을 직접 보냈을 때만 돈다
        if value is None:
            raise ValueError("null 일 수 없습니다")
        return value

    def changes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class InstructorTagOut(BaseModel):
    id: int
    name: str
    group: str | None


class DocumentAdminOut(BaseModel):
    """서류 한 종류. 미제출이면 submitted_at·size 가 null 이다. 관리자 응답에는 href 가 없다(결정 x)."""

    type_id: str
    name: str
    required: bool
    submitted_at: dt.datetime | None
    size: int | None


class DocumentOut(DocumentAdminOut):
    """강사 본인이 자기 서류를 여는 주소. 미제출이면 null."""

    href: str | None


class InstructorMeOut(BaseModel):
    id: int
    email: str
    name: str
    phone: str
    org: str | None
    intro: str | None
    career: list[str]
    status: InstructorStatus
    reject_reason: str | None
    terms_version: str
    terms_agreed_at: dt.datetime
    tags: list[InstructorTagOut]
    documents: list[DocumentOut]
    created_at: dt.datetime


class InstructorAdminItemOut(BaseModel):
    id: int
    email: str
    name: str
    phone: str
    org: str | None
    status: InstructorStatus
    applied_at: dt.datetime  # 신청일 = 가입 시각
    tags: list[InstructorTagOut]
    documents_submitted: int
    documents_required: int


class InstructorAdminOut(InstructorAdminItemOut):
    intro: str | None
    career: list[str]
    reject_reason: str | None
    memo: str | None
    documents: list[DocumentAdminOut]


class RejectIn(BaseModel):
    reason: Reason


class MemoIn(BaseModel):
    memo: Memo  # 필수 키. null·빈 글자는 메모를 지운다
