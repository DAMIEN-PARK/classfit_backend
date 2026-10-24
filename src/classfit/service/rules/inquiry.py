"""교육 문의 규칙(T9b 결정 iv·v·xxiv): 접수 칸 · 영수증 모양 · honeypot 판정 · 창 상수. 순수 함수다.

- 영수증 번호는 행에 저장하는 난수다: 초대코드 알파벳(32자, 0·O·1·I 없음 — rules.invite) 10자, 경우의 수 32¹⁰.
  표에 유일이고, 겹치면(23505) service 가 새 난수로 RECEIPT_TRIES 번까지 넣어 본 뒤 409 다(결정 v).
- 재제출 창 DUPLICATE_WINDOW(1분, r3 139)와 이메일당 하루 상한 창 DAILY_WINDOW(24시간)는 crud 가 SQL now() 기준으로 쓴다.
- 규모 4구간의 정본은 models.inquiry 다(schemas 가 들인다 — 결정 iii). 여기 두지 않는다.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from classfit.service.rules.invite import INVITE_ALPHABET

RECEIPT_LENGTH = 10
RECEIPT_TRIES = 3  # 영수증 겹침(23505) 때 새 난수로 넣어 보는 횟수, 넘으면 409
DUPLICATE_WINDOW = timedelta(minutes=1)  # 같은 이메일 + 같은 내용이면 같은 영수증
DAILY_WINDOW = timedelta(hours=24)  # 이메일당 상한(INQUIRY_DAILY_MAX)을 세는 창


@dataclass(frozen=True)
class InquiryFields:
    """접수 칸 — 스키마가 다듬은 값이다. email 은 정규화한 소문자, 선택 칸은 비면 None."""

    company_name: str
    contact_name: str
    email: str
    phone: str
    dept_title: str | None
    company_size: str | None
    message: str | None


def new_receipt_no() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(RECEIPT_LENGTH))


def is_honeypot(value: str | None) -> bool:
    """숨은 칸(website)을 채운 요청은 봇이다 — 앞뒤 공백을 지우고도 글자가 남으면 참."""
    return value is not None and bool(value.strip())
