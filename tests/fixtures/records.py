"""T7 시험 도우미: 이미지 표본 · 날짜 · 기록 본문 · 배정된 세션 · 응답 키 집합(worker-b 의 계약 시험도 쓴다).

- 배정은 운영 경로 sections.patch_session(SessionPatchIn(instructor_id=…), actor="admin:1")이다(T5 결정 vii).
  강사는 T5 approved(), 강의·섹션은 T5 course_with_section(2026-11-02 시작 평일 2일, 13:00~17:00), 세션은
  crud.schedule.insert_session 이다. T6 시험 픽스처에는 기대지 않는다.
- 이미지 표본은 확장자마다 첫 바이트가 맞고(rules.attachment._SHAPES) 서로 다르며, T2b PDF·T6 표본과도 다르다
  (같은 sha 면 내용 주소가 합쳐 "지우면 바이트는 남는다" 단언이 갈리지 않는다).
- PAST 는 시험 강의의 일차(2026-11-02·03)보다 뒤인 "오늘"이다. 계약 시험은 set_today 로, 통합·행동 시험은 service 의
  today= 로 준다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import today
from classfit.core.config import Settings
from classfit.crud import schedule as crud_schedule
from classfit.schemas.course import SessionPatchIn
from classfit.service.courses import sections
from tests.fixtures.assign import approved, course_with_section

IMAGES: dict[str, bytes] = {
    ".png": b"\x89PNG\r\n\x1a\n%t7-png",
    ".jpg": b"\xff\xd8\xff%t7-jpg",
    ".jpeg": b"\xff\xd8\xff%t7-jpeg",
    ".webp": b"RIFF\x10\x00\x00\x00WEBP%t7-webp",
}
PAST = date(2026, 11, 10)
RECORD_BODY: dict[str, Any] = {
    "held_on": "2026-11-02",
    "start_time": "13:00",
    "end_time": "13:50",
    "attendees": 3,
    "content": "실제 진행",
    "note": None,
}

# 응답 키 집합(T7 결정 xxi) — 계약 시험이 == 로 잰다
RECORD_KEYS = {
    "session_id",
    "status",
    "held_on",
    "start_time",
    "end_time",
    "attendees",
    "content",
    "note",
    "recorded_by",
    "recorded_by_name",
    "recorded_at",
    "confirmed_at",
}
MY_SESSION_KEYS = {
    "session_id",
    "section_id",
    "section_title",
    "title",
    "day_no",
    "date",
    "plan_start",
    "plan_end",
    "status",
    "record",
    "photos",
    "photos_more",
}
ADMIN_SESSION_KEYS = MY_SESSION_KEYS | {"instructor_id", "instructor_name"}
SUMMARY_KEYS = {"sessions", "recorded", "confirmed", "missing", "photos"}
MY_PHOTO_KEYS = {
    "id",
    "session_id",
    "href",
    "size",
    "caption",
    "taken_on",
    "uploaded_by",
    "uploader_name",
    "created_at",
    "editable",
}
ADMIN_PHOTO_KEYS = (MY_PHOTO_KEYS - {"editable"}) | {"seen"}
GALLERY_KEYS = ADMIN_PHOTO_KEYS | {
    "course_id",
    "course_title",
    "client_name",
    "session_title",
    "day_no",
}
# 포털·수강생 응답 어디에도 없어야 하는 기록·사진 칸 이름(T7 결정 xvii)
RECORD_FIELD_KEYS = {
    "record",
    "records",
    "photos",
    "held_on",
    "attendees",
    "content",
    "note",
    "recorded_by",
    "recorded_by_name",
    "recorded_at",
    "confirmed_at",
    "caption",
    "taken_on",
    "uploaded_by",
    "uploader_name",
    "seen",
    "editable",
}


@dataclass(frozen=True)
class Assigned:
    instructor_id: int
    headers: dict[str, str]
    course_id: int
    section_id: int
    session_id: int


async def assigned(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    day_no: int | None = 1,
    slot: int | None = 1,
) -> Assigned:
    """승인 강사 X · 새 강의와 섹션 · 그 섹션의 세션 하나(day_no·slot)를 만들고 X 에게 배정한다."""
    iid, headers = await approved(session, settings, email=email)
    course, section = await course_with_section(session)
    row = await crud_schedule.insert_session(
        session,
        section.id,
        title="교육",
        day_no=day_no,
        slot=slot,
        is_open=True,
        keywords=[],
    )
    await sections.patch_session(
        session, row.id, SessionPatchIn(instructor_id=iid), actor="admin:1"
    )
    return Assigned(iid, headers, course.id, section.id, row.id)


def set_today(app: FastAPI, d: date = PAST) -> None:
    """계약 시험의 오늘(app.deps.today)을 d 로 고정한다."""
    app.dependency_overrides[today] = lambda: d


async def put_record(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    session_id: int,
    **over: Any,
) -> httpx.Response:
    """강사 기록 저장. 본문은 RECORD_BODY 에 over 를 덮은 것이다."""
    return await client.put(
        f"/v1/me/sessions/{session_id}/record",
        headers=headers,
        json={**RECORD_BODY, **over},
    )


async def upload_photo(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    session_id: int,
    name: str = "a.png",
    data: bytes | None = None,
    *,
    caption: str | None = None,
) -> httpx.Response:
    """강사 사진 올리기. 파트 content_type 은 일부러 application/octet-stream 이다(표 값이 정한다)."""
    return await client.post(
        f"/v1/me/sessions/{session_id}/photos",
        headers=headers,
        files={
            "file": (
                name,
                IMAGES[".png"] if data is None else data,
                "application/octet-stream",
            )
        },
        data={} if caption is None else {"caption": caption},
    )
