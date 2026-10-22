"""강사 본인(GET·PATCH /v1/me · POST /v1/me:reapply · /v1/me/documents/…), T3 계획 결정 iv·v·xi·xii.

PATCH 는 준 칸만 바꾼다. 분야 0개는 422, 사용 중지 태그는 422(그 요청은 아무 행도 남기지 않는다).
재신청은 반려 → 대기만이고 사유를 비운다(사유는 audit 에만). 강사 경로는 전부 InstructorCaller 다.
"""

import re

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.main import create_app
from classfit.models import AuditLog, Instructor, InstructorTag, Tag
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.enter import json_keys
from tests.fixtures.instructors import (
    REJECT_REASON,
    count,
    instructor_headers,
    locs,
    make_instructor,
    problem_of,
)

ME = "/v1/me"
EMAIL = "instructor-a@example.com"
METHODS = {"get", "post", "put", "patch", "delete"}
SECRET_KEYS = frozenset({"password_hash", "memo", "code_hash"})


def _instructor_operations() -> list[tuple[str, str]]:
    spec = create_app(Settings()).openapi()
    return sorted(
        (method.upper(), re.sub(r"\{[^}]+\}", "1", path))
        for path, item in spec["paths"].items()
        if path == ME or path.startswith((ME + "/", ME + ":"))
        for method in item
        if method in METHODS
    )


async def _tag_names(session: AsyncSession, instructor_id: int) -> set[str]:
    rows = await session.scalars(
        select(Tag.name)
        .join(InstructorTag, InstructorTag.tag_id == Tag.id)
        .where(InstructorTag.instructor_id == instructor_id)
    )
    return set(rows)


