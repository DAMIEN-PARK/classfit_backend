"""입장·포털: learner · enrollment · session_attachment

- learner 는 이메일만 둔다(이름 없음, ADR-002 결정 2). 같은 이메일은 식 유일 색인 uq_learner_email_lower = lower(email).
- enrollment 는 (course_id, learner_id) 유일, 이름 1~50자 CHECK. course·learner FK 는 기본 NO ACTION 이다.
- session_attachment 의 kind 는 5종 CHECK, 대상 CHECK target(link ⇔ url 있음 ∧ link 면 file_id 없음).
  session_id → session · file_id → stored_file(유일) FK 는 기본 NO ACTION 이다. 지우는 쪽은 service 가 맡는다.
- 표를 만들기 전에 lock_timeout 과 "수강생 auth_session 행" 가드를 둔다(백엔드 안내서 §3.2).
  learner 표가 없던 때의 수강생 세션(T1·T2a 이웃 흐름 probe 잔여)이 남으면 그 principal_id 가
  새 learner id 와 겹쳐 남의 세션이 된다. 멈추고 행 수를 알린다.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

GUARD = """
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM auth_session WHERE principal_type = 'learner';
  IF n > 0 THEN
    RAISE EXCEPTION '0004 중단 - learner 표가 없던 때의 수강생 auth_session 행 % 개. 그 행을 지운 뒤 다시 돌린다 (T2a 계획 이웃 흐름의 정리 줄)', n;
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


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(GUARD)

    op.create_table(
        "learner",
        _id(),
        sa.Column("email", sa.Text(), nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learner")),
    )
    op.create_index(
        "uq_learner_email_lower", "learner", [sa.text("lower(email)")], unique=True
    )
    op.create_table(
        "enrollment",
        _id(),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("learner_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("dept", sa.Text(), nullable=True),
        _now("created_at"),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 50", name=op.f("ck_enrollment_name")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["course.id"], name=op.f("fk_enrollment_course_id_course")
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learner.id"],
            name=op.f("fk_enrollment_learner_id_learner"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollment")),
        sa.UniqueConstraint(
            "course_id", "learner_id", name="uq_enrollment_course_id_learner_id"
        ),
    )
    op.create_table(
        "session_attachment",
        _id(),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "kind IN ('pdf', 'office', 'html', 'link', 'image')",
            name=op.f("ck_session_attachment_kind"),
        ),
        sa.CheckConstraint(
            "((kind = 'link') = (url IS NOT NULL))"
            " AND (kind <> 'link' OR file_id IS NULL)",
            name=op.f("ck_session_attachment_target"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session.id"],
            name=op.f("fk_session_attachment_session_id_session"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["stored_file.id"],
            name=op.f("fk_session_attachment_file_id_stored_file"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_attachment")),
        sa.UniqueConstraint("file_id", name=op.f("uq_session_attachment_file_id")),
    )
    op.create_index(
        "ix_session_attachment_session_id_sort_id",
        "session_attachment",
        ["session_id", "sort", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_attachment_session_id_sort_id", table_name="session_attachment"
    )
    op.drop_table("session_attachment")
    op.drop_table("enrollment")
    op.drop_index("uq_learner_email_lower", table_name="learner")
    op.drop_table("learner")
