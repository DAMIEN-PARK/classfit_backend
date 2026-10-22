"""T2b 시험 도우미: 입장 · PDF 첨부 · 섹션·세션 만들기. 강의는 tests/fixtures/courses.py 의 open_test_course 로 만든다.

- enter_learner 는 POST /v1/enter 응답을 그대로 돌려준다(상태 코드를 시험이 본다). name 이 None 이면 칸을 빼고 보낸다.
- add_pdf 는 multipart 로 kind=pdf 를 올린다. 앱 설정에 file_store_root 가 있어야 201 이다(store_root 픽스처).
- add_session 은 관리자 API 로 섹션 1개와 세션 1개를 만들고 세션 id 를 돌려준다.
"""

from __future__ import annotations

from typing import Any

import httpx

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\n%%EOF\n"
ADMIN = "/v1/admin"
# 포털·입장 조회 응답에 있으면 안 되는 개인 키(원칙 10, E-14)
PERSONAL_KEYS = frozenset({"email", "name", "dept", "learner_id", "enrollment_id"})


def json_keys(value: Any) -> set[str]:
    """JSON 값 안의 모든 객체 키(재귀)."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in json_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in json_keys(v)}
    return set()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def enter_learner(
    client: httpx.AsyncClient,
    code: str,
    email: str,
    name: str | None = None,
    **extra: Any,
) -> httpx.Response:
    body: dict[str, Any] = {"code": code, "email": email, **extra}
    if name is not None:
        body["name"] = name
    return await client.post("/v1/enter", json=body)


async def add_pdf(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    session_id: int,
    data: bytes = PDF,
    *,
    title: str = "1교시 강의안",
    content_type: str = "application/pdf",
) -> httpx.Response:
    return await client.post(
        f"{ADMIN}/sessions/{session_id}/attachments",
        headers=headers,
        data={"kind": "pdf", "title": title},
        files={"file": ("a.pdf", data, content_type)},
    )


async def add_section(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    course_id: int,
    title: str = "공통",
) -> int:
    r = await client.post(
        f"{ADMIN}/courses/{course_id}/sections", headers=headers, json={"title": title}
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def add_session(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    course_id: int,
    *,
    section_id: int | None = None,
    **fields: Any,
) -> int:
    """fields 는 SessionIn 칸(title·day_no·slot·is_open …). title 기본값은 "세션"."""
    if section_id is None:
        section_id = await add_section(client, headers, course_id)
    r = await client.post(
        f"{ADMIN}/courses/{course_id}/sections/{section_id}/sessions",
        headers=headers,
        json={"title": "세션", **fields},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])
