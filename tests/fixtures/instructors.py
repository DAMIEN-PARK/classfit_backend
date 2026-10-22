"""T3 시험 도우미: 강사 만들기 · 강사 토큰 · PDF · 응답 검사.

- make_instructor 는 단일 진입점 signup() 을 거친다(Design 5절 13): 인증 요청 행(request_email_code) →
  issue_email_code() 로 코드 → signup → 상태는 crud.instructor.set_status 로 바꾼다(반려면 사유 REJECT_REASON).
  인증 요청이 outbox 에 email_code 1행을 남긴다(보내지 않은 채로).
- instructor_headers 는 auth_session 행을 직접 넣어 Bearer 헤더를 만든다(T2a _bearer 꼴, 로그인·argon2 를 건너뛴다).
  관리자 헤더는 tests/fixtures/courses.py 의 admin_headers 를 쓴다.
- pdf_bytes 는 T2b tests/fixtures/enter.py 의 PDF 다.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud.instructor import lock_instructor, set_status
from classfit.schemas.enter import normalize_email
from classfit.service.auth.email_code import issue_email_code
from classfit.service.instructors.signup import request_email_code, signup
from tests.fixtures.courses import _bearer
from tests.fixtures.enter import PDF

PASSWORD = "instructor-pass-1"
REJECT_REASON = "서류를 보완해 주세요"
DOCUMENT_TYPES = ["resume", "cert", "pledge"]


async def make_instructor(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    status: str = "pending",
    tags: Iterable[str] = ("프롬프트",),
) -> int:
    """강사 id. 이름 "강사" · 전화 010-0000-0000 · 무소속 · 비밀번호 PASSWORD."""
    email = normalize_email(email)
    verification_id = await request_email_code(session, email=email)
    code = await issue_email_code(session, verification_id)
    result = await signup(
        session,
        settings,
        email=email,
        code=code,
        password=PASSWORD,
        name="강사",
        phone="010-0000-0000",
        org=None,
        intro=None,
        career=[],
        tags=list(tags),
        client="192.0.2.99",
    )
    assert result.outcome == "ok" and result.instructor_id is not None, result
    if status != "pending":
        row = await lock_instructor(session, result.instructor_id)
        assert row is not None
        reason = REJECT_REASON if status == "rejected" else None
        await set_status(session, row, status, reject_reason=reason)
    return result.instructor_id


async def instructor_headers(
    session: AsyncSession, instructor_id: int, token: str | None = None
) -> dict[str, str]:
    return await _bearer(
        session,
        token or f"instructor-token-{instructor_id}",
        "instructor",
        instructor_id,
        None,
    )


def pdf_bytes() -> bytes:
    return PDF


async def count(session: AsyncSession, model: type, *where: object) -> int:
    return (
        await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    )


def problem_of(
    r: httpx.Response, status: int, type_: str | None = None
) -> dict[str, Any]:
    """problem+json 이고 상태·type 이 맞으면 본문."""
    assert r.status_code == status, (r.status_code, r.text)
    assert r.headers["content-type"].startswith("application/problem+json")
    body: dict[str, Any] = r.json()
    if type_ is not None:
        assert body["type"] == type_, body
    return body


def locs(body: dict[str, Any]) -> list[list[Any]]:
    return [v["loc"] for v in body.get("violations", [])]
