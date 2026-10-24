"""과정 풀: pool_course · pool_course_file · capability · capability_file · curriculum · curriculum_slot · curriculum_file · advanced_course + 시퀀스 pool_id_seq

- pool_course 는 Text id(ax-… · ax-custom-<n> · own-<강사 id>-<n>), source ax·own CHECK, 소유 강사는 own 일 때만(CHECK owner),
  직무군 ARRAY(Text) cardinality ≥ 1, 난이도 하·중·상, 플래그 셋 active·pub·reviewed 와 reviewed_at(T4 결정 v·vi).
- curriculum 은 Text id(cur-<강사 id>-<n>), 일수 1~30, 시작 < 끝, 차시 curriculum_slot 은 (커리큘럼, 일, 교시) 유일 · CASCADE.
- 파일 표 셋은 T2b session_attachment 와 같은 kind 5종 · 대상 CHECK target · file_id 유일. FK 는 차시만 CASCADE,
  나머지는 기본 NO ACTION 이다(지우는 쪽은 crud 가 파일 행 → stored_file 행 순서로 맡는다, 결정 x·xi).
- advanced_course 는 Text id(adv-<n>), hours > 0, features ≤ 5. 시드는 넣지 않는다(결정 xvii).
- 시퀀스 pool_id_seq 하나가 관리자·강사가 만드는 id 의 번호를 낸다(결정 xiii). 모델 밖이라 alembic check 비교 대상이 아니다.
- 기존 표를 바꾸지 않으므로 행 가드가 없다. lock_timeout 만 둔다(0004 꼴).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SEQUENCE = "pool_id_seq"
TITLE_CHECK = "length(btrim(title)) BETWEEN 1 AND 200"
DIFFICULTY_CHECK = "difficulty IN ('하', '중', '상')"
JOB_GROUPS_CHECK = "cardinality(job_groups) >= 1"
FILE_TABLES = (
    ("pool_course_file", "pool_course_id", sa.Text(), "pool_course"),
    ("capability_file", "capability_id", sa.BigInteger(), "capability"),
    ("curriculum_file", "curriculum_id", sa.Text(), "curriculum"),
)


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _flag(name: str, default: str) -> sa.Column:
    return sa.Column(
        name, sa.Boolean(), server_default=sa.text(default), nullable=False
    )


def _text_array(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.ARRAY(sa.Text()),
        server_default=sa.text("'{}'::text[]"),
        nullable=False,
    )


def _flags() -> list[sa.Column]:
    """active·pub·reviewed·reviewed_at·created_at·updated_at(풀 과정·커리큘럼 공통)."""
    return [
        _flag("active", "true"),
        _flag("pub", "false"),
        _flag("reviewed", "false"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        _now("created_at"),
        _now("updated_at"),
    ]


def _pool_course() -> None:
    op.create_table(
        "pool_course",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("owner_instructor_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("job_groups", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("difficulty", sa.Text(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("material", sa.Text(), nullable=True),
        _text_array("theory"),
        _text_array("practice"),
        sa.Column(
            "schedule",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        *_flags(),
        sa.CheckConstraint(
            "source IN ('ax', 'own')", name=op.f("ck_pool_course_source")
        ),
        sa.CheckConstraint(
            "(source = 'own') = (owner_instructor_id IS NOT NULL)",
            name=op.f("ck_pool_course_owner"),
        ),
        sa.CheckConstraint(TITLE_CHECK, name=op.f("ck_pool_course_title")),
        sa.CheckConstraint(JOB_GROUPS_CHECK, name=op.f("ck_pool_course_job_groups")),
        sa.CheckConstraint(DIFFICULTY_CHECK, name=op.f("ck_pool_course_difficulty")),
        sa.CheckConstraint("minutes > 0", name=op.f("ck_pool_course_minutes")),
        sa.ForeignKeyConstraint(
            ["owner_instructor_id"],
            ["instructor.id"],
            name=op.f("fk_pool_course_owner_instructor_id_instructor"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pool_course")),
    )
    op.create_index("ix_pool_course_source_active", "pool_course", ["source", "active"])
    op.create_index(
        op.f("ix_pool_course_owner_instructor_id"),
        "pool_course",
        ["owner_instructor_id"],
    )


def _capability() -> None:
    op.create_table(
        "capability",
        _id(),
        sa.Column("instructor_id", sa.BigInteger(), nullable=False),
        sa.Column("pool_course_id", sa.Text(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["instructor.id"],
            name=op.f("fk_capability_instructor_id_instructor"),
        ),
        sa.ForeignKeyConstraint(
            ["pool_course_id"],
            ["pool_course.id"],
            name=op.f("fk_capability_pool_course_id_pool_course"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capability")),
        sa.UniqueConstraint(
            "instructor_id",
            "pool_course_id",
            name="uq_capability_instructor_id_pool_course_id",
        ),
    )
    op.create_index("ix_capability_pool_course_id", "capability", ["pool_course_id"])


def _curriculum() -> None:
    op.create_table(
        "curriculum",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("instructor_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("job_groups", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("difficulty", sa.Text(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("slot_min", sa.Integer(), nullable=False),
        sa.Column("break_min", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        *_flags(),
        sa.CheckConstraint(TITLE_CHECK, name=op.f("ck_curriculum_title")),
        sa.CheckConstraint(JOB_GROUPS_CHECK, name=op.f("ck_curriculum_job_groups")),
        sa.CheckConstraint(DIFFICULTY_CHECK, name=op.f("ck_curriculum_difficulty")),
        sa.CheckConstraint("days BETWEEN 1 AND 30", name=op.f("ck_curriculum_days")),
        sa.CheckConstraint("start_time < end_time", name=op.f("ck_curriculum_hours")),
        sa.CheckConstraint("slot_min > 0", name=op.f("ck_curriculum_slot_min")),
        sa.CheckConstraint("break_min >= 0", name=op.f("ck_curriculum_break_min")),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["instructor.id"],
            name=op.f("fk_curriculum_instructor_id_instructor"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum")),
    )
    op.create_index(
        op.f("ix_curriculum_instructor_id"), "curriculum", ["instructor_id"]
    )
    op.create_table(
        "curriculum_slot",
        _id(),
        sa.Column("curriculum_id", sa.Text(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.CheckConstraint("day >= 1", name=op.f("ck_curriculum_slot_day")),
        sa.CheckConstraint("slot >= 1", name=op.f("ck_curriculum_slot_slot")),
        sa.CheckConstraint(TITLE_CHECK, name=op.f("ck_curriculum_slot_title")),
        sa.ForeignKeyConstraint(
            ["curriculum_id"],
            ["curriculum.id"],
            name=op.f("fk_curriculum_slot_curriculum_id_curriculum"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_slot")),
        sa.UniqueConstraint(
            "curriculum_id",
            "day",
            "slot",
            name="uq_curriculum_slot_curriculum_id_day_slot",
        ),
    )


def _file_table(
    name: str, owner_fk: str, owner_type: sa.types.TypeEngine, owner: str
) -> None:
    op.create_table(
        name,
        _id(),
        sa.Column(owner_fk, owner_type, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _now("created_at"),
        sa.CheckConstraint(
            "kind IN ('pdf', 'office', 'html', 'link', 'image')",
            name=op.f(f"ck_{name}_kind"),
        ),
        sa.CheckConstraint(
            "((kind = 'link') = (url IS NOT NULL))"
            " AND (kind <> 'link' OR file_id IS NULL)",
            name=op.f(f"ck_{name}_target"),
        ),
        sa.ForeignKeyConstraint(
            [owner_fk], [f"{owner}.id"], name=op.f(f"fk_{name}_{owner_fk}_{owner}")
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_file.id"], name=op.f(f"fk_{name}_file_id_stored_file")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
        sa.UniqueConstraint("file_id", name=op.f(f"uq_{name}_file_id")),
    )
    op.create_index(f"ix_{name}_{owner_fk}_sort_id", name, [owner_fk, "sort", "id"])


def _advanced_course() -> None:
    op.create_table(
        "advanced_course",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        _text_array("features"),
        _flag("active", "true"),
        _flag("pub", "false"),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(TITLE_CHECK, name=op.f("ck_advanced_course_title")),
        sa.CheckConstraint("hours > 0", name=op.f("ck_advanced_course_hours")),
        sa.CheckConstraint(
            "cardinality(features) <= 5", name=op.f("ck_advanced_course_features")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_advanced_course")),
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f"CREATE SEQUENCE {SEQUENCE}")
    _pool_course()
    _file_table(*FILE_TABLES[0])
    _capability()
    _file_table(*FILE_TABLES[1])
    _curriculum()
    _file_table(*FILE_TABLES[2])
    _advanced_course()


def _drop_file_table(name: str, owner_fk: str) -> None:
    op.drop_index(f"ix_{name}_{owner_fk}_sort_id", table_name=name)
    op.drop_table(name)


def downgrade() -> None:
    op.drop_table("advanced_course")
    _drop_file_table("curriculum_file", "curriculum_id")
    op.drop_table("curriculum_slot")
    op.drop_index(op.f("ix_curriculum_instructor_id"), table_name="curriculum")
    op.drop_table("curriculum")
    _drop_file_table("capability_file", "capability_id")
    op.drop_index("ix_capability_pool_course_id", table_name="capability")
    op.drop_table("capability")
    _drop_file_table("pool_course_file", "pool_course_id")
    op.drop_index(op.f("ix_pool_course_owner_instructor_id"), table_name="pool_course")
    op.drop_index("ix_pool_course_source_active", table_name="pool_course")
    op.drop_table("pool_course")
    op.execute(f"DROP SEQUENCE {SEQUENCE}")
