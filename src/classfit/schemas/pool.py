"""과정 풀 입출력 모양(T4 계획 결정 i·v·vi·viii·xiv·xviii·xxi).

- 직무군 job_groups 는 models.pool.JOB_GROUPS 13값 안에서 1개 이상, 중복 없이다. 빈 목록·밖의 값·중복은
  422 loc ["body", "job_groups"]. 난이도는 하·중·상(DIFFICULTIES), 분은 MINUTES_RANGE(import 와 같은 10~600).
- 진행표 schedule 은 [시각, 종류, 내용] 세 칸 줄의 목록이다. 줄(tuple)을 저장 모양(배열의 배열)으로 바꾸는 것은
  service(common.clean_fields)다 — 같은 값 PATCH 가 바뀐 칸 0 이 되게.
- 강사용 출력(PoolItemOut·PoolDetailOut)에는 작성자 칸이 없고 mine 만 있다(기획안 :435 · CAT-004).
  파일 목록은 본인 고유 과정일 때만 채운다. 관리자 출력에만 owner{id, name}·플래그 셋·역량 강사가 있다.
- PATCH 는 준 칸만 바꾼다(changes()). null 을 받지 않는 칸에 null 이면 422. goal·output·material 은 null 로 비운다.
- 파일 폼 PoolFileFormIn 은 T2b 첨부 폼에서 description 을 뺀 꼴이다(kind pdf·link · title · url 은 link 만, 결정 xxi).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
)

from classfit.models.pool import (
    DIFFICULTIES,
    JOB_GROUPS,
    MINUTES_RANGE,
    POOL_CONTENT_FIELDS,
    POOL_ITEM_MAX,
    POOL_ITEMS_MAX,
    POOL_SCHEDULE_CELL_MAX,
    POOL_SCHEDULE_MAX,
    POOL_TEXT_MAX,
    POOL_TITLE_MAX,
)
from classfit.schemas.attachment import URL_MAX, Title, http_url
from classfit.schemas.auth import no_control_chars


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("NUL 문자를 쓸 수 없습니다")
    return value


def _blank_is_none(value: str | None) -> str | None:
    return value or None


def _job_groups(value: list[str]) -> list[str]:
    if any(v not in JOB_GROUPS for v in value):
        raise ValueError(f"직무군은 {len(JOB_GROUPS)}개 값 중에서 고릅니다")
    if len(set(value)) != len(value):
        raise ValueError("같은 직무군을 두 번 줄 수 없습니다")
    return value


def _difficulty(value: str) -> str:
    if value not in DIFFICULTIES:
        raise ValueError("난이도는 " + "·".join(DIFFICULTIES) + " 중 하나입니다")
    return value


def _cell(max_length: int) -> Any:
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length),
        AfterValidator(no_control_chars),
    ]


# 풀 과정·커리큘럼·차시·심화의 제목(표 CHECK 1~200 과 같은 상수)
PoolTitle = _cell(POOL_TITLE_MAX)
JobGroups = Annotated[
    list[str],
    Field(min_length=1),
    AfterValidator(_job_groups),
    WithJsonSchema(
        {
            "type": "array",
            "items": {"type": "string", "enum": list(JOB_GROUPS)},
            "minItems": 1,
            "uniqueItems": True,
        }
    ),
]
Difficulty = Annotated[
    str,
    AfterValidator(_difficulty),
    WithJsonSchema({"type": "string", "enum": list(DIFFICULTIES)}),
]
Minutes = Annotated[int, Field(ge=MINUTES_RANGE[0], le=MINUTES_RANGE[1])]
Text = Annotated[
    Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=POOL_TEXT_MAX),
        AfterValidator(_no_nul),
    ]
    | None,
    AfterValidator(_blank_is_none),
]
Items = Annotated[list[_cell(POOL_ITEM_MAX)], Field(max_length=POOL_ITEMS_MAX)]
# [시각, 종류, 내용] — 기획안 7절 AX_DETAIL.schedule 꼴
ScheduleRow = tuple[
    _cell(POOL_SCHEDULE_CELL_MAX), _cell(POOL_SCHEDULE_CELL_MAX), _cell(POOL_ITEM_MAX)
]
Schedule = Annotated[list[ScheduleRow], Field(max_length=POOL_SCHEDULE_MAX)]
Memo = Annotated[
    Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=POOL_TEXT_MAX),
        AfterValidator(_no_nul),
    ]
    | None,
    AfterValidator(_blank_is_none),
]


def not_null(value: Any) -> Any:
    """PATCH 의 null 거절. 기본값(None)은 검증하지 않으므로 손님이 null 을 직접 보냈을 때만 돈다."""
    if value is None:
        raise ValueError("null 일 수 없습니다")
    return value


class PatchModel(BaseModel):
    """준 칸만 바꾸는 본문."""

    def changes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}


# ── 입력


class OwnCourseIn(BaseModel):
    """강사 고유 과정 등록 · 관리자 AX 과정 추가(AxCourseCreateIn)의 본문."""

    title: PoolTitle
    job_groups: JobGroups
    difficulty: Difficulty
    minutes: Minutes
    goal: Text = None
    output: Text = None
    material: Text = None
    theory: Items = []
    practice: Items = []
    schedule: Schedule = []

    def fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in POOL_CONTENT_FIELDS}


class AxCourseCreateIn(OwnCourseIn):
    """관리자 AX 과정 추가(id ax-custom-<n>, reviewed 참 · pub 거짓, 결정 xviii)."""


class OwnCoursePatchIn(PatchModel):
    """강사 고유 과정 수정. 내용 칸이 바뀌면 reviewed 가 거짓으로 돌아간다(pub·active 유지, 결정 vi)."""

    title: PoolTitle | None = None
    job_groups: JobGroups | None = None
    difficulty: Difficulty | None = None
    minutes: Minutes | None = None
    goal: Text = None
    output: Text = None
    material: Text = None
    theory: Items | None = None
    practice: Items | None = None
    schedule: Schedule | None = None

    @field_validator(
        "title",
        "job_groups",
        "difficulty",
        "minutes",
        "theory",
        "practice",
        "schedule",
    )
    @classmethod
    def _content_not_null(cls, value: Any) -> Any:
        return not_null(value)


class PoolAdminPatchIn(OwnCoursePatchIn):
    """관리자 풀 수정. AX 행은 내용 + active·pub, 고유 과정 행은 reviewed·pub·active 만(결정 xviii).

    한 본문의 플래그는 reviewed → pub → active 순으로 적용한다(결정 v).
    """

    reviewed: bool | None = None
    pub: bool | None = None
    active: bool | None = None

    @field_validator("reviewed", "pub", "active")
    @classmethod
    def _flags_not_null(cls, value: Any) -> Any:
        return not_null(value)


class CapabilityIn(BaseModel):
    """역량 표시. memo 를 빼거나 null·빈 글자면 메모를 비운다."""

    memo: Memo = None


class PoolFileFormIn(BaseModel):
    """풀 파일 폼의 글자 필드. kind 가 먼저라 url 검사가 kind 를 본다."""

    kind: Literal["pdf", "link"]
    title: Title
    url: str | None = Field(default=None, max_length=URL_MAX * 2, validate_default=True)

    @field_validator("url")
    @classmethod
    def _url_for_link(cls, value: str | None, info: ValidationInfo) -> str | None:
        kind = info.data.get("kind")
        if value is not None and not value.strip():
            value = None
        if kind == "link":
            if value is None:
                raise ValueError("link 는 url 이 필요합니다")
            return http_url(value)
        if value is not None:
            raise ValueError("pdf 에는 url 을 주지 않습니다")
        return None


# ── 출력


class PoolFileOut(BaseModel):
    id: int
    kind: str
    title: str
    href: str  # pdf 는 /v1/files/{key}, link 는 그 주소
    size: int | None  # link 는 null


class OwnerOut(BaseModel):
    id: int
    name: str


class CapableOut(BaseModel):
    instructor_id: int
    name: str


class _PoolBase(BaseModel):
    id: str
    source: str  # ax · own
    title: str
    job_groups: list[str]
    difficulty: str
    minutes: int
    goal: str | None
    output: str | None


class _PoolContent(BaseModel):
    material: str | None
    theory: list[str]
    practice: list[str]
    schedule: list[list[str]]


class PoolItemOut(_PoolBase):
    """강사용 풀 한 줄. 작성자 칸이 없다."""

    mine: bool  # 내 고유 과정
    capable: bool  # 내가 가능 표시(역량)를 했다


class PoolDetailOut(PoolItemOut, _PoolContent):
    files: list[PoolFileOut]  # 본인 고유 과정일 때만, 아니면 빈 목록


class OwnCourseOut(PoolDetailOut):
    reviewed: bool
    reviewed_at: dt.datetime | None  # reviewed 거짓 ∧ 값 있음 = 검토 뒤 강사가 고침
    pub: bool
    active: bool


class CapabilityOut(BaseModel):
    pool_id: str
    title: str
    memo: str | None
    files: list[PoolFileOut]
    created_at: dt.datetime


class PoolAdminItemOut(_PoolBase):
    owner: OwnerOut | None  # AX 는 null
    reviewed: bool
    reviewed_at: dt.datetime | None
    pub: bool
    active: bool
    capable_count: int


class PoolAdminOut(PoolAdminItemOut, _PoolContent):
    capable: list[CapableOut]
    files: list[PoolFileOut]
