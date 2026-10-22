"""세션 첨부 session_attachment. 0004(T2b), T6 이 마이그레이션 없이 그대로 쓴다.

- kind 는 기획안 7절 5종(pdf · office · html · link · image)이다. T2b 끝점은 pdf·link 만 받는다.
  T6 강사 끝점은 파일 넷(확장자로 종류, service.rules.attachment)과 링크를 받는다.
- 대상 CHECK target: link 면 url 이 있고 file_id 가 없다, link 가 아니면 url 이 없다.
  "pdf ⇒ file_id 있음" 은 걸지 않는다. 넣기가 첨부 행 → stored_file(owner_id = 첨부 id) → file_id 채움 순서라서다
  (id 가 Identity always 라 첨부 id 를 미리 못 받는다). 그 규칙은 시험이 잰다.
- FK 는 둘 다 기본 NO ACTION 이다. 세션·섹션·강의를 지우는 service 가 첨부 행과 그 stored_file 행을 먼저 지운다(r3 부록 C).
- 순서는 (session_id, sort, id). sort 는 끝에 붙인다(crud.attachment).
- origin(T5, 0007): NULL 보통 첨부 · 값은 기본 강의안 사본의 원본 owner_kind(ATTACHMENT_ORIGINS), 응답 노출은 T6.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin

ATTACHMENT_KINDS = ("pdf", "office", "html", "link", "image")
# 기본 강의안 사본의 원본 종류(= T4 풀 파일 표 이름, crud.pool_file.FILE_OWNER_KINDS 와 같다 — 통합 시험이 잰다)
ATTACHMENT_ORIGINS = ("pool_course_file", "capability_file", "curriculum_file")
# 세션당 첨부 상한(T6 결정 iv). 강사 넣기만 센다 — 관리자 넣기·기본 강의안 사본은 걸지 않는다
ATTACHMENTS_MAX = 20


class SessionAttachment(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "session_attachment"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('pdf', 'office', 'html', 'link', 'image')", name="kind"
        ),
        CheckConstraint(
            "((kind = 'link') = (url IS NOT NULL))"
            " AND (kind <> 'link' OR file_id IS NULL)",
            name="target",
        ),
        CheckConstraint(
            "origin IS NULL"
            " OR origin IN ('pool_course_file', 'capability_file', 'curriculum_file')",
            name="origin",
        ),
        Index("ix_session_attachment_session_id_sort_id", "session_id", "sort", "id"),
    )

    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("session.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stored_file.id"), unique=True
    )
    url: Mapped[str | None] = mapped_column(Text)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    origin: Mapped[str | None] = mapped_column(Text)
