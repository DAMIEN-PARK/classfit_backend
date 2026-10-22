"""인증 표: auth_session(관리자·강사·수강생 공용 세션) · auth_attempt(로그인 시도) · email_verification(인증 코드 해시).

- auth_session 은 불투명 토큰의 sha256 hex 만 둔다(평문 없음). 수강생 행만 course_id 를 가진다(ADR-002, CHECK).
  course_id → course.id FK 는 0003(T2a)이 더했다. ON DELETE 는 기본 NO ACTION 이다(수강생이 있는 강의 삭제는 T2b 가 409 로 먼저 막는다).
- auth_attempt.subject_hash 는 정규화한 login_id 의 sha256 hex. kind 는 상태 열이 아니라 CHECK 를 두지 않는다.
- email_verification 은 T1 이 해시 칸만 앞당겼다. 강사 연결 칸은 0005(T3)가 더한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin


class AuthSession(BigIdMixin, Base):
    __tablename__ = "auth_session"
    __table_args__ = (
        CheckConstraint(
            "principal_type IN ('admin', 'instructor', 'learner')",
            name="principal_type",
        ),
        CheckConstraint(
            "(principal_type = 'learner') = (course_id IS NOT NULL)",
            name="learner_course",
        ),
    )

    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    principal_type: Mapped[str] = mapped_column(Text, nullable=False)
    principal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    course_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("course.id"))
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class AuthAttempt(BigIdMixin, Base):
    __tablename__ = "auth_attempt"
    __table_args__ = (
        Index("ix_auth_attempt_window", "kind", "subject_hash", "client", "at"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)  # T1: "admin_login"
    subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    client: Mapped[str] = mapped_column(Text, nullable=False)  # request.client.host
    at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)


class EmailVerification(BigIdMixin, Base):
    __tablename__ = "email_verification"

    # 처음 발급 전에는 NULL. issue_email_code() 만 채운다(다시 부르면 덮고 tries 를 0 으로)
    code_hash: Mapped[str | None] = mapped_column(Text)
    tries: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
