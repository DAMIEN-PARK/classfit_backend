"""처리 이력 audit_log: 누가 · 언제 · 대상 · 무엇.

상태를 바꾸는 문(승인·반려·정지·확정 …)은 같은 트랜잭션에 1행을 남긴다.
요청 기록(request_log)은 반대로 다른 트랜잭션에 남긴다 — 그건 이 표가 아니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin


class AuditLog(BigIdMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_target", "target_type", "target_id"),)

    at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)
    # 주체 표기: "admin:3" · "instructor:12" · "system"
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    # 동작 표기: "instructor.approve" · "course.publish"
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
