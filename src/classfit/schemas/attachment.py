"""세션 첨부 입출력 모양(T2b 계획 결정 viii).

- 넣기는 폼(multipart·urlencoded) 필드 kind·title·description?·file|url 이다. 끝점이 인증 뒤에 폼을 읽고
  글자 필드를 AttachmentFormIn 으로 검증한다(422). 파일 파트(file)는 끝점이 따로 본다.
- T2b 는 pdf·link 만 받는다(표의 kind CHECK 는 5종). link 는 http·https 만, 2048자까지다. pdf 에는 url 을 주지 않는다.
- href 는 pdf 면 파일 끝점 주소(service.files.store.href_for), link 면 그 url 이다. size 는 pdf 의 바이트 수다.
- Title·Description 은 T6 강사 첨부 모양(schemas.my_attachment)도 쓴다.
"""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from classfit.schemas.auth import no_control_chars

URL_MAX = 2048
DESCRIPTION_MAX = 5000
_SCHEMES = ("http", "https")


class AttachmentOut(BaseModel):
    id: int
    kind: str
    title: str
    description: str | None
    href: str
    size: int | None  # link 는 null


def http_url(value: str) -> str:
    url = no_control_chars(value.strip())
    if len(url) > URL_MAX:
        raise ValueError(f"주소는 {URL_MAX}자까지입니다")
    if any(ch.isspace() for ch in url):
        raise ValueError("주소에 공백을 쓸 수 없습니다")
    parts = urlsplit(url)
    if parts.scheme.lower() not in _SCHEMES or not parts.netloc:
        raise ValueError("주소는 http:// 나 https:// 로 시작해야 합니다")
    return url


def _optional_line(value: str | None) -> str | None:
    """앞뒤 공백 제거 → 제어 문자 422(title·입장 스키마와 같은 정책) → 비면 None."""
    if value is None:
        return None
    return no_control_chars(value.strip()) or None


Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(no_control_chars),
]
Description = Annotated[
    str | None, Field(max_length=DESCRIPTION_MAX), AfterValidator(_optional_line)
]


class AttachmentFormIn(BaseModel):
    """폼 글자 필드의 검증. kind 가 먼저라 url 검사가 kind 를 본다."""

    kind: Literal["pdf", "link"]
    title: Title
    description: Description = None
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
