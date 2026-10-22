"""강사 첨부 입출력 모양(T6 계획 결정 iii·vii·viii·xi).

- 응답 MyAttachmentOut 은 T2b AttachmentOut 칸 + origin(기본 강의안 사본이면 원본 owner_kind, 보통 첨부는 null)이다.
  origin 은 강사 첨부 끝점에만 나간다 — 수강생·관리자 포털과 T2b 첨부 응답에는 없다(결정 xi). 파일을 바꾸거나 링크
  주소를 바꾸면 사본이 아니게 되어 null 이 된다(결정 vii·viii).
- 파일 넣기 폼은 title·description?·file 이다. 종류는 파일 이름의 확장자로 정하므로 kind 칸은 받지 않는다(결정 iii).
  파일 파트(file)는 끝점이 따로 본다.
- 링크 넣기 본문은 {title, url, description?}, 고치기 본문은 {title?, description?, url?, position?} 이다. 그 밖의 키는
  422 extra_forbidden(loc ["body", <키>]). title·url·position 의 null 은 422, description 의 null 은 비운다.
  position 은 그 세션 첨부 목록((sort, id) 순)에서 0부터 센 자리이고 목록보다 크면 끝이다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from classfit.schemas.attachment import (
    URL_MAX,
    AttachmentOut,
    Description,
    Title,
    http_url,
)
from classfit.schemas.course import _not_null, _Patch

AttachmentOrigin = Literal["pool_course_file", "capability_file", "curriculum_file"]
POSITION_MAX = 1000
# 앞뒤 공백을 지우기 전 길이는 넉넉히 받고, 지운 뒤 2048자·scheme 은 http_url 이 본다(T2b AttachmentFormIn.url 과 같다)
LinkUrl = Annotated[str, Field(max_length=URL_MAX * 2), AfterValidator(http_url)]


class MyAttachmentOut(AttachmentOut):
    origin: AttachmentOrigin | None


class MyFileFormIn(BaseModel):
    """파일 넣기 폼의 글자 필드."""

    title: Title
    description: Description = None


class MyLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    url: LinkUrl
    description: Description = None


class MyAttachmentPatchIn(_Patch):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    description: Description = None
    url: LinkUrl | None = None
    position: int | None = Field(default=None, ge=0, le=POSITION_MAX)

    @model_validator(mode="after")
    def _shape(self) -> MyAttachmentPatchIn:
        _not_null(self, "title", "url", "position")
        return self
