"""교육 기록·사진: session_record · photo

- session_record 는 세션당 1행(session_id 유일)이다. status done·ok(none 은 행 없음), 실시일 · 실제 시작·끝(둘 다 있거나
  둘 다 없고 시작 < 끝) · 참석 인원 0..10000 · 진행 내용(공백류뿐 금지) · 비고 · 기록자 종류·id · 기록 시각 · 확인자·확인 시각
  (ok 일 때만, 둘이 같이). 세션 FK 는 CASCADE 다(파일이 없다, T7 결정 iv).
- photo 는 course·session FK 기본 NO ACTION(세션·섹션·강의 삭제가 crud 로 먼저 지운다, 결정 xvi) · file_id 유일 ·
  올린 사람 종류 CHECK · 설명 · 교육일 · 확인 표시 seen_at. 색인은 course_id · session_id · (created_at, id)(모아보기 키셋).
- 기록자·확인자·올린 사람 칸에는 FK 를 걸지 않는다(audit_log.actor 와 같은 주체 표기, 결정 iv·vii·xiii).
- 기존 표를 바꾸지 않으므로 행 가드가 없다. lock_timeout 만 둔다(0007 꼴).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# (이름, 식) — models/record.py 의 CheckConstraint 와 같은 글자
RECORD_CHECKS = (
    ("status", "status IN ('done', 'ok')"),
    ("time_pair", "(start_time IS NULL) = (end_time IS NULL)"),
    ("time_order", "start_time IS NULL OR start_time < end_time"),
    ("attendees", "attendees IS NULL OR attendees BETWEEN 0 AND 10000"),
    # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다 — btrim 은 스페이스만 지운다
    ("content", "content ~ '[^[:space:]]'"),
    ("recorded_by_kind", "recorded_by_kind IN ('instructor', 'admin')"),
    ("confirmed_status", "(status = 'ok') = (confirmed_at IS NOT NULL)"),
    ("confirmed_pair", "(confirmed_at IS NULL) = (confirmed_by_id IS NULL)"),
)
UPLOADED_BY_KIND_CHECK = "uploaded_by_kind IN ('instructor', 'admin')"
PHOTO_INDEXES = (("course_id",), ("session_id",), ("created_at", "id"))


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _session_record() -> None:
    op.create_table(
        "session_record",
        _id(),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("attendees", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by_kind", sa.Text(), nullable=False),
        sa.Column("recorded_by_id", sa.BigInteger(), nullable=False),
        _now("recorded_at"),
        sa.Column("confirmed_by_id", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        *(
            sa.CheckConstraint(sql, name=op.f(f"ck_session_record_{name}"))
            for name, sql in RECORD_CHECKS
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["session.id"],
            name=op.f("fk_session_record_session_id_session"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_record")),
        sa.UniqueConstraint("session_id", name=op.f("uq_session_record_session_id")),
    )


def _photo() -> None:
    op.create_table(
        "photo",
        _id(),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by_kind", sa.Text(), nullable=False),
        sa.Column("uploaded_by_id", sa.BigInteger(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("taken_on", sa.Date(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            UPLOADED_BY_KIND_CHECK, name=op.f("ck_photo_uploaded_by_kind")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["course.id"], name=op.f("fk_photo_course_id_course")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["session.id"], name=op.f("fk_photo_session_id_session")
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_file.id"], name=op.f("fk_photo_file_id_stored_file")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo")),
        sa.UniqueConstraint("file_id", name=op.f("uq_photo_file_id")),
    )
    for columns in PHOTO_INDEXES:
        op.create_index(op.f("ix_photo_" + "_".join(columns)), "photo", list(columns))


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    _session_record()
    _photo()


def downgrade() -> None:
    for columns in reversed(PHOTO_INDEXES):
        op.drop_index(op.f("ix_photo_" + "_".join(columns)), table_name="photo")
    op.drop_table("photo")
    op.drop_table("session_record")
