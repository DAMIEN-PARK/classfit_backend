"""태그 표 tag: 분야(field) · 세션(session) · 설문 영역(survey_area). 0005(T3), T3 는 field 만 쓴다.

- 이름은 앞뒤 공백 제거 + 연속 공백 하나로 정규화해 둔다(crud.tag.normalize_tag_name). (kind, name) 유일.
- group_name 은 분야 태그일 때만 있고 대분류 6값 중 하나다(기획안 7절 Tag · 시안 TAG_GROUPS). 같은 6값이
  service.rules.instructor.TAG_GROUPS 에 있다. 강사가 새로 만든 분야 태그는 "기타" 다(기획안 P4).
- source 는 만든 쪽(admin · instructor). 사용 중지(active 거짓) 태그는 새로 붙일 수 없고 이미 붙은 프로필에는 남는다.
- 칸 이름은 PG 예약어 group·order 를 피해 group_name·sort 다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin


class Tag(BigIdMixin, Base):
    __tablename__ = "tag"
    __table_args__ = (
        CheckConstraint("kind IN ('field', 'session', 'survey_area')", name="kind"),
        CheckConstraint(
            "((kind = 'field') = (group_name IS NOT NULL))"
            " AND (group_name IS NULL OR group_name IN ("
            "'AI 활용·업무자동화', '직무별 AX', '개발·데이터',"
            " '콘텐츠·디자인·영상', '경영·리더십', '기타'))",
            name="group_name",
        ),
        CheckConstraint("source IN ('admin', 'instructor')", name="source"),
        UniqueConstraint("kind", "name", name="uq_tag_kind_name"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
