"""교육 문의: inquiry

- 공개 폼 접수 1행. 영수증 번호(저장 난수, 유일 uq_inquiry_receipt_no) · 회사명·담당자(공백류뿐 금지) · 이메일(정규화한
  소문자) · 연락처 · 부서·직함 · 규모 코드 4구간 · 문의 내용(NULL 허용, 공백류뿐 금지) · 동의 시각 · 접수 시각.
- FK 없음(Company 연결 없음 · 주체 없음) · IP 칸 없음 · updated_at 없음(고치는 끝점이 없다 — T9b 결정 v·vii).
- 식 색인 ix_inquiry_email_lower_created_at(lower(email), created_at) — 재제출(1분)·이메일당 하루 상한 조회.
- 기존 표를 바꾸지 않으므로 행 가드가 없다. lock_timeout 만 둔다(0008 꼴).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SIZES = "'under_30', '30_99', '100_299', '300_plus'"  # models.inquiry.INQUIRY_SIZES
# (이름, 식) — models/inquiry.py 의 INQUIRY_CHECKS 와 같은 글자
INQUIRY_CHECKS = (
    # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다 — btrim 은 스페이스만 지운다
    ("company_name", "company_name ~ '[^[:space:]]'"),
    ("contact_name", "contact_name ~ '[^[:space:]]'"),
    ("message", "message IS NULL OR message ~ '[^[:space:]]'"),
    ("company_size", f"company_size IS NULL OR company_size IN ({SIZES})"),
)
EMAIL_INDEX = "ix_inquiry_email_lower_created_at"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.create_table(
        "inquiry",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("receipt_no", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("dept_title", sa.Text(), nullable=True),
        sa.Column("company_size", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("privacy_agreed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *(
            sa.CheckConstraint(sql, name=op.f(f"ck_inquiry_{name}"))
            for name, sql in INQUIRY_CHECKS
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inquiry")),
        sa.UniqueConstraint("receipt_no", name=op.f("uq_inquiry_receipt_no")),
    )
    op.create_index(EMAIL_INDEX, "inquiry", [sa.text("lower(email)"), "created_at"])


def downgrade() -> None:
    op.drop_index(EMAIL_INDEX, table_name="inquiry")
    op.drop_table("inquiry")
