"""교육 문의 표 inquiry. 0011(T9b).

- 공개 폼 접수 1행이다. Company 연결 없음(r3 338) · 주체 없음 · FK 없음. 요청 주소(IP)는 저장하지 않는다(T9b 결정 vii).
- 영수증 번호는 저장하는 난수다(유일 uq_inquiry_receipt_no, 결정 v). 고치는 끝점이 없어 updated_at 이 없다(MailOutbox 꼴).
  지우기는 scripts.inquiry_gc 한 곳이고 그 행의 outbox(params inquiry_id)도 함께 지운다(결정 xxv).
- 필수는 회사명·담당자·이메일·연락처, 부서·직함·규모·내용은 선택이다(결정 ii). 공백류뿐인 회사명·담당자·내용은 CHECK 가
  막는다(btrim 은 스페이스만 지운다 — 0008 content 꼴). email 은 정규화한 소문자 Text 다(varchar 면 alembic 이 식 색인을
  lower((email)::text) 로 읽는다 — T3 instructor 꼴). 재제출·하루 상한 조회는 식 색인 ix_inquiry_email_lower_created_at 을 탄다.
- 규모 Literal 의 정본은 이 파일이다(schemas 가 들인다 — schemas → models 는 아래 방향). 회사 표(models.diagnosis)의
  5구간과 합치지 않는다(spec A2-6). 라벨은 공개홈 #ct-sz 글자 그대로(outbox 알림 본문이 쓴다).
- 행은 service.inquiries.receive 의 receive_inquiry() 만 만든다(crud.inquiry.insert_inquiry 경유, 단일 진입).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, get_args

from sqlalchemy import CheckConstraint, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin

InquirySize = Literal["under_30", "30_99", "100_299", "300_plus"]
INQUIRY_SIZES: tuple[str, ...] = get_args(InquirySize)
INQUIRY_SIZE_LABELS: dict[str, str] = {
    "under_30": "30명 미만",
    "30_99": "30 ~ 99명",
    "100_299": "100 ~ 299명",
    "300_plus": "300명 이상",
}
COMPANY_NAME_MAX = 100
CONTACT_NAME_MAX = 50
DEPT_TITLE_MAX = 100
MESSAGE_MAX = 5000
PHONE_MAX = 20
WEBSITE_MAX = 1024  # honeypot 칸(저장하지 않는다)

_SIZE_LIST = ", ".join(f"'{s}'" for s in INQUIRY_SIZES)
# (이름, 식) — 0011 의 같은 이름 튜플과 같은 글자
INQUIRY_CHECKS = (
    # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다 — btrim 은 스페이스만 지운다
    ("company_name", "company_name ~ '[^[:space:]]'"),
    ("contact_name", "contact_name ~ '[^[:space:]]'"),
    ("message", "message IS NULL OR message ~ '[^[:space:]]'"),
    ("company_size", f"company_size IS NULL OR company_size IN ({_SIZE_LIST})"),
)


class Inquiry(BigIdMixin, Base):
    __tablename__ = "inquiry"
    __table_args__ = tuple(CheckConstraint(sql, name=n) for n, sql in INQUIRY_CHECKS)

    receipt_no: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_name: Mapped[str] = mapped_column(Text, nullable=False)  # 담당자
    email: Mapped[str] = mapped_column(Text, nullable=False)  # 정규화한 소문자
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    dept_title: Mapped[str | None] = mapped_column(Text)  # 부서 · 직함
    company_size: Mapped[str | None] = mapped_column(Text)  # INQUIRY_SIZES 코드
    message: Mapped[str | None] = mapped_column(Text)
    privacy_agreed_at: Mapped[datetime] = mapped_column(
        nullable=False
    )  # 접수 트랜잭션 now()
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


Index(
    "ix_inquiry_email_lower_created_at",
    func.lower(Inquiry.email),
    Inquiry.created_at,
)
