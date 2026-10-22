"""초대코드 invite_code. 0003(T2a).

- code 는 전 행 유일이다(replaced 행의 코드도 다시 쓰지 않는다).
- 강의당 산 코드(status <> 'replaced')는 하나다: 부분 유일 색인 uq_invite_code_course_live.
- 행은 service.courses.codes 의 issue_invite_code() 만 만든다(Design 5절 13). created_at 이 발급일이다.
- 상태는 저장값 active·paused·replaced 이고, 화면의 상태(stopped·expired 포함)는 service.rules.status 가 계산한다.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin

INVITE_CODE_STATUSES = ("active", "paused", "replaced")


class InviteCode(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "invite_code"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'replaced')", name="status"),
        CheckConstraint("max_seats IS NULL OR max_seats > 0", name="max_seats"),
        Index(
            "uq_invite_code_course_live",
            "course_id",
            unique=True,
            postgresql_where=text("status <> 'replaced'"),
        ),
    )

    course_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("course.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'active'")
    )
    expires_on: Mapped[date] = mapped_column(Date, nullable=False)
    max_seats: Mapped[int | None] = mapped_column(Integer)
