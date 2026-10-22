"""T4 시험 도우미: 풀 과정·커리큘럼 만들기 · 플래그 · 풀 파일 올리기 · 강사 둘 · audit 읽기.

- make_pool_course 는 service 를 거친다(Design 5절 13 · 증명 단일 진입): own 은 create_own_course(reviewed·pub 거짓),
  ax 는 관리자 추가 create_ax_course(id ax-custom-<n>, reviewed 참 · pub 거짓). over 로 내용 칸을 바꾼다.
- make_curriculum 은 create_curriculum 을 거친다(차시표 없이). 차시표는 시험이 API 로 넣는다.
- set_flags 는 시험 준비용으로 행의 reviewed·pub·active 를 바로 쓴다(관리자 PATCH 규칙은 그 PATCH 를 재는 시험이 본다).
  reviewed 를 켜면 reviewed_at 도 채운다.
- add_pool_pdf·add_pool_link 는 multipart·폼으로 올린다. pdf 는 앱 설정에 file_store_root 가 있어야 201 이다.
- instructor_pair 는 강사 A·B 를 만들고 이름을 "가명 가"·"가명 나" 로 바꾼다(응답에 이름 글자가 없는지 보려고).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud.instructor import lock_instructor, update_instructor
from classfit.models import AuditLog, Curriculum, PoolCourse
from classfit.service.pool import admin, curricula, own
from tests.fixtures.enter import PDF
from tests.fixtures.instructors import instructor_headers, make_instructor

ME = "/v1/me"
ADMIN = "/v1/admin"
NAME_A = "가명 가"
NAME_B = "가명 나"
# 강사용 풀 응답에 있으면 안 되는 작성자 키(기획안 :435 · CAT-004)
PERSONAL_POOL_KEYS = frozenset(
    {"instructor_id", "owner", "owner_instructor_id", "name", "email"}
)
OWN_DEFAULTS: dict[str, Any] = {
    "title": "시험 과정 가",
    "job_groups": ["공통(전 직원)"],
    "difficulty": "중",
    "minutes": 120,
    "goal": "시험 목표",
    "output": "시험 산출물",
    "material": None,
    "theory": ["이론 하나", "이론 둘"],
    "practice": ["실습 하나"],
    "schedule": [["09:00", "이론", "개요"], ["10:00", "실습", "따라 하기"]],
}
CURRICULUM_DEFAULTS: dict[str, Any] = {
    "title": "시험 커리큘럼 가",
    "job_groups": ["사무·행정"],
    "difficulty": "하",
    "days": 4,
    "start_time": dt.time(13, 0),
    "end_time": dt.time(17, 0),
    "slot_min": 50,
    "break_min": 10,
    "goal": "시험 목표",
    "output": "시험 산출물",
}


def own_body(**over: Any) -> dict[str, Any]:
    """POST /v1/me/own-courses 본문(JSON)."""
    return {**OWN_DEFAULTS, **over}


def curriculum_body(**over: Any) -> dict[str, Any]:
    """POST /v1/me/curricula 본문(JSON, 시각은 "HH:MM")."""
    body = {**CURRICULUM_DEFAULTS, **over}
    for key in ("start_time", "end_time"):
        if isinstance(body[key], dt.time):
            body[key] = body[key].strftime("%H:%M")
    return body


async def make_pool_course(
    session: AsyncSession,
    *,
    source: str = "own",
    owner_instructor_id: int | None = None,
    **over: Any,
) -> PoolCourse:
    fields = {**OWN_DEFAULTS, **over}
    if source == "own":
        if owner_instructor_id is None:
            raise ValueError("고유 과정은 owner_instructor_id 가 필요합니다")
        return await own.create_own_course(
            session, instructor_id=owner_instructor_id, fields=fields
        )
    return await admin.create_ax_course(session, actor="system", fields=fields)


async def make_curriculum(
    session: AsyncSession, *, instructor_id: int, **over: Any
) -> Curriculum:
    return await curricula.create_curriculum(
        session, instructor_id=instructor_id, fields={**CURRICULUM_DEFAULTS, **over}
    )


async def set_flags(
    session: AsyncSession, row: PoolCourse | Curriculum, **flags: bool
) -> None:
    for name, value in flags.items():
        setattr(row, name, value)
    if flags.get("reviewed"):
        row.reviewed_at = dt.datetime.now(dt.UTC)
    await session.flush()


async def add_pool_pdf(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    path: str,
    data: bytes = PDF,
    *,
    title: str = "강의안",
) -> httpx.Response:
    """path 는 …/files 끝점(예: /v1/me/capabilities/{pool_id}/files)."""
    return await client.post(
        path,
        headers=headers,
        data={"kind": "pdf", "title": title},
        files={"file": ("a.pdf", data, "application/pdf")},
    )


async def add_pool_link(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    path: str,
    *,
    title: str = "참고 자료",
    url: str = "https://example.com/guide",
) -> httpx.Response:
    return await client.post(
        path,
        headers=headers,
        files={"kind": (None, "link"), "title": (None, title), "url": (None, url)},
    )


async def instructor_pair(
    session: AsyncSession, settings: Settings
) -> tuple[tuple[int, dict[str, str]], tuple[int, dict[str, str]]]:
    """((A id, A 헤더), (B id, B 헤더)). 둘 다 대기(pending) 상태다(결정 xvi — 상태를 보지 않는다)."""
    out = []
    for email, name in (
        ("instructor-a@example.com", NAME_A),
        ("instructor-b@example.com", NAME_B),
    ):
        iid = await make_instructor(session, settings, email=email)
        row = await lock_instructor(session, iid)
        assert row is not None
        await update_instructor(session, row, name=name)
        out.append((iid, await instructor_headers(session, iid)))
    return out[0], out[1]


async def audit_rows(
    session: AsyncSession, action_prefix: str
) -> list[tuple[str, str, str, str | None, Any]]:
    """(action, actor, target_type, target_id, detail) — action 이 접두로 시작하는 행, id 순."""
    rows = await session.execute(
        select(
            AuditLog.action,
            AuditLog.actor,
            AuditLog.target_type,
            AuditLog.target_id,
            AuditLog.detail,
        )
        .where(AuditLog.action.startswith(action_prefix))
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]
