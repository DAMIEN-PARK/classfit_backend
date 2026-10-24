"""수강생 표: learner(이메일만) · enrollment(강의마다 이름·부서). 0004(T2b).

- learner 는 사람 하나다. 같은 이메일(소문자 비교)은 같은 행이다: 식 유일 색인 uq_learner_email_lower(r3 부록 C).
  이름 칸이 없다(ADR-002 결정 2). email 은 Text 다. alembic 은 식 색인을 반영한 식 글자로 비교하는데,
  varchar 면 lower((email)::text) 로 읽혀 모델의 lower(email) 과 다르다고 본다.
- enrollment 는 (강의, 사람) 하나에 한 행이다. 표시 이름·부서는 여기에만 두고 다른 강의 행을 바꾸지 않는다(r3 N9).
  created_at 이 등록일이다. 행은 service.enroll.enter 만 만든다(crud.enrollment.insert_enrollment 경유).
- FK 는 둘 다 기본 NO ACTION 이다. 수강생이 있는 강의 삭제는 service 가 409 로 먼저 막는다(T2b 결정 xi).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from classfit.models.base import Base, BigIdMixin


class Learner(BigIdMixin, Base):
    __tablename__ = "learner"

    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


Index("uq_learner_email_lower", func.lower(Learner.email), unique=True)


class Enrollment(BigIdMixin, Base):
    __tablename__ = "enrollment"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "learner_id", name="uq_enrollment_course_id_learner_id"
        ),
        # 공백류가 아닌 글자 하나 이상 · 앞뒤 스페이스를 뺀 50자 이하(0012 — 탭·줄바꿈만 있는 값도 막는다)
        CheckConstraint(
            "name ~ '[^[:space:]]' AND length(btrim(name)) <= 50", name="name"
        ),
    )

    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course.id"), nullable=False
    )
    learner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("learner.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    dept: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    # 관리자 명단의 이메일. 게으른 읽기는 막고(async), 쓰는 쪽이 joinedload 로 부른다(crud.enrollment.list_stmt)
    learner: Mapped[Learner] = relationship(lazy="raise")
