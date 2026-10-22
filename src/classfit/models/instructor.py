"""강사 표: instructor(가입·상태·프로필) · instructor_tag(분야 태그 잇기). 0005(T3).

- 같은 이메일(소문자 비교)은 한 사람이다: 식 유일 색인 uq_instructor_email_lower(T2b learner 꼴). email 은 Text 다
  (varchar 면 alembic 이 lower((email)::text) 로 읽어 모델과 다르다고 본다).
- 상태는 Text + CHECK 4값(기획안 A2): pending · approved · rejected · suspended. 전이표는 service.rules.instructor 한 곳이다.
  반려 사유는 반려 상태일 때만 있다: CHECK reject_reason 이 두 방향을 다 막는다(T3 결정 vii·xii).
- org 가 NULL 이면 무소속이다. memo 는 관리자 칸이라 강사 응답에 나가지 않는다. created_at 이 신청일이다.
- 행은 service.instructors.signup 의 signup() 만 만든다(crud.instructor.insert_instructor 경유, 단일 진입).
- instructor_tag 는 강사를 지우면 CASCADE 다(파일이 없다). tag FK 는 기본 NO ACTION 이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin


class Instructor(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "instructor"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 50", name="name"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'suspended')",
            name="status",
        ),
        CheckConstraint(
            "(status = 'rejected') = (reject_reason IS NOT NULL)", name="reject_reason"
        ),
        Index("ix_instructor_status_created_at", "status", "created_at"),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    org: Mapped[str | None] = mapped_column(Text)
    intro: Mapped[str | None] = mapped_column(Text)
    career: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    reject_reason: Mapped[str | None] = mapped_column(Text)
    memo: Mapped[str | None] = mapped_column(Text)
    terms_version: Mapped[str] = mapped_column(Text, nullable=False)
    terms_agreed_at: Mapped[datetime] = mapped_column(nullable=False)


Index("uq_instructor_email_lower", func.lower(Instructor.email), unique=True)


class InstructorTag(Base):
    __tablename__ = "instructor_tag"

    instructor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instructor.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tag.id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
