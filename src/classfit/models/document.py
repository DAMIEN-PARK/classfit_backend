"""강사 서류 표: document_type(종류 시드) · instructor_document(강사가 낸 서류). 0005(T3).

- document_type 은 0005 가 시드 3행을 넣는다: resume 이력서 · cert 자격증/경력증명 · pledge 강사 서약서(기획안 7절 Document,
  모두 required, sort 1·2·3). id 는 글자 PK 다.
- instructor_document 는 (강사, 종류)마다 한 행이고 파일은 stored_file 한 행이다(file_id NOT NULL·유일).
  그 stored_file 의 owner_kind 는 instructor_document, owner_id 는 강사 id 다(서류 행 id 가 아니다, T3 결정 ix).
- FK 는 셋 다 기본 NO ACTION 이다. 교체는 새 stored_file → file_id 바꿈 → 옛 stored_file 행 삭제, 삭제는 서류 행 →
  stored_file 행 순서로 service.files.documents 가 같은 트랜잭션에서 한다(Design 5절 11). 바이트는 gc 몫이다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin


class DocumentType(Base):
    __tablename__ = "document_type"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class InstructorDocument(BigIdMixin, Base):
    __tablename__ = "instructor_document"
    __table_args__ = (
        UniqueConstraint(
            "instructor_id",
            "type_id",
            name="uq_instructor_document_instructor_id_type_id",
        ),
    )

    instructor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instructor.id"), nullable=False
    )
    type_id: Mapped[str] = mapped_column(
        Text, ForeignKey("document_type.id"), nullable=False
    )
    file_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stored_file.id"), nullable=False, unique=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
