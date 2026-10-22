"""강의 개설: course · course_day · section · session · invite_code + FK auth_session.course_id → course

- 상태 열은 Text + CHECK(Design 5절 12). course.status 는 prep·running·ended, invite_code.status 는 active·paused·replaced.
- invite_code.code 는 전 행 유일, 강의당 산 코드는 부분 유일 색인 uq_invite_code_course_live 로 하나.
- 아래 표는 강의를 지우면 CASCADE 다. auth_session.course_id FK 는 기본 NO ACTION 이다.
- FK 를 걸기 전에 lock_timeout 과 "course_id 가 있는 auth_session 행" 가드를 둔다(백엔드 안내서 §3.2).
  새 course 표는 비어 있으니 그런 행이 하나라도 있으면 FK 가 깨진다. 멈추고 행 수를 알린다.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

GUARD = """
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM auth_session WHERE course_id IS NOT NULL;
  IF n > 0 THEN
    RAISE EXCEPTION '0003 중단 - course_id 가 있는 auth_session 행 % 개. 그 행을 지운 뒤 다시 돌린다 (T1 계획 이웃 흐름의 정리 줄)', n;
  END IF;
END $$
"""


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _course_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["course_id"],
        ["course.id"],
        name=op.f(f"fk_{table}_course_id_course"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "course",
        _id(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("course_type", sa.Text(), nullable=True),
        sa.Column("cohort", sa.Text(), nullable=True),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("hours_per_person", sa.Integer(), nullable=False),
        sa.Column("start_on", sa.Date(), nullable=False),
        sa.Column("end_on", sa.Date(), nullable=False),
        sa.Column(
            "slot_min", sa.Integer(), server_default=sa.text("50"), nullable=False
        ),
        sa.Column(
            "break_min", sa.Integer(), server_default=sa.text("10"), nullable=False
        ),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("notice", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'prep'"), nullable=False
        ),
        sa.Column(
            "status_manual",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "status IN ('prep', 'running', 'ended')", name=op.f("ck_course_status")
        ),
        sa.CheckConstraint("start_on <= end_on", name=op.f("ck_course_period")),
        sa.CheckConstraint(
            "hours_per_person >= 0", name=op.f("ck_course_hours_per_person")
        ),
        sa.CheckConstraint("slot_min > 0", name=op.f("ck_course_slot_min")),
        sa.CheckConstraint("break_min >= 0", name=op.f("ck_course_break_min")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course")),
    )
    op.create_table(
        "course_day",
        _id(),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("day_no", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("lunch_start", sa.Time(), nullable=True),
        sa.Column("lunch_end", sa.Time(), nullable=True),
        sa.CheckConstraint("day_no >= 1", name=op.f("ck_course_day_day_no")),
        sa.CheckConstraint("start_time < end_time", name=op.f("ck_course_day_hours")),
        sa.CheckConstraint(
            "(lunch_start IS NULL) = (lunch_end IS NULL)",
            name=op.f("ck_course_day_lunch_pair"),
        ),
        sa.CheckConstraint(
            "lunch_start IS NULL OR lunch_start < lunch_end",
            name=op.f("ck_course_day_lunch_order"),
        ),
        _course_fk("course_day"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_day")),
        sa.UniqueConstraint(
            "course_id", "day_no", name="uq_course_day_course_id_day_no"
        ),
    )
    op.create_table(
        "section",
        _id(),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        _course_fk("section"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section")),
    )
    op.create_index(op.f("ix_section_course_id"), "section", ["course_id"])
    op.create_table(
        "session",
        _id(),
        sa.Column("section_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("day_no", sa.Integer(), nullable=True),
        sa.Column("slot", sa.Integer(), nullable=True),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("time_start", sa.Time(), nullable=True),
        sa.Column("time_end", sa.Time(), nullable=True),
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "is_open", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.CheckConstraint(
            "day_no IS NOT NULL OR slot IS NULL", name=op.f("ck_session_slot_needs_day")
        ),
        sa.CheckConstraint("slot IS NULL OR slot >= 1", name=op.f("ck_session_slot")),
        sa.CheckConstraint(
            "minutes IS NULL OR minutes > 0", name=op.f("ck_session_minutes")
        ),
        sa.CheckConstraint(
            "(time_start IS NULL) = (time_end IS NULL)",
            name=op.f("ck_session_time_pair"),
        ),
        sa.CheckConstraint(
            "time_start IS NULL OR time_start < time_end",
            name=op.f("ck_session_time_order"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["section.id"],
            name=op.f("fk_session_section_id_section"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session")),
    )
    op.create_index(op.f("ix_session_section_id"), "session", ["section_id"])
    op.create_table(
        "invite_code",
        _id(),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("max_seats", sa.Integer(), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'replaced')",
            name=op.f("ck_invite_code_status"),
        ),
        sa.CheckConstraint(
            "max_seats IS NULL OR max_seats > 0", name=op.f("ck_invite_code_max_seats")
        ),
        _course_fk("invite_code"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invite_code")),
        sa.UniqueConstraint("code", name=op.f("uq_invite_code_code")),
    )
    op.create_index(op.f("ix_invite_code_course_id"), "invite_code", ["course_id"])
    op.create_index(
        "uq_invite_code_course_live",
        "invite_code",
        ["course_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'replaced'"),
    )

    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(GUARD)
    op.create_foreign_key(
        op.f("fk_auth_session_course_id_course"),
        "auth_session",
        "course",
        ["course_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_auth_session_course_id_course"), "auth_session", type_="foreignkey"
    )
    op.drop_index("uq_invite_code_course_live", table_name="invite_code")
    op.drop_index(op.f("ix_invite_code_course_id"), table_name="invite_code")
    op.drop_table("invite_code")
    op.drop_index(op.f("ix_session_section_id"), table_name="session")
    op.drop_table("session")
    op.drop_index(op.f("ix_section_course_id"), table_name="section")
    op.drop_table("section")
    op.drop_table("course_day")
    op.drop_table("course")