async def test_instructor_me_patch_profile_and_tags(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email=EMAIL, tags=("프롬프트", "엑셀")
    )
    auth = await instructor_headers(db_session, iid)
    before = (await client.get(ME, headers=auth)).json()
    r = await client.patch(
        ME,
        headers=auth,
        json={
            "name": " 새 이름 ",
            "org": "A사",
            "career": ["A사 사내 강의 3년"],
            "tags": ["엑셀", "데이터 분석"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["name"], body["org"], body["career"]) == (
        "새 이름",
        "A사",
        ["A사 사내 강의 3년"],
    )
    # 주지 않은 칸은 그대로
    for key in ("email", "phone", "intro", "status", "terms_version", "created_at"):
        assert body[key] == before[key], key
    assert {t["name"] for t in body["tags"]} == {"엑셀", "데이터 분석"}
    assert await _tag_names(db_session, iid) == {"엑셀", "데이터 분석"}
    assert await count(db_session, InstructorTag) == 2
    assert (
        await count(db_session, Tag, Tag.name == "프롬프트") == 1
    )  # 떼어도 태그는 남는다
    assert (await client.get(ME, headers=auth)).json() == body
    # null 로 소속·소개를 비운다(무소속)
    r = await client.patch(ME, headers=auth, json={"org": None, "intro": None})
    assert r.status_code == 200, r.text
    assert (r.json()["org"], r.json()["name"]) == (None, "새 이름")
    assert await _tag_names(db_session, iid) == {"엑셀", "데이터 분석"}


async def test_instructor_me_patch_zero_tags_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(db_session, app.state.settings, email=EMAIL)
    auth = await instructor_headers(db_session, iid)
    r = await client.patch(ME, headers=auth, json={"tags": []})
    assert ["body", "tags"] in locs(problem_of(r, 422))
    for key in ("tags", "name", "phone", "career"):
        r = await client.patch(ME, headers=auth, json={key: None})
        assert locs(problem_of(r, 422)) == [["body", key]], key
    assert await _tag_names(db_session, iid) == {"프롬프트"}


async def test_instructor_me_patch_inactive_tag_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    settings = app.state.settings
    keeper = await make_instructor(
        db_session, settings, email="instructor-b@example.com", tags=("중지될 분야",)
    )
    iid = await make_instructor(db_session, settings, email=EMAIL, tags=("엑셀",))
    auth = await instructor_headers(db_session, iid)
    _, admin = await admin_headers(db_session)
    tag_id = await db_session.scalar(select(Tag.id).where(Tag.name == "중지될 분야"))
    r = await client.patch(
        f"/v1/admin/tags/{tag_id}", headers=admin, json={"active": False}
    )
    assert r.status_code == 200, r.text
    tags_before = await count(db_session, Tag)
    r = await client.patch(
        ME, headers=auth, json={"tags": ["중지될 분야", "완전히 새 분야"]}
    )
    body = problem_of(r, 422)
    assert [(v["loc"], v["type"]) for v in body["violations"]] == [
        (["body", "tags", 0], "tag_inactive")
    ]
    assert await count(db_session, Tag) == tags_before  # 새 태그 행 0(롤백)
    assert await _tag_names(db_session, iid) == {"엑셀"}
    # 이미 붙은 프로필에는 남는다
    keeper_auth = await instructor_headers(db_session, keeper)
    kept = (await client.get(ME, headers=keeper_auth)).json()["tags"]
    assert [t["name"] for t in kept] == ["중지될 분야"]


async def test_instructor_status_reapply_rejected_to_pending(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email=EMAIL, status="rejected"
    )
    auth = await instructor_headers(db_session, iid)
    assert (await client.get(ME, headers=auth)).json()["reject_reason"] == REJECT_REASON
    r = await client.post(ME + ":reapply", headers=auth)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["reject_reason"]) == ("pending", None)
    row = (
        await db_session.execute(
            select(Instructor.status, Instructor.reject_reason).where(
                Instructor.id == iid
            )
        )
    ).one()
    assert tuple(row) == ("pending", None)
    audit = (
        await db_session.execute(
            select(AuditLog.action, AuditLog.actor, AuditLog.target_id).where(
                AuditLog.target_type == "instructor"
            )
        )
    ).all()
    assert [tuple(a) for a in audit] == [
        ("instructor.reapply", f"instructor:{iid}", str(iid))
    ]


async def test_instructor_status_reapply_not_rejected_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    for n, status in enumerate(("pending", "approved")):
        iid = await make_instructor(
            db_session,
            app.state.settings,
            email=f"instructor-{n}@example.com",
            status=status,
        )
        auth = await instructor_headers(db_session, iid)
        problem_of(
            await client.post(ME + ":reapply", headers=auth), 409, "/problems/conflict"
        )
        current = await db_session.scalar(
            select(Instructor.status).where(Instructor.id == iid)
        )
        assert current == status
    assert await count(db_session, AuditLog, AuditLog.target_type == "instructor") == 0


async def test_instructor_paths_admin_403_and_no_token_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    operations = _instructor_operations()
    assert len(operations) >= 5, (
        operations
    )  # GET·PATCH /me · :reapply · PUT·DELETE 서류
    _, admin = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    learner = await learner_headers(db_session, course.id)
    wrong = []
    for method, path in operations:
        as_admin = await client.request(method, path, headers=admin)
        as_learner = await client.request(method, path, headers=learner)
        anonymous = await client.request(method, path)
        if (
            as_admin.status_code != 403
            or as_learner.status_code != 403
            or anonymous.status_code != 401
            or anonymous.headers.get("www-authenticate") != "Bearer"
        ):
            wrong.append(
                (
                    method,
                    path,
                    as_admin.status_code,
                    as_learner.status_code,
                    anonymous.status_code,
                )
            )
    assert wrong == []


async def test_instructor_me_has_no_secret_keys(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    iid = await make_instructor(
        db_session, app.state.settings, email=EMAIL, status="rejected"
    )
    _, admin = await admin_headers(db_session)
    memo = "관리자만 보는 메모"
    r = await client.patch(
        f"/v1/admin/instructors/{iid}/memo", headers=admin, json={"memo": memo}
    )
    assert r.status_code == 200, r.text
    auth = await instructor_headers(db_session, iid)
    responses = [
        await client.get(ME, headers=auth),
        await client.patch(ME, headers=auth, json={"intro": "한 줄 소개"}),
        await client.post(ME + ":reapply", headers=auth),
    ]
    for r in responses:
        assert r.status_code == 200, r.text
        assert json_keys(r.json()) & SECRET_KEYS == set()
        assert memo not in r.text and "$argon2" not in r.text
