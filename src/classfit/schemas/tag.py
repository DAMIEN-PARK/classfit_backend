"""태그 입출력 모양(T3 계획 결정 xi).

- 표 하나 tag(kind, name). kind 는 field·session·survey_area 이고 T3 는 field 만 쓴다.
- 대분류(group)는 field 태그에만 있고 6값 중 하나다. 값의 원본은 service.rules.instructor.TAG_GROUPS 이고,
  schemas 는 service 를 모르므로 여기 Literal 은 사본이다(같은지는 계약 시험이 잰다).
- 관리자 추가에서 field 태그의 group 을 빼면 기본 "기타" 다. field 가 아닌 태그에는 group 을 주지 않는다.
- 이름은 앞뒤 공백 제거 뒤 1~30자다. 연속 공백 정규화는 crud.tag.normalize_tag_name 이 한다.
- 목록은 T1 Page 모양이되 커서를 받지 않는다(한 쪽만, next_cursor 는 항상 null).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from classfit.schemas.auth import no_control_chars

TagKind = Literal["field", "session", "survey_area"]
TagGroup = Literal[
    "AI 활용·업무자동화",
    "직무별 AX",
    "개발·데이터",
    "콘텐츠·디자인·영상",
    "경영·리더십",
    "기타",
]
DEFAULT_GROUP: TagGroup = "기타"

TagName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=30),
    AfterValidator(no_control_chars),
]


class TagOut(BaseModel):
    id: int
    kind: str
    name: str
    group: str | None
    active: bool
    source: str


class TagAdminOut(TagOut):
    used_by: int  # 이 태그를 단 강사 수(중지 태그 포함)


class TagCreateIn(BaseModel):
    kind: TagKind
    name: TagName
    # 기본값도 검증해야 field 태그의 빠진 대분류가 "기타" 가 된다
    group: TagGroup | None = Field(default=None, validate_default=True)

    @field_validator("group", mode="after")
    @classmethod
    def _group_for_field(
        cls, value: TagGroup | None, info: ValidationInfo
    ) -> TagGroup | None:
        kind = info.data.get("kind")
        if kind == "field":
            return value or DEFAULT_GROUP
        if value is not None:
            raise ValueError("대분류는 field 태그에만 있습니다")
        return None


class TagPatchIn(BaseModel):
    """준 칸만 바꾼다. 셋 다 null 을 받지 않는다."""

    name: TagName | None = None
    group: TagGroup | None = None
    active: bool | None = None

    @field_validator("name", "group", "active")
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("null 일 수 없습니다")
        return value

    def changes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}
