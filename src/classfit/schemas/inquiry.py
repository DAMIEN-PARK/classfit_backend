"""교육 문의 입출력 모양(T9b 계획 결정 i·ii·iii·iv·xx). 공개(인증 없음) 끝점이라 입력을 좁게 받는다(T2b enter 꼴).

- 필수 넷은 회사명·담당자·이메일·연락처다(공개홈 P6 · r1 — r3 323 은 넷을 열거하지 않는다, 결정 ii). 부서·직함·규모·내용은
  선택이고 다듬어 비면 None 이다. 개인정보 동의 privacy_agreed 는 true 만 받는다. 모르는 키는 422 extra_forbidden 이다.
- 이메일은 T2b Email(앞뒤 공백 제거 + 소문자 + 254자 + 정규식)이다. 연락처는 문의 전용 InquiryPhone: 허용 글자 0-9 + - ( )
  공백 · 20자까지 · 숫자만 세어 9~15자(공개홈 :1368 의 9자 + 국제 번호 상한 15 — T3 Phone 은 숫자 0개도 통과한다, 결정 xx).
- 회사명 1~100 · 담당자 1~50 · 부서·직함 100 은 앞뒤 공백을 지우고 제어 문자를 422 로 막는다. 내용은 5000자까지이고 NUL 만
  막는다(줄바꿈·탭 허용 — T7 Note 꼴). 칸 상한·규모 Literal 의 정본은 models.inquiry 다(여기는 들이기만 한다 — 계약 ①
  아래 방향). _optional_text(T2b)·_no_nul_or_none(T7)은 같은 schemas 층의 비공개 이름이지만 그대로 들인다(결정 xx).
- honeypot 칸 website 는 모양 검사 없이 1024자까지만 받고 저장하지 않는다(결정 iv). service 를 import 하지 않는다 — 끝점이
  InquiryFields(**body.model_dump(exclude={"privacy_agreed", "website"})) 로 바꾼다.
- 응답에는 개인 칸이 없다(영수증 번호 · 접수 시각뿐 — 새 접수 · 재제출 · honeypot 이 같은 모양, 결정 i).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from classfit.models.inquiry import (
    COMPANY_NAME_MAX,
    CONTACT_NAME_MAX,
    DEPT_TITLE_MAX,
    MESSAGE_MAX,
    PHONE_MAX,
    WEBSITE_MAX,
    InquirySize,
)
from classfit.schemas.auth import no_control_chars
from classfit.schemas.enter import Email, _optional_text
from classfit.schemas.record import _no_nul_or_none

PHONE_DIGITS_MIN = 9
PHONE_DIGITS_MAX = 15
_PHONE = re.compile(r"[0-9+\-() ]*")


def _inquiry_phone(value: str) -> str:
    """앞뒤 공백 제거 → 허용 글자 · PHONE_MAX 자 · 숫자 9~15자. 아니면 422 value_error."""
    phone = value.strip()
    if len(phone) > PHONE_MAX or not _PHONE.fullmatch(phone):
        raise ValueError(
            f"연락처는 숫자 · + · - · 괄호 · 공백으로 {PHONE_MAX}자까지입니다"
        )
    digits = sum(ch.isdigit() for ch in phone)
    if not PHONE_DIGITS_MIN <= digits <= PHONE_DIGITS_MAX:
        raise ValueError(
            f"연락처의 숫자는 {PHONE_DIGITS_MIN}~{PHONE_DIGITS_MAX}자입니다"
        )
    return phone


CompanyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=COMPANY_NAME_MAX),
    AfterValidator(no_control_chars),
]
ContactName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=CONTACT_NAME_MAX),
    AfterValidator(no_control_chars),
]
InquiryPhone = Annotated[str, AfterValidator(_inquiry_phone)]
DeptTitle = Annotated[str | None, AfterValidator(_optional_text(DEPT_TITLE_MAX))]
# 내용: T7 Note 와 같은 strip 꼴, 다듬어 비면 None
Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=MESSAGE_MAX),
    AfterValidator(_no_nul_or_none),
]
Website = Annotated[str, Field(max_length=WEBSITE_MAX)]


class InquiryIn(BaseModel):
    """POST /v1/inquiries 본문(공개홈 P6 폼 칸 일곱 + 동의 + honeypot)."""

    model_config = ConfigDict(extra="forbid")

    company_name: CompanyName
    contact_name: ContactName
    email: Email
    phone: InquiryPhone
    dept_title: DeptTitle = None
    company_size: InquirySize | None = None
    message: Message | None = None
    privacy_agreed: Literal[True]
    website: Website | None = (
        None  # honeypot — 사람이 쓰는 폼에서는 숨은 칸이라 비어 있다
    )


class InquiryReceiptOut(BaseModel):
    """접수 영수증. 새 접수 · 1분 안 재제출(같은 영수증) · honeypot(저장하지 않는 난수)이 같은 모양이다."""

    receipt_no: str
    received_at: dt.datetime
