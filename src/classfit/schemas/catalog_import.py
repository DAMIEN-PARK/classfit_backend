"""AX 카탈로그 import 입력 모양(scripts.import_ax_catalog, T4 결정 ii).

- 파일 하나 = {"courses": [AxCourseIn…], "advanced": [AdvancedCourseImportIn…]}. 둘 다 선택이지만 둘 다 비면 거절한다.
- 모르는 키는 거절한다(extra=forbid) — 시안 모양(dept·deptName·deptId)을 넣으면 멈춘다. 직무군 매핑은 운영자 몫이다.
- id: 과정 ^ax-[a-z0-9]+(-[a-z0-9]+)*$, 심화 ^adv-[a-z0-9]+(-[a-z0-9]+)*$. ax-custom- 접두는 관리자 추가 전용이라
  field_validator 가 거절한다(룩어헤드는 pydantic 기본 정규식 엔진이 받지 않는다). 파일 안 중복 id 도 거절한다.
- 값: 직무군 JOB_GROUPS 13 안(1개 이상) · 난이도 하·중·상 · 분 MINUTES_RANGE 10~600 · 시간 1~200 · 특징 5개까지.
- 글자·목록 상한은 API 스키마와 한 벌이다(models.pool 의 POOL_*_MAX · models.advanced 의 ADVANCED_*_MAX, 리뷰 Nit 3):
  id 80자 · 제목 200자 · 긴 글 2000자 · 이론·실습 30줄 × 500자 · 진행표 50줄([시각·종류 20자, 내용 500자]) ·
  심화 대상 100자 · 도구 50자 · 특징 100자. import 한 행이 끝점에서 열리고 관리자 PATCH 로 고칠 수 있게 넘는 행은 거절한다.
  한 줄 글자는 앞뒤 공백을 깎고 제어 문자를, 긴 글은 NUL 을 거절하고 빈 글자는 null 로 본다(API Text 와 같다).
- 오류 메시지에 입력 값을 넣지 않는다(스크립트가 위치·사유만 찍는다).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from classfit.models.advanced import (
    ADVANCED_AUDIENCE_MAX,
    ADVANCED_CONTENT_FIELDS,
    ADVANCED_FEATURE_TEXT_MAX,
    ADVANCED_FEATURES_MAX,
    ADVANCED_HOURS_RANGE,
    ADVANCED_TOOL_MAX,
)
from classfit.models.pool import (
    JOB_GROUPS,
    MINUTES_RANGE,
    POOL_CONTENT_FIELDS,
    POOL_ID_MAX,
    POOL_ITEM_MAX,
    POOL_ITEMS_MAX,
    POOL_SCHEDULE_CELL_MAX,
    POOL_SCHEDULE_MAX,
    POOL_TEXT_MAX,
    POOL_TITLE_MAX,
)
from classfit.schemas.auth import no_control_chars

AX_ID_PATTERN = r"^ax-[a-z0-9]+(-[a-z0-9]+)*$"
ADVANCED_ID_PATTERN = r"^adv-[a-z0-9]+(-[a-z0-9]+)*$"
RESERVED_PREFIX = "ax-custom-"


def _line(max_length: int) -> Any:
    """한 줄 글자: 앞뒤 공백을 깎고 1~max_length 자, 제어 문자 거절."""
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length),
        AfterValidator(no_control_chars),
    ]


def _long_text(value: str) -> str | None:
    """긴 글: NUL 거절, 빈 글자는 null(API schemas.pool.Text 와 같다)."""
    if "\x00" in value:
        raise ValueError("NUL 문자를 쓸 수 없습니다")
    return value or None


Title = _line(POOL_TITLE_MAX)
Item = _line(POOL_ITEM_MAX)
Cell = _line(POOL_SCHEDULE_CELL_MAX)
Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=POOL_TEXT_MAX),
    AfterValidator(_long_text),
]
Items = Annotated[list[Item], Field(max_length=POOL_ITEMS_MAX)]
ScheduleRow = tuple[Cell, Cell, Item]  # [시각, 종류, 내용]
Schedule = Annotated[list[ScheduleRow], Field(max_length=POOL_SCHEDULE_MAX)]
Audience = _line(ADVANCED_AUDIENCE_MAX)
Tool = _line(ADVANCED_TOOL_MAX)
Feature = _line(ADVANCED_FEATURE_TEXT_MAX)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AxCourseIn(_In):
    id: Annotated[str, StringConstraints(pattern=AX_ID_PATTERN, max_length=POOL_ID_MAX)]
    title: Title
    job_groups: list[str] = Field(min_length=1)
    difficulty: Literal["하", "중", "상"]
    minutes: int = Field(ge=MINUTES_RANGE[0], le=MINUTES_RANGE[1])
    goal: Text | None = None
    output: Text | None = None
    material: Text | None = None
    theory: Items = Field(default_factory=list)
    practice: Items = Field(default_factory=list)
    schedule: Schedule = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value.startswith(RESERVED_PREFIX):
            raise ValueError(f"{RESERVED_PREFIX} 접두는 관리자 추가 전용입니다")
        return value

    @field_validator("job_groups")
    @classmethod
    def _known_jobs(cls, value: list[str]) -> list[str]:
        if any(job not in JOB_GROUPS for job in value):
            raise ValueError(f"직무군은 정해진 {len(JOB_GROUPS)}개 값 중에서만 고릅니다")
        if len(set(value)) != len(value):
            raise ValueError("직무군이 겹칩니다")
        return value

    def content(self) -> dict[str, Any]:
        """내용 칸(POOL_CONTENT_FIELDS) dict. 진행표 줄은 목록이다(JSONB 값과 같은 모양)."""
        out = {name: getattr(self, name) for name in POOL_CONTENT_FIELDS}
        out["schedule"] = [list(row) for row in self.schedule]
        return out


class AdvancedCourseImportIn(_In):
    id: Annotated[
        str, StringConstraints(pattern=ADVANCED_ID_PATTERN, max_length=POOL_ID_MAX)
    ]
    title: Title
    audience: Audience
    tool: Tool
    hours: int = Field(ge=ADVANCED_HOURS_RANGE[0], le=ADVANCED_HOURS_RANGE[1])
    goal: Text | None = None
    features: list[Feature] = Field(default_factory=list, max_length=ADVANCED_FEATURES_MAX)

    def content(self) -> dict[str, Any]:
        """내용 칸(ADVANCED_CONTENT_FIELDS) dict."""
        return {name: getattr(self, name) for name in ADVANCED_CONTENT_FIELDS}


def _first_duplicate(ids: list[str]) -> int | None:
    seen: set[str] = set()
    for index, value in enumerate(ids):
        if value in seen:
            return index
        seen.add(value)
    return None


class AxCatalogFileIn(_In):
    courses: list[AxCourseIn] = Field(default_factory=list)
    advanced: list[AdvancedCourseImportIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _whole_file(self) -> AxCatalogFileIn:
        if not self.courses and not self.advanced:
            raise ValueError("courses 와 advanced 가 둘 다 비었습니다")
        for section, items in (("courses", self.courses), ("advanced", self.advanced)):
            index = _first_duplicate([item.id for item in items])
            if index is not None:
                raise ValueError(f"{section}.{index}.id 가 파일 안의 앞 항목과 겹칩니다")
        return self
