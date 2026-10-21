"""관리자 계정 admin_account. 아이디는 소문자·앞뒤 공백 제거로 정규화해 넣는다(정규화는 crud.admin 한 곳)."""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin


class AdminAccount(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "admin_account"

    login_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # argon2id (core.passwords)
