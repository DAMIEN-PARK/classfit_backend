"""강사 가입: instructor · tag · instructor_tag · document_type(시드 3행) · instructor_document + email_verification 칸 4개

- instructor 는 식 유일 색인 uq_instructor_email_lower = lower(email), 상태 Text + CHECK 4값, 반려 ⇔ 사유 CHECK 두 방향.
- tag 는 (kind, name) 유일, 분야(field)일 때만 대분류 6값, source admin·instructor. instructor_tag 는 강사 삭제 CASCADE.
- document_type 시드: resume 이력서 · cert 자격증/경력증명 · pledge 강사 서약서(required, sort 1·2·3, T3 결정 xiv).
  downgrade 는 표와 함께 지운다.
- instructor_document 는 (강사, 종류) 유일, file_id 유일·NOT NULL. FK 는 셋 다 기본 NO ACTION 이다(T3 결정 ix).
- email_verification 에 email(NOT NULL) · issued_at · consumed_at · instructor_id(FK NO ACTION)와 부분 유일 색인
  uq_email_verification_open = lower(email) WHERE consumed_at IS NULL 을 더한다(T3 결정 xvi).
- 표를 만들기 전에 lock_timeout 과 "email_verification 행" 가드를 둔다(백엔드 안내서 §3.2). email 칸이 없던 때의 행
  (T1 이웃 흐름의 outbox_preview 잔여)이 남으면 NOT NULL 칸을 더할 수 없다. 멈추고 행 수를 알린다.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

GUARD = """
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM email_verification;
  IF n > 0 THEN
    RAISE EXCEPTION '0005 중단 - email 칸이 없던 때의 email_verification 행 % 개. mail_outbox 의 email_code 행과 그 행을 지운 뒤 다시 돌린다 (T3 계획 착수 조건 로컬 DB 줄)', n;
  END IF;
END $$
"""

TAG_GROUP_CHECK = (
    "((kind = 'field') = (group_name IS NOT NULL))"
    " AND (group_name IS NULL OR group_name IN ("
    "'AI 활용·업무자동화', '직무별 AX', '개발·데이터',"
    " '콘텐츠·디자인·영상', '경영·리더십', '기타'))"
)
DOCUMENT_TYPES = [
    {"id": "resume", "name": "이력서", "required": True, "sort": 1},
    {"id": "cert", "name": "자격증/경력증명", "required": True, "sort": 2},
    {"id": "pledge", "name": "강사 서약서", "required": True, "sort": 3},
]


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _instructor() -> None:
    op.create_table(
        "instructor",
        _id(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=True),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column(
            "career",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.Text(), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("terms_version", sa.Text(), nullable=False),
        sa.Column("terms_agreed_at", sa.DateTime(timezone=True), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 50", name=op.f("ck_instructor_name")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'suspended')",
            name=op.f("ck_instructor_status"),
        ),
        sa.CheckConstraint(
            "(status = 'rejected') = (reject_reason IS NOT NULL)",
            name=op.f("ck_instructor_reject_reason"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instructor")),
    )
    op.create_index(
        "uq_instructor_email_lower",
        "instructor",
        [sa.text("lower(email)")],
        unique=True,
    )
    op.create_index(
        "ix_instructor_status_created_at", "instructor", ["status", "created_at"]
    )


def _tags() -> None:
    op.create_table(
        "tag",
        _id(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("group_name", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _now("created_at"),
        sa.CheckConstraint(
            "kind IN ('field', 'session', 'survey_area')", name=op.f("ck_tag_kind")
        ),
        sa.CheckConstraint(TAG_GROUP_CHECK, name=op.f("ck_tag_group_name")),
        sa.CheckConstraint(
            "source IN ('admin', 'instructor')", name=op.f("ck_tag_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tag")),
        sa.UniqueConstraint("kind", "name", name="uq_tag_kind_name"),
    )
    op.create_table(
        "instructor_tag",
        sa.Column("instructor_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        _now("created_at"),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["instructor.id"],
            name=op.f("fk_instructor_tag_instructor_id_instructor"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tag.id"], name=op.f("fk_instructor_tag_tag_id_tag")
        ),
        sa.PrimaryKeyConstraint(
            "instructor_id", "tag_id", name=op.f("pk_instructor_tag")
        ),
    )


def _documents() -> None:
    document_type = op.create_table(
        "document_type",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "required", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("sort", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_type")),
    )
    op.create_table(
        "instructor_document",
        _id(),
        sa.Column("instructor_id", sa.BigInteger(), nullable=False),
        sa.Column("type_id", sa.Text(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        _now("submitted_at"),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["instructor.id"],
            name=op.f("fk_instructor_document_instructor_id_instructor"),
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["document_type.id"],
            name=op.f("fk_instructor_document_type_id_document_type"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["stored_file.id"],
            name=op.f("fk_instructor_document_file_id_stored_file"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instructor_document")),
        sa.UniqueConstraint("file_id", name=op.f("uq_instructor_document_file_id")),
        sa.UniqueConstraint(
            "instructor_id",
            "type_id",
            name="uq_instructor_document_instructor_id_type_id",
        ),
    )
    assert document_type is not None
    op.bulk_insert(document_type, DOCUMENT_TYPES)


def _email_verification() -> None:
    op.add_column("email_verification", sa.Column("email", sa.Text(), nullable=False))
    op.add_column(
        "email_verification",
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_verification",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_verification",
        sa.Column("instructor_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_email_verification_instructor_id_instructor"),
        "email_verification",
        "instructor",
        ["instructor_id"],
        ["id"],
    )
    op.create_index(
        "uq_email_verification_open",
        "email_verification",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(GUARD)
    _instructor()
    _tags()
    _documents()
    _email_verification()


def downgrade() -> None:
    op.drop_index("uq_email_verification_open", table_name="email_verification")
    op.drop_constraint(
        op.f("fk_email_verification_instructor_id_instructor"),
        "email_verification",
        type_="foreignkey",
    )
    op.drop_column("email_verification", "instructor_id")
    op.drop_column("email_verification", "consumed_at")
    op.drop_column("email_verification", "issued_at")
    op.drop_column("email_verification", "email")
    op.drop_table("instructor_document")
    op.drop_table("document_type")
    op.drop_table("instructor_tag")
    op.drop_table("tag")
    op.drop_index("ix_instructor_status_created_at", table_name="instructor")
    op.drop_index("uq_instructor_email_lower", table_name="instructor")
    op.drop_table("instructor")
