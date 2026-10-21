"""stored_file: 파일 행. 바이트는 디스크의 sha256 내용 주소에 있고(service.files), 행은 불투명 key 로 가리킨다.

owner_kind·owner_id 는 다형 참조라 FK 가 없다(Design 4절). 그래서 소유자 행을 지우는 crud 가
같은 트랜잭션에서 이 행도 지운다. 등록 안 된 owner_kind 는 crud.scope 가 404 로 막는다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin


class StoredFile(BigIdMixin, Base):
    __tablename__ = "stored_file"

    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    owner_kind: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
