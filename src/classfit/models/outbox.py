"""메일 outbox: 보내지 않고 같은 요청 트랜잭션에 kind + params 로 쌓는다(ADR-003 결정 5).

본문은 params 에 넣지 않는다. 인증 코드는 params={verification_id} 만 두고 scripts.outbox_preview 가
issue_email_code() 로 만든다. `to` 는 SQL 예약어라 원시 SQL 에서는 "to" 로 따옴표를 친다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin


class MailOutbox(BigIdMixin, Base):
    __tablename__ = "mail_outbox"

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    to: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
