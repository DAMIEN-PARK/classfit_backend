"""강의 배정: session 칸 셋(pool_course_id · curriculum_id · instructor_id) · course.curriculum_src_id · session_attachment.origin

- session.pool_course_id(Text) → pool_course · session.curriculum_id(Text) → curriculum · session.instructor_id(BigInteger)
  → instructor 와 색인 ix_session_instructor_id, course.curriculum_src_id(Text) → curriculum. 넷 다 NULL 허용이고
  FK 는 기본 NO ACTION 이다 — 풀 과정·커리큘럼 "삭제" 는 비활성이고(T4 결정 xi) 강사 삭제 끝점은 없다(T5 계획).
- session_attachment.origin(Text NULL) 은 기본 강의안 사본의 원본 owner_kind 다. NULL 은 보통 첨부(T5 결정 xi).
  CHECK origin 이 값 집합을 막는다. server_default 가 없어 기존 행은 전부 NULL(보통 첨부)로 남는다.
- 기존 표에 NULL 허용 칸만 더하므로 행 가드가 없다. lock_timeout 만 둔다(0006 꼴).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

ORIGIN_CHECK = (
    "origin IS NULL"
    " OR origin IN ('pool_course_file', 'capability_file', 'curriculum_file')"
)
# (표, 칸, 타입, 가리키는 표)
REFS = (
    ("session", "pool_course_id", sa.Text(), "pool_course"),
    ("session", "curriculum_id", sa.Text(), "curriculum"),
    ("session", "instructor_id", sa.BigInteger(), "instructor"),
    ("course", "curriculum_src_id", sa.Text(), "curriculum"),
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table, column, type_, referred in REFS:
        op.add_column(table, sa.Column(column, type_, nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_{column}_{referred}"),
            table,
            referred,
            [column],
            ["id"],
        )
    op.create_index(op.f("ix_session_instructor_id"), "session", ["instructor_id"])
    op.add_column("session_attachment", sa.Column("origin", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_session_attachment_origin"), "session_attachment", ORIGIN_CHECK
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_session_attachment_origin"), "session_attachment", type_="check"
    )
    op.drop_column("session_attachment", "origin")
    op.drop_index(op.f("ix_session_instructor_id"), table_name="session")
    for table, column, _, referred in reversed(REFS):
        op.drop_constraint(
            op.f(f"fk_{table}_{column}_{referred}"), table, type_="foreignkey"
        )
        op.drop_column(table, column)
