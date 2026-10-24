"""AX 진단: company · diagnosis · diag_link · course.company_id

- company 는 회사명·담당자(공백류뿐 금지) · 연락처 · 업종(자유 글자) · 규모 코드 5구간 · 부서 text[](20개까지) · 메모.
- diagnosis 는 회사(FK CASCADE — 파일이 없다) · 회차 번호(회사 안에서 유일, ≥ 1) · 사전/사후 · 방문/링크 · draft/review/
  final · 진단일(링크면 제출일) · 기록자 표기 · 응답자 JSONB(링크 회차만) · 답·증빙·현장·역량 JSONB(기본 {}) · 권장 구성
  JSONB · 확정 시각·확정자(final 일 때만, 둘이 같이).
- diag_link 는 회사(FK CASCADE) · 토큰(32자 token_urlsafe 글자, 유일) · 사전/사후 · 받는 분 · 발급일 ≤ 만료일 · open/
  submitted/revoked(만료는 계산) · 제출·회수 시각 · 제출이 만든 회차(FK NO ACTION 유일, submitted 일 때만). 회사당 open 은
  부분 유일 색인 uq_diag_link_company_open WHERE status = 'open' 으로 하나다. 색인 ix_diag_link_company_id.
- course.company_id(BIGINT NULL) → company ON DELETE SET NULL 과 색인 ix_course_company_id(0007 의 ALTER 꼴).
- 기존 표에는 NULL 허용 칸만 더하므로 행 가드가 없다. lock_timeout 만 둔다(0009 꼴).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# (이름, 식) — models/diagnosis.py 의 같은 이름 튜플과 같은 글자
COMPANY_CHECKS = (
    # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다 — btrim 은 스페이스만 지운다
    ("name", "name ~ '[^[:space:]]'"),
    ("contact", "contact ~ '[^[:space:]]'"),
    ("size", "size IN ('lt10', 's10_49', 's50_99', 's100_299', 'ge300')"),
    ("depts", "coalesce(array_length(depts, 1), 0) <= 20"),
)
DIAGNOSIS_CHECKS = (
    ("round_no", "round_no >= 1"),
    ("phase", "phase IN ('pre', 'post')"),
    ("mode", "mode IN ('visit', 'link')"),
    ("status", "status IN ('draft', 'review', 'final')"),
    ("respondent", "mode = 'link' OR respondent IS NULL"),
    ("finalized_status", "(status = 'final') = (finalized_at IS NOT NULL)"),
    ("finalized_pair", "(finalized_at IS NULL) = (finalized_by_id IS NULL)"),
)
LINK_CHECKS = (
    ("token", "token ~ '^[A-Za-z0-9_-]{32}$'"),
    ("phase", "phase IN ('pre', 'post')"),
    ("period", "issued_on <= expires_on"),
    ("status", "status IN ('open', 'submitted', 'revoked')"),
    ("submitted_at", "status <> 'submitted' OR submitted_at IS NOT NULL"),
    ("revoked_at", "status <> 'revoked' OR revoked_at IS NOT NULL"),
    ("submitted_history", "submitted_at IS NULL OR status IN ('submitted', 'revoked')"),
    ("diagnosis_submitted", "diagnosis_id IS NULL OR status = 'submitted'"),
)
JSON_FIELDS = ("answers", "evidence", "field", "matrix")


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _checks(
    table: str, checks: tuple[tuple[str, str], ...]
) -> list[sa.CheckConstraint]:
    return [sa.CheckConstraint(sql, name=op.f(f"ck_{table}_{n}")) for n, sql in checks]


def _company() -> None:
    op.create_table(
        "company",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("contact", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("size", sa.Text(), nullable=True),
        sa.Column(
            "depts",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("memo", sa.Text(), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        *_checks("company", COMPANY_CHECKS),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company")),
    )


def _diagnosis() -> None:
    op.create_table(
        "diagnosis",
        _id(),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("diagnosed_on", sa.Date(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("respondent", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *(
            sa.Column(
                name,
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            )
            for name in JSON_FIELDS
        ),
        sa.Column("reco", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by_id", sa.BigInteger(), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        *_checks("diagnosis", DIAGNOSIS_CHECKS),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["company.id"],
            name=op.f("fk_diagnosis_company_id_company"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis")),
        sa.UniqueConstraint(
            "company_id", "round_no", name="uq_diagnosis_company_id_round_no"
        ),
    )


def _diag_link() -> None:
    op.create_table(
        "diag_link",
        _id(),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnosis_id", sa.BigInteger(), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        *_checks("diag_link", LINK_CHECKS),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["company.id"],
            name=op.f("fk_diag_link_company_id_company"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["diagnosis_id"],
            ["diagnosis.id"],
            name=op.f("fk_diag_link_diagnosis_id_diagnosis"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diag_link")),
        sa.UniqueConstraint("token", name=op.f("uq_diag_link_token")),
        sa.UniqueConstraint("diagnosis_id", name=op.f("uq_diag_link_diagnosis_id")),
    )
    op.create_index(op.f("ix_diag_link_company_id"), "diag_link", ["company_id"])
    op.create_index(
        "uq_diag_link_company_open",
        "diag_link",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    _company()
    _diagnosis()
    _diag_link()
    op.add_column("course", sa.Column("company_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_course_company_id_company"),
        "course",
        "company",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_course_company_id"), "course", ["company_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_course_company_id"), table_name="course")
    op.drop_constraint(
        op.f("fk_course_company_id_company"), "course", type_="foreignkey"
    )
    op.drop_column("course", "company_id")
    op.drop_index("uq_diag_link_company_open", table_name="diag_link")
    op.drop_index(op.f("ix_diag_link_company_id"), table_name="diag_link")
    op.drop_table("diag_link")
    op.drop_table("diagnosis")
    op.drop_table("company")
