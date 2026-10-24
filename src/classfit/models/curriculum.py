"""커리큘럼 표: curriculum(강사가 짠 여러 날 과정) · curriculum_slot(차시) · curriculum_file. 0006(T4).

- curriculum.id 는 Text `cur-<강사 id>-<n>` 이다(기획안 7절 :898 · 강사.html:1054, T4 결정 xiii).
- 플래그는 풀 과정과 같은 불리언 셋 reviewed·pub·active 다(결정 v·vi). 지우기는 active=false 다(결정 xi).
- 차시표는 통째 교체다(결정 xv): 격자(일수 × slots_per_day) 안 · (일, 교시) 유일. curriculum 행을 지우면 차시는 CASCADE 다.
  교체·수정은 curriculum 행을 FOR UPDATE 로 잠근 뒤 한다(crud.curriculum.lock_curriculum, 결정 xix).
- 파일 표 curriculum_file 의 칸·CHECK 는 models.pool 의 파일 표와 같다. curriculum FK 는 기본 NO ACTION 이다.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin
from classfit.models.pool import (
    _DIFFICULTY_CHECK,
    _JOB_GROUPS_CHECK,
    _TITLE_CHECK,
    _file_checks,
    _PoolFileCols,
)

CURRICULUM_DAYS_MAX = 30
# 내용 칸. 강사가 이 중 하나나 차시표를 바꾸면 reviewed=false(T4 결정 vi)
CURRICULUM_CONTENT_FIELDS = (
    "title",
    "job_groups",
    "difficulty",
    "days",
    "start_time",
    "end_time",
    "slot_min",
    "break_min",
    "goal",
    "output",
)


class Curriculum(TimestampMixin, Base):
    __tablename__ = "curriculum"
    __table_args__ = (
        CheckConstraint(_TITLE_CHECK, name="title"),
        CheckConstraint(_JOB_GROUPS_CHECK, name="job_groups"),
        CheckConstraint(_DIFFICULTY_CHECK, name="difficulty"),
        CheckConstraint("days BETWEEN 1 AND 30", name="days"),
        CheckConstraint("start_time < end_time", name="hours"),
        CheckConstraint("slot_min > 0", name="slot_min"),
        CheckConstraint("break_min >= 0", name="break_min"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    instructor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instructor.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    job_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    difficulty: Mapped[str] = mapped_column(Text, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    slot_min: Mapped[int] = mapped_column(Integer, nullable=False)
    break_min: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    pub: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reviewed_at: Mapped[dt.datetime | None] = mapped_column()


class CurriculumSlot(BigIdMixin, Base):
    __tablename__ = "curriculum_slot"
    __table_args__ = (
        UniqueConstraint(
            "curriculum_id",
            "day",
            "slot",
            name="uq_curriculum_slot_curriculum_id_day_slot",
        ),
        CheckConstraint("day >= 1", name="day"),
        CheckConstraint("slot >= 1", name="slot"),
        CheckConstraint(_TITLE_CHECK, name="title"),
    )

    curriculum_id: Mapped[str] = mapped_column(
        Text, ForeignKey("curriculum.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class CurriculumFile(_PoolFileCols, BigIdMixin, Base):
    __tablename__ = "curriculum_file"
    __table_args__ = (
        *_file_checks(),
        Index(
            "ix_curriculum_file_curriculum_id_sort_id", "curriculum_id", "sort", "id"
        ),
    )
    owner_fk: ClassVar[str] = "curriculum_id"

    curriculum_id: Mapped[str] = mapped_column(
        Text, ForeignKey("curriculum.id"), nullable=False
    )
