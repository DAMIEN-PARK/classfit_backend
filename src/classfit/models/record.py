"""세션 교육 기록 session_record · 교육 사진 photo. 0008(T7).

- 기록은 세션당 1행(session_id 유일)이다. 상태 none 은 행 없음이고 행의 status 는 done·ok 둘이다(T7 결정 iii·iv).
  확인 칸 둘(confirmed_at · confirmed_by_id)은 같이 있거나 같이 없고, ok 일 때만 있다(CHECK confirmed_status · confirmed_pair).
- 기록의 세션 FK 는 CASCADE 다(파일이 없다 — 세션·섹션·강의 삭제가 기록을 같이 지운다). 기록을 지우는 끝점은 없다.
- 사진의 course·session FK 는 기본 NO ACTION 이다. 세션·섹션·강의를 지우는 service 가 crud.photo.delete_photos_under 로
  사진 행과 그 stored_file 행을 먼저 지운다(T7 결정 xvi). 바이트는 gc 몫이다.
- 사진 넣기 순서는 사진 행 → stored_file(owner_kind photo, owner_id = 사진 id) → file_id 채움이다(id 가 Identity always).
- 기록자(recorded_by_*)·올린 사람(uploaded_by_*)은 audit_log.actor 와 같은 FK 없는 주체 표기다(instructor·admin). FK 가
  없어 instructor 행에 KEY SHARE 잠금이 생기지 않는다(T7 결정 xiii).
- 사진에 공개 칸은 없다(r3 §7-7). taken_on 은 올릴 때 그 세션의 일차 날짜이고, 일차를 지우거나 옮겨도 남는다.
  seen_at NULL 은 관리자가 아직 확인하지 않은 새 사진이다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin

RECORD_STATUSES = ("done", "ok")
ACTOR_KINDS = ("instructor", "admin")
ATTENDEES_MAX = 10_000
CAPTION_MAX = 200


class SessionRecord(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "session_record"
    __table_args__ = (
        CheckConstraint("status IN ('done', 'ok')", name="status"),
        CheckConstraint("(start_time IS NULL) = (end_time IS NULL)", name="time_pair"),
        CheckConstraint(
            "start_time IS NULL OR start_time < end_time", name="time_order"
        ),
        CheckConstraint(
            "attendees IS NULL OR attendees BETWEEN 0 AND 10000", name="attendees"
        ),
        # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다(0008 과 같은 글자)
        CheckConstraint("content ~ '[^[:space:]]'", name="content"),
        CheckConstraint(
            "recorded_by_kind IN ('instructor', 'admin')", name="recorded_by_kind"
        ),
        CheckConstraint(
            "(status = 'ok') = (confirmed_at IS NOT NULL)", name="confirmed_status"
        ),
        CheckConstraint(
            "(confirmed_at IS NULL) = (confirmed_by_id IS NULL)", name="confirmed_pair"
        ),
    )

    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("session.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    held_on: Mapped[dt.date] = mapped_column(Date, nullable=False)  # 실시일
    start_time: Mapped[dt.time | None] = mapped_column(Time)  # 실제 시작·끝
    end_time: Mapped[dt.time | None] = mapped_column(Time)
    attendees: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by_kind: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 내용을 마지막으로 저장한 시각(확인만 하면 바뀌지 않는다)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_by_id: Mapped[int | None] = mapped_column(BigInteger)  # 확인한 관리자
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Photo(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "photo"
    __table_args__ = (
        CheckConstraint(
            "uploaded_by_kind IN ('instructor', 'admin')", name="uploaded_by_kind"
        ),
        Index("ix_photo_created_at_id", "created_at", "id"),  # 모아보기 키셋
    )

    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course.id"), nullable=False, index=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("session.id"), nullable=False, index=True
    )
    file_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stored_file.id"), unique=True
    )
    uploaded_by_kind: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    caption: Mapped[str | None] = mapped_column(
        Text
    )  # 한 줄 ≤ CAPTION_MAX(schemas 가 막는다)
    taken_on: Mapped[dt.date] = mapped_column(Date, nullable=False)  # 교육일
    seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
