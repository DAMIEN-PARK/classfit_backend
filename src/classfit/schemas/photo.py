"""교육 사진 입출력 모양(T7 계획 결정 vii·viii·xi·xxi·xxii).

- 올리기는 폼 caption?·file 이다. 끝점이 인증·세션 판정 뒤에 폼을 읽고 글자 칸을 PhotoFormIn 으로 검증한다(422).
  파일 파트(file)는 끝점이 따로 본다. 설명은 앞뒤 공백을 지운 한 줄 200자이고 비면 null 이다(제어 문자 422).
- 설명 고치기 본문은 {caption} 하나다(null 은 지움, 그 밖의 키는 422 extra_forbidden). 내려받기 목록·확인 표시 본문은
  {ids} 이고 겹친 id 는 하나로 친다(준 차례는 그대로).
- 공개 칸 없음(r3 §7-7). 사람 칸은 강사 이름 하나(uploader_name — 관리자가 올린 사진이면 null, 역할만 uploaded_by,
  T7 결정 xxi). 강사 응답은 editable(내가 올린 사진), 관리자 응답은 seen(확인 표시)을 싣는다.
- href 는 파일 끝점 주소(service.files.store.href_for)이고 바이트는 그 끝점으로만 준다(ADR-003 결정 1·3).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from classfit.models.record import CAPTION_MAX
from classfit.schemas.auth import no_control_chars
from classfit.schemas.course import DbId

ActorKind = Literal["instructor", "admin"]
DOWNLOAD_IDS_MAX = 100
SEEN_IDS_MAX = 500


def _caption(value: str | None) -> str | None:
    """앞뒤 공백 제거 → 제어 문자 422 → 200자 넘으면 422 → 비면 None."""
    if value is None:
        return None
    text = no_control_chars(value.strip())
    if len(text) > CAPTION_MAX:
        raise ValueError(f"설명은 {CAPTION_MAX}자까지입니다")
    return text or None


# 앞뒤 공백을 지우기 전 길이는 넉넉히 받고, 지운 뒤 200자는 _caption 이 본다(schemas.my_attachment.LinkUrl 꼴)
Caption = Annotated[
    str | None, Field(max_length=CAPTION_MAX * 2), AfterValidator(_caption)
]


def _distinct(ids: list[int]) -> list[int]:
    """겹친 id 는 하나로(처음 나온 차례)."""
    return list(dict.fromkeys(ids))


DownloadIds = Annotated[
    list[DbId],
    Field(min_length=1, max_length=DOWNLOAD_IDS_MAX),
    AfterValidator(_distinct),
]
SeenIds = Annotated[
    list[DbId], Field(min_length=1, max_length=SEEN_IDS_MAX), AfterValidator(_distinct)
]


class PhotoFormIn(BaseModel):
    """올리기 폼의 글자 칸."""

    caption: Caption = None


class PhotoPatchIn(BaseModel):
    """caption 키는 있어야 한다(없으면 422 missing). null 은 설명을 지운다."""

    model_config = ConfigDict(extra="forbid")

    caption: Caption


class PhotoIdsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: DownloadIds


class PhotoSeenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: SeenIds


class PhotoOut(BaseModel):
    id: int
    session_id: int
    href: str
    size: int
    caption: str | None
    taken_on: dt.date  # 교육일 — 올릴 때 그 세션의 일차 날짜
    uploaded_by: ActorKind
    uploader_name: str | None  # 올린 강사 이름(관리자가 올렸으면 null)
    created_at: dt.datetime


class MyPhotoOut(PhotoOut):
    editable: bool  # 내가 올린 사진(설명 고치기·지우기 가능)


class AdminPhotoOut(PhotoOut):
    seen: bool  # 관리자 확인 표시(false = 새 사진)


class GalleryPhotoOut(AdminPhotoOut):
    """모아보기 한 항목. 화면이 고객사 → 강의 → 교육일로 묶는다."""

    course_id: int
    course_title: str
    client_name: str
    session_title: str
    day_no: int | None  # 세션의 지금 일차(일차를 지웠으면 null)


class PhotoDownloadItemOut(BaseModel):
    id: int
    href: str
    filename: str  # <고객사>_<YYYYMMDD>_<n>일차_<NN>.<확장자>(service.rules.photo.download_name)


class PhotoDownloadOut(BaseModel):
    items: list[PhotoDownloadItemOut]  # 준 차례
    missing: list[int]  # 없거나 범위 밖인 id


class MarkSeenOut(BaseModel):
    marked: int  # 이번 요청이 새로 확인 표시한 장수
