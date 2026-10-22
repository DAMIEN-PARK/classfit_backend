"""T6 시험 도우미: 확장자마다 최소 바이트 · zip 만들기 · 강사에게 배정된 세션 · 강사 첨부 HTTP 호출 · 응답 키 집합.

- SAMPLES 는 확장자마다 서로 다른 바이트다. pdf 는 T2b PDF(tests/fixtures/enter.py)에 한 줄을 더한 다른 바이트다 —
  T5 역량 원본 픽스처가 그 PDF 를 쓰므로(tests/fixtures/assign.py) 같은 바이트면 내용 주소 저장이 한 파일로 합쳐
  "강사 업로드만 지우고 원본은 남는다" gc 단언이 서지 않는다(T6 계획 codex 1차 #3).
  OOXML·zip 은 표준 zipfile 로 메모리에서 만들고(날짜를 고정해 늘 같은 바이트), 이미지는 머리 바이트 + 표시 글자다.
- 배정은 운영 경로 sections.patch_session(SessionPatchIn(instructor_id=…), actor="admin:1")이다(T5 리뷰 Nit 1).
  강사는 T5 approved(승인 강사 + Bearer 헤더), 강의는 T5 course_with_section 이다.
- upload 는 파트 content_type 을 일부러 application/octet-stream 으로 보낸다(저장 content_type 은 확장자 표 값이어야 한다).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import schedule as crud_schedule
from classfit.schemas.course import SessionPatchIn
from classfit.service.courses import sections
from tests.fixtures.assign import approved, course_with_section
from tests.fixtures.enter import PDF

ME = "/v1/me"
ROSTER_KEYS = frozenset({"name", "dept", "enrolled_at"})
MY_ATTACHMENT_KEYS = frozenset(
    {"id", "kind", "title", "description", "href", "size", "origin"}
)


def zip_bytes(files: Mapping[str, str | bytes]) -> bytes:
    """files(이름 → 내용)를 담은 zip 바이트. 날짜를 고정해 같은 입력이면 같은 바이트다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data)
    return buf.getvalue()


SAMPLES: dict[str, bytes] = {
    ".pdf": PDF + b"%t6-own\n",
    ".pptx": zip_bytes(
        {"[Content_Types].xml": "<Types/>", "ppt/presentation.xml": "<p/>"}
    ),
    ".docx": zip_bytes(
        {"[Content_Types].xml": "<Types/>", "word/document.xml": "<w/>"}
    ),
    ".xlsx": zip_bytes({"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<x/>"}),
    ".csv": "이름,부서\n가명,A팀\n".encode(),
    ".zip": zip_bytes({"index.html": "<h1>t6</h1>"}),
    ".png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + b"t6-png",
    ".jpg": b"\xff\xd8\xff\xe0" + b"t6-jpg",
    ".jpeg": b"\xff\xd8\xff\xe1" + b"t6-jpeg",
    ".webp": b"RIFF" + (10).to_bytes(4, "little") + b"WEBP" + b"VP8 t6",
}


@dataclass(frozen=True)
class MySetup:
    instructor_id: int
    headers: dict[str, str]
    course_id: int
    section_id: int
    session_id: int


async def assigned_session(
    session: AsyncSession,
    section_id: int,
    *,
    instructor_id: int | None,
    is_open: bool = False,
    title: str = "세션",
) -> int:
    """그 섹션에 세션을 넣고 instructor_id 강사에게 배정한다(None 이면 미배정). 세션 id."""
    row = await crud_schedule.insert_session(
        session, section_id, title=title, keywords=[], is_open=is_open
    )
    if instructor_id is not None:
        await sections.patch_session(
            session,
            row.id,
            SessionPatchIn(instructor_id=instructor_id),
            actor="admin:1",
        )
    return row.id


async def instructor_session(
    session: AsyncSession, settings: Settings, *, email: str, is_open: bool = False
) -> MySetup:
    """승인 강사 하나와 그에게 배정된 세션 하나(새 강의 · 섹션 하나)."""
    iid, headers = await approved(session, settings, email=email)
    course, section = await course_with_section(session)
    sid = await assigned_session(
        session, section.id, instructor_id=iid, is_open=is_open, title="내 세션"
    )
    return MySetup(iid, headers, course.id, section.id, sid)


async def upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    session_id: int,
    name: str,
    data: bytes,
    *,
    title: str = "강의안",
) -> httpx.Response:
    return await client.post(
        f"{ME}/sessions/{session_id}/attachments",
        headers=headers,
        data={"title": title},
        files={"file": (name, data, "application/octet-stream")},
    )


async def link(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    session_id: int,
    url: str,
    *,
    title: str = "링크",
) -> httpx.Response:
    return await client.post(
        f"{ME}/sessions/{session_id}/attachments:link",
        headers=headers,
        json={"title": title, "url": url},
    )
