"""만족도 설문 표: survey_template(양식) · survey(배포 설문) · survey_response(응답). 0009(T8).

- 상태는 저장하지 않는다. open_on·close_on(날짜, 닫힘일 당일까지 열림)·closed_at 과 오늘로 계산한다
  (service.rules.survey.status_at · crud.survey.survey_status_sql). 상태 글자는 SURVEY_STATUSES 셋이고 칸이 아니다.
- 강의당 현재(current) 설문은 하나다: 부분 유일 색인 uq_survey_course_id_current WHERE current. 같은 강의에 새로 배포하면
  닫힌 옛 행을 밀어낸다(current = false). 밀려난 행은 늘 닫혀 있다 — CHECK current_closed.
- 기본 양식은 많아야 하나다: 부분 유일 색인 uq_survey_template_default WHERE is_default. 0009 가 기본 양식 1행을 넣는다.
- 배포 설문의 문항(questions)·양식 이름(template_name)은 배포 시점 스냅샷이다. 양식을 고치거나 지워도 바뀌지 않는다.
  template FK 는 SET NULL, course FK 는 CASCADE 다(파일이 없다 — 수강생 있는 강의는 삭제가 409 라 응답이 사라지는 길은 없다).
- 응답은 (설문, 등록) 하나다(uq_survey_response_survey_id_enrollment_id). 넣기만 하고 고치거나 지우지 않는다.
  submitted_at 은 저장하되 어떤 응답 API 에도 싣지 않는다(Design 1절 만족도 공개 범위). 결과 집계는 answers 만 읽는다.
- 문항은 아홉 키 dict 의 배열이다(T8 결정 v). 아래 상수는 schemas 가 모양 검사에 쓴다.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin

SURVEY_STATUSES = ("scheduled", "open", "closed")  # 계산 상태(칸이 아니다)
QUESTION_TYPES = ("scale", "single", "multi", "text", "info")
KEY_PATTERN = r"^[a-z][a-z0-9_]{0,39}$"
NAME_MAX = 100
QUESTIONS_MAX = 60
OPTIONS_MAX = 30


class SurveyTemplate(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "survey_template"
    __table_args__ = (
        # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다(0009 와 같은 글자)
        CheckConstraint("name ~ '[^[:space:]]'", name="name"),
        CheckConstraint("length(name) <= 100", name="name_length"),
        CheckConstraint("jsonb_typeof(questions) = 'array'", name="questions"),
        Index(
            "uq_survey_template_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)


class Survey(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "survey"
    __table_args__ = (
        CheckConstraint("open_on <= close_on", name="period"),
        CheckConstraint("current OR closed_at IS NOT NULL", name="current_closed"),
        Index(
            "uq_survey_course_id_current",
            "course_id",
            unique=True,
            postgresql_where=text("current"),
        ),
        Index("ix_survey_created_at_id", "created_at", "id"),  # 관리자 목록 키셋
    )

    course_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("course.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("survey_template.id", ondelete="SET NULL"), index=True
    )  # 색인 0012 — 양식 삭제·배포 수 셈·양식별 잠금
    template_name: Mapped[str] = mapped_column(Text, nullable=False)  # 배포 시점 이름
    questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False
    )  # 배포 시점 복제본
    open_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    close_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    # 관리자가 닫았거나 밀려난 시각. 날짜로 닫힌 설문은 None 이다
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class SurveyResponse(BigIdMixin, Base):
    __tablename__ = "survey_response"
    __table_args__ = (
        UniqueConstraint(
            "survey_id",
            "enrollment_id",
            name="uq_survey_response_survey_id_enrollment_id",
        ),
        CheckConstraint("jsonb_typeof(answers) = 'object'", name="answers"),
    )

    survey_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("survey.id", ondelete="CASCADE"), nullable=False
    )
    enrollment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("enrollment.id"), nullable=False
    )
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
