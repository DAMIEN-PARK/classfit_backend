"""심화 과정 표 advanced_course. 0006(T4), 관리자만 만든다(기획안 A3 :780).

- id 는 Text `adv-<n>` 이다. import 는 파일 값(시안·현행 홈의 adv-1~adv-10)을 그대로 넣고, 관리자 추가는
  crud.pool.next_id 가 이미 있는 id 를 건너뛴다(T4 결정 xiii).
- 시간은 정수 hours 다(시안 hr:'18시간' → 18, 결정 xvii). 특징 features 는 5개까지(CHECK).
- 지우기는 없다. 사용 중지는 active=false 다. 시드는 넣지 않는다(결정 xvii, import 의 advanced 구간이 넣는다).
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, TimestampMixin
from classfit.models.pool import _TITLE_CHECK

ADVANCED_FEATURES_MAX = 5
ADVANCED_HOURS_RANGE = (1, 200)
ADVANCED_AUDIENCE_MAX = 100  # 대상 글자 수
ADVANCED_TOOL_MAX = 50  # 도구 글자 수
ADVANCED_FEATURE_TEXT_MAX = 100  # 특징 한 줄 글자 수(줄 수는 ADVANCED_FEATURES_MAX)
# 내용 칸(import 지문 · 관리자 PATCH). 플래그는 pub·active
ADVANCED_CONTENT_FIELDS = ("title", "audience", "tool", "hours", "goal", "features")


class AdvancedCourse(TimestampMixin, Base):
    __tablename__ = "advanced_course"
    __table_args__ = (
        CheckConstraint(_TITLE_CHECK, name="title"),
        CheckConstraint("hours > 0", name="hours"),
        CheckConstraint("cardinality(features) <= 5", name="features"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    hours: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    features: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    pub: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
