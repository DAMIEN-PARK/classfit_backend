"""공통 바닥: admin_account · auth_session · auth_attempt · email_verification · mail_outbox · stored_file

- 상태·종류 열은 Text. auth_session 은 principal_type CHECK 와 learner ⇔ course_id CHECK(ADR-002).
  FK auth_session.course_id → course 는 0003 이 더한다.
- stored_file 은 다형 참조라 FK 가 없다.
- email_verification 은 해시 칸만 앞당긴다(T1 착수 조건 (a)). 강사 연결 칸은 0005 가 더한다.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "admin_account",
        _id(),
        sa.Column("login_id", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_account")),
        sa.UniqueConstraint("login_id", name=op.f("uq_admin_account_login_id")),
    )
    op.create_table(
        "auth_session",
        _id(),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("principal_type", sa.Text(), nullable=False),
        sa.Column("principal_id", sa.BigInteger(), nullable=False),
        sa.Column("course_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _now("created_at"),
        sa.CheckConstraint(
            "principal_type IN ('admin', 'instructor', 'learner')",
            name=op.f("ck_auth_session_principal_type"),
        ),
        sa.CheckConstraint(
            "(principal_type = 'learner') = (course_id IS NOT NULL)",
            name=op.f("ck_auth_session_learner_course"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_session_token_hash")),
    )
    op.create_table(
        "auth_attempt",
        _id(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("subject_hash", sa.Text(), nullable=False),
        sa.Column("client", sa.Text(), nullable=False),
        _now("at"),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_attempt")),
    )
    op.create_index(
        "ix_auth_attempt_window",
        "auth_attempt",
        ["kind", "subject_hash", "client", "at"],
    )
    op.create_table(
        "email_verification",
        _id(),
        sa.Column("code_hash", sa.Text(), nullable=True),
        sa.Column("tries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_verification")),
    )
    op.create_table(
        "mail_outbox",
        _id(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("to", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_outbox")),
    )
    op.create_table(
        "stored_file",
        _id(),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("owner_kind", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_file")),
        sa.UniqueConstraint("key", name=op.f("uq_stored_file_key")),
    )
    op.create_index(op.f("ix_stored_file_sha256"), "stored_file", ["sha256"])


def downgrade() -> None:
    op.drop_index(op.f("ix_stored_file_sha256"), table_name="stored_file")
    op.drop_table("stored_file")
    op.drop_table("mail_outbox")
    op.drop_table("email_verification")
    op.drop_index("ix_auth_attempt_window", table_name="auth_attempt")
    op.drop_table("auth_attempt")
    op.drop_table("auth_session")
    op.drop_table("admin_account")
