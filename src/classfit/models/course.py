"""강의 표: course · course_day(일차) · section · session(세션). 0003(T2a).

- course 의 status·status_manual: 수동이 아니면 상태는 날짜로 계산한다(service.rules.status). 저장 status 는 수동일 때만 뜻이 있다.
- 기간 start_on·end_on 은 상태·만료일의 기준이다. 일차가 있으면 첫·끝 일차 날짜를 따른다(service.courses.days).
- session 표의 클래스 이름은 CourseSession 이다(AuthSession · SQLAlchemy 세션과 구별).
- 열 이름은 PG 예약어 end·desc 를 피한다(기획안 Session.desc → description).
- 표를 지우면 아래 표는 CASCADE 다: course → course_day · section → session.
- 0007(T5): 원본 참조·담당 강사. 원본 삭제는 비활성이라 NO ACTION(T4) — session 의 pool_course_id · curriculum_id ·
  instructor_id(차시 하나의 현재 담당 강사), course 의 curriculum_src_id(커리큘럼 시작점의 원본).
- 0010(T9a): 회사 연결 company_id(선택 · client_name 은 개설 시점 표시용 복제본으로 따로 남는다). 회사 삭제는 service 가
  활성 연결 강의가 있으면 409, 보관 강의 연결은 DB 가 SET NULL 로 푼다.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin

COURSE_STATUSES = ("prep", "running", "ended")


class Course(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "course"
    __table_args__ = (
        CheckConstraint("status IN ('prep', 'running', 'ended')", name="status"),
        CheckConstraint("start_on <= end_on", name="period"),
        CheckConstraint("hours_per_person >= 0", name="hours_per_person"),
        CheckConstraint("slot_min > 0", name="slot_min"),
        CheckConstraint("break_min >= 0", name="break_min"),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    client_name: Mapped[str] = mapped_column(Text, nullable=False)  # 개설 시점 표시용
    course_type: Mapped[str | None] = mapped_column(Text)
    cohort: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    hours_per_person: Mapped[int] = mapped_column(Integer, nullable=False)
    start_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    slot_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("50")
    )
    break_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )
    intro: Mapped[str | None] = mapped_column(Text)
    notice: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'prep'")
    )
    status_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    archived_at: Mapped[dt.datetime | None] = mapped_column()
    curriculum_src_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("curriculum.id")
    )
    company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("company.id", ondelete="SET NULL"), index=True
    )


class CourseDay(BigIdMixin, Base):
    __tablename__ = "course_day"
    __table_args__ = (
        UniqueConstraint("course_id", "day_no", name="uq_course_day_course_id_day_no"),
        CheckConstraint("day_no >= 1", name="day_no"),
        CheckConstraint("start_time < end_time", name="hours"),
        CheckConstraint(
            "(lunch_start IS NULL) = (lunch_end IS NULL)", name="lunch_pair"
        ),
        CheckConstraint(
            "lunch_start IS NULL OR lunch_start < lunch_end", name="lunch_order"
        ),
    )

    course_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course.id", ondelete="CASCADE"), nullable=False
    )
    day_no: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    lunch_start: Mapped[dt.time | None] = mapped_column(Time)
    lunch_end: Mapped[dt.time | None] = mapped_column(Time)


class Section(BigIdMixin, Base):
    __tablename__ = "section"

    course_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("course.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    description: Mapped[str | None] = mapped_column(Text)


class CourseSession(BigIdMixin, Base):
    __tablename__ = "session"
    __table_args__ = (
        CheckConstraint("day_no IS NOT NULL OR slot IS NULL", name="slot_needs_day"),
        CheckConstraint("slot IS NULL OR slot >= 1", name="slot"),
        CheckConstraint("minutes IS NULL OR minutes > 0", name="minutes"),
        CheckConstraint("(time_start IS NULL) = (time_end IS NULL)", name="time_pair"),
        CheckConstraint(
            "time_start IS NULL OR time_start < time_end", name="time_order"
        ),
    )

    section_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("section.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    day_no: Mapped[int | None] = mapped_column(Integer)
    slot: Mapped[int | None] = mapped_column(Integer)
    minutes: Mapped[int | None] = mapped_column(Integer)
    # 예외 시각. 있으면 교시 계산보다 우선한다(시안 scTime)
    time_start: Mapped[dt.time | None] = mapped_column(Time)
    time_end: Mapped[dt.time | None] = mapped_column(Time)
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    is_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    pool_course_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("pool_course.id")
    )
    curriculum_id: Mapped[str | None] = mapped_column(Text, ForeignKey("curriculum.id"))
    instructor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("instructor.id"), index=True
    )
