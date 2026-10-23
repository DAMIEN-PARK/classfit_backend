"""교육 사진: 올리기 · 거절 · 설명 · 남의 사진 403 · 지우기 · 관리자 모아보기 · 확인 표시 · 내려받기 목록
(T7 계획 결정 i·vii·viii·ix·xi·xii·xxi·xxii · 증명 14~19).

올리기는 담당 강사 ∧ 지난 차시(그 세션의 일차 날짜 ≤ 오늘)만이다(예정·일차 미정 409, 남의 세션·미배정 403). 종류는 파일
이름의 확장자(png·jpg·jpeg·webp)로 정하고 첫 바이트가 맞아야 하며 content_type 은 확장자 표의 값이다. 설명 고치기·지우기는
담당 강사 ∧ 내가 올린 사진만이다. 파일 열람은 관리자 ∨ 그 세션의 지금 담당 강사다(수강생·같은 강의 다른 강사 403).
공개 칸은 없다. 저장소 루트가 필요한 시험은 app.state.settings 를 file_store_root=tmp_path 로 바꾼다.
"""

import hashlib
import itertools
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud.instructor import lock_instructor, update_instructor
from classfit.models import AuditLog, Photo, StoredFile
from classfit.service.files.store import path_for
from tests.fixtures.assign import approved, course_with_section
from tests.fixtures.courses import admin_headers, learner_headers
from tests.fixtures.enter import PDF, add_session, json_keys
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.records import (
    GALLERY_KEYS,
    IMAGES,
    MY_PHOTO_KEYS,
    assigned,
    set_today,
    upload_photo,
)

ADMIN = "/v1/admin"
ME = "/v1/me"
MIB = 1024 * 1024
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422
DAY1 = date(2026, 11, 2)  # 시험 강의 1일차
X_NAME = "강사"  # make_instructor 가 주는 이름
Y_NAME = "이가명"
# 확장자 → content_type. 결정 vii 의 표를 시험이 따로 적는다(규칙 모듈의 표를 읽지 않는다)
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
PUBLIC_KEYS = {"public", "is_public", "published"}
PRIVATE_KEYS = {"email", "phone", "learner_id", "enrollment_id", "public"}
PAGE_KEYS = {"items", "next_cursor", "has_more"}
# 사진 자리에서 받지 않는 종류의 문구(끝점 글자를 시험이 따로 적는다)
NOT_IMAGE = "이미지 파일이 아닙니다(png·jpg·jpeg·webp 만 받습니다)"
_SEQ = itertools.count(1)


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _sample(ext: str) -> bytes:
    """그 확장자의 첫 바이트 + 부를 때마다 다른 꼬리(같은 sha 로 합쳐지지 않게)."""
    return IMAGES[ext] + f"-photos-{next(_SEQ)}".encode()


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json() if status != 204 else None


async def _assign(
    client: httpx.AsyncClient, admin: dict[str, str], session_id: int, iid: int | None
) -> None:
    r = await client.patch(
        f"{ADMIN}/sessions/{session_id}", headers=admin, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


async def _owned(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    course_id: int,
    section_id: int,
    iid: int | None,
    **fields: Any,
) -> int:
    sid = await add_session(client, admin, course_id, section_id=section_id, **fields)
    if iid is not None:
        await _assign(client, admin, sid, iid)
    return sid


async def _upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    session_id: int,
    ext: str = ".png",
    *,
    caption: str | None = None,
) -> dict[str, Any]:
    r = await upload_photo(
        client, headers, session_id, f"사진{ext}", _sample(ext), caption=caption
    )
    body: dict[str, Any] = _ok(r, 201)
    return body


async def _written(session: AsyncSession) -> tuple[int, int, int]:
    """(사진 행, 사진 파일 행, 사진 audit) 수."""
    return (
        await count(session, Photo),
        await count(session, StoredFile, StoredFile.owner_kind == "photo"),
        await count(session, AuditLog, AuditLog.target_type == "photo"),
    )


async def _audits(session: AsyncSession, action: str) -> list[tuple[Any, ...]]:
    """그 action 의 (actor, target_id, detail), id 순."""
    rows = await session.execute(
        select(AuditLog.actor, AuditLog.target_id, AuditLog.detail)
        .where(AuditLog.action == action)
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _stored_of(session: AsyncSession, href: str) -> StoredFile:
    key = href.rsplit("/", 1)[-1]
    return (
        await session.execute(select(StoredFile).where(StoredFile.key == key))
    ).scalar_one()


async def _rename(session: AsyncSession, instructor_id: int, name: str) -> None:
    row = await lock_instructor(session, instructor_id)
    assert row is not None
    await update_instructor(session, row, name=name)


async def test_photo_upload_201(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    set_today(app)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    await _owned(client, admin, me.course_id, me.section_id, y, day_no=1, slot=2)
    learner = await learner_headers(db_session, me.course_id)
    captions = {".png": "  실습 장면  ", ".jpg": None, ".jpeg": "", ".webp": "발표"}
    stored_captions = {
        ".png": "실습 장면",
        ".jpg": None,
        ".jpeg": None,
        ".webp": "발표",
    }

    made: list[tuple[dict[str, Any], bytes]] = []
    for ext, data in IMAGES.items():
        # 파트 content_type 은 application/octet-stream 이다 — 저장값은 확장자 표의 값
        r = await upload_photo(
            client, me.headers, me.session_id, f"사진{ext}", data, caption=captions[ext]
        )
        body = _ok(r, 201)
        assert set(body) == MY_PHOTO_KEYS, ext
        assert {k: body[k] for k in MY_PHOTO_KEYS - {"id", "href", "created_at"}} == {
            "session_id": me.session_id,
            "size": len(data),
            "caption": stored_captions[ext],
            "taken_on": "2026-11-02",  # 교육일 = 그 세션의 일차 날짜
            "uploaded_by": "instructor",
            "uploader_name": X_NAME,
            "editable": True,
        }, ext
        assert json_keys(body) & PUBLIC_KEYS == set()
        stored = await _stored_of(db_session, body["href"])
        assert (
            stored.content_type,
            stored.owner_kind,
            stored.owner_id,
            stored.size,
        ) == (CONTENT_TYPES[ext], "photo", body["id"], len(data)), ext
        file_id = await db_session.scalar(
            select(Photo.file_id).where(Photo.id == body["id"])
        )
        assert file_id == stored.id, ext
        made.append((body, data))

    assert await _audits(db_session, "photo.create") == [
        (
            f"instructor:{me.instructor_id}",
            str(body["id"]),
            {"session_id": me.session_id},
        )
        for body, _ in made
    ]
    for body, data in made:
        for headers in (me.headers, admin):  # 담당 강사 · 관리자
            got = await client.get(body["href"], headers=headers)
            assert (got.status_code, got.content) == (200, data), body["href"]
        for headers in (y_auth, learner):  # 같은 강의 다른 강사 · 수강생
            problem_of(
                await client.get(body["href"], headers=headers),
                403,
                "/problems/forbidden",
            )
    assert {c.name for c in Photo.__table__.columns} & PUBLIC_KEYS == set()


async def test_photo_upload_rejections(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    app.state.settings = Settings(file_store_root=tmp_path, attachment_image_max_mb=1)
    settings = app.state.settings
    set_today(app, DAY1)  # 1일차(11-02)는 지난 차시, 2일차(11-03)는 예정
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    x = me.instructor_id
    theirs = await _owned(
        client, admin, me.course_id, me.section_id, y, day_no=1, slot=2
    )
    nobody = await _owned(
        client, admin, me.course_id, me.section_id, None, day_no=1, slot=3
    )
    future = await _owned(
        client, admin, me.course_id, me.section_id, x, day_no=2, slot=1
    )
    undated = await _owned(client, admin, me.course_id, me.section_id, x, title="미정")
    learner = await learner_headers(db_session, me.course_id)
    png = IMAGES[".png"]
    before = await _written(db_session)
    assert before == (0, 0, 0)

    async def rejected(
        r: httpx.Response,
        status: int,
        type_: str | None = None,
        loc: list[Any] | None = None,
    ) -> dict[str, Any]:
        body = problem_of(r, status, type_)
        if loc is not None:
            assert locs(body) == [loc], body
        assert await _written(db_session) == before, r.request.url
        return body

    for sid in (future, undated):  # 예정 차시 · 일차 미정 — 지난 차시에만 올린다
        await rejected(
            await upload_photo(client, me.headers, sid), 409, "/problems/conflict"
        )
    for sid in (theirs, nobody):  # 남의 세션 · 미배정
        await rejected(
            await upload_photo(client, me.headers, sid), 403, "/problems/forbidden"
        )
    await rejected(
        await upload_photo(client, learner, me.session_id), 403, "/problems/forbidden"
    )
    await rejected(
        await upload_photo(client, me.headers, LARGEST), 404, "/problems/not_found"
    )
    body = await rejected(
        await upload_photo(client, me.headers, OVERFLOW),
        422,
        loc=["path", "session_id"],
    )
    assert [v["type"] for v in body["violations"]] == ["less_than"]
    for name, data in (
        ("강의안.pdf", PDF),  # 받는 첨부 종류지만 사진이 아니다
        ("그림.svg", b"<svg/>"),
        ("그림.gif", b"GIF89a"),
        ("이름없음", png),
        ("그림.png", PDF),  # 확장자와 첫 바이트가 다름
    ):
        await rejected(
            await upload_photo(client, me.headers, me.session_id, name, data),
            422,
            loc=["body", "file"],
        )
    # 사진이 아닌 확장자는 첫 바이트와 상관없이 "이미지가 아님" 이고, 이미지 확장자에 틀린 바이트만 "맞지 않음" 이다
    for name, data, msg in (
        ("강의안.pdf", PDF, NOT_IMAGE),
        ("강의안.pdf", png, NOT_IMAGE),  # pdf 확장자에 pdf 가 아닌 바이트
        ("발표.pptx", png, NOT_IMAGE),
        ("그림.png", PDF, "파일 내용이 확장자와 맞지 않습니다"),
    ):
        body = await rejected(
            await upload_photo(client, me.headers, me.session_id, name, data),
            422,
            loc=["body", "file"],
        )
        assert [v["msg"] for v in body["violations"]] == [msg], name
    for caption in ("가" * 201, "줄\n바꿈"):
        await rejected(
            await upload_photo(client, me.headers, me.session_id, caption=caption),
            422,
            loc=["body", "caption"],
        )
    await rejected(  # file 파트 없음
        await client.post(
            f"{ME}/sessions/{me.session_id}/photos",
            headers=me.headers,
            data={"caption": "x"},
        ),
        422,
        loc=["body", "file"],
    )
    big = png + b"\0" * (MIB + 1 - len(png))  # 이미지 상한 1MiB + 1바이트
    body = await rejected(
        await upload_photo(client, me.headers, me.session_id, "큰.png", big), 413
    )
    assert "1MB" in body["detail"]

    async def chunks() -> AsyncIterator[bytes]:
        yield b'--x\r\nContent-Disposition: form-data; name="caption"\r\n\r\nx\r\n--x--\r\n'

    r = await client.post(
        f"{ME}/sessions/{me.session_id}/photos",
        headers={**me.headers, "content-type": "multipart/form-data; boundary=x"},
        content=chunks(),
    )
    assert "content-length" not in r.request.headers
    await rejected(r, 411)
    assert not any(p.is_file() for p in tmp_path.rglob("*"))  # 바이트도 쓰지 않았다

    app.state.settings = Settings(attachment_image_max_mb=1)  # 저장소 미구성
    body = await rejected(
        await upload_photo(client, me.headers, me.session_id),
        501,
        "/problems/not_configured",
    )
    assert body["missing"] == ["CLASSFIT_FILE_STORE_ROOT"]


async def test_photo_caption_and_others_photo_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    set_today(app)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    mine = (await _upload(client, me.headers, me.session_id, caption="처음"))["id"]
    url = f"{ME}/photos/{mine}"
    update = (f"instructor:{me.instructor_id}", str(mine), {"fields": ["caption"]})

    body = _ok(
        await client.patch(url, headers=me.headers, json={"caption": " 바꾼 설명 "})
    )
    assert set(body) == MY_PHOTO_KEYS
    assert (body["id"], body["caption"], body["editable"], body["uploader_name"]) == (
        mine,
        "바꾼 설명",
        True,
        X_NAME,
    )
    assert await _audits(db_session, "photo.update") == [update]
    same = _ok(
        await client.patch(url, headers=me.headers, json={"caption": "바꾼 설명"})
    )
    assert same == body
    assert await _audits(db_session, "photo.update") == [update]  # 같은 값은 audit 없음
    cleared = _ok(await client.patch(url, headers=me.headers, json={"caption": None}))
    assert cleared["caption"] is None
    assert await _audits(db_session, "photo.update") == [update, update]
    body = problem_of(
        await client.patch(
            url, headers=me.headers, json={"caption": "x", "file_id": 1}
        ),
        422,
    )
    assert locs(body) == [["body", "file_id"]]
    assert [v["type"] for v in body["violations"]] == ["extra_forbidden"]
    body = problem_of(await client.patch(url, headers=me.headers, json={}), 422)
    assert locs(body) == [["body", "caption"]]

    # 남의 사진: Y 가 담당일 때 올린 사진은 X 가 다시 맡아도 고치지도 지우지도 못한다.
    # Y 는 이제 담당이 아니라 자기 사진도 못 고친다(관리자가 지운다)
    await _assign(client, admin, me.session_id, y)
    theirs = (await _upload(client, y_auth, me.session_id, ".jpg", caption="Y 사진"))[
        "id"
    ]
    await _assign(client, admin, me.session_id, me.instructor_id)
    before = await _written(db_session)
    for headers in (me.headers, y_auth):
        problem_of(
            await client.patch(
                f"{ME}/photos/{theirs}", headers=headers, json={"caption": "남의 것"}
            ),
            403,
            "/problems/forbidden",
        )
        problem_of(
            await client.delete(f"{ME}/photos/{theirs}", headers=headers),
            403,
            "/problems/forbidden",
        )
    problem_of(
        await client.patch(url, headers=y_auth, json={"caption": "x"}),
        403,
        "/problems/forbidden",
    )
    assert await _written(db_session) == before
    caption = await db_session.scalar(select(Photo.caption).where(Photo.id == theirs))
    assert caption == "Y 사진"

    problem_of(
        await client.patch(
            f"{ME}/photos/{LARGEST}", headers=me.headers, json={"caption": "x"}
        ),
        404,
        "/problems/not_found",
    )
    problem_of(
        await client.delete(f"{ME}/photos/{LARGEST}", headers=me.headers),
        404,
        "/problems/not_found",
    )
    for r in (
        await client.patch(
            f"{ME}/photos/{OVERFLOW}", headers=me.headers, json={"caption": "x"}
        ),
        await client.delete(f"{ME}/photos/{OVERFLOW}", headers=me.headers),
    ):
        assert locs(problem_of(r, 422)) == [["path", "photo_id"]]


async def test_photo_delete_204_and_admin_delete(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    set_today(app)
    admin_id, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    first_bytes = _sample(".png")
    first = _ok(
        await upload_photo(client, me.headers, me.session_id, "a.png", first_bytes),
        201,
    )
    second = await _upload(client, me.headers, me.session_id, ".webp")
    by_x = f"instructor:{me.instructor_id}"

    _ok(await client.delete(f"{ME}/photos/{first['id']}", headers=me.headers), 204)
    assert await count(db_session, Photo, Photo.id == first["id"]) == 0
    assert (
        await count(
            db_session,
            StoredFile,
            StoredFile.owner_kind == "photo",
            StoredFile.owner_id == first["id"],
        )
        == 0
    )
    for headers in (me.headers, admin):  # 옛 href 는 404
        problem_of(
            await client.get(first["href"], headers=headers), 404, "/problems/not_found"
        )
    # 바이트는 gc 몫이다(같은 트랜잭션에서 지우지 않는다)
    assert path_for(store_root, hashlib.sha256(first_bytes).hexdigest()).is_file()
    problem_of(
        await client.delete(f"{ME}/photos/{first['id']}", headers=me.headers),
        404,
        "/problems/not_found",
    )

    _ok(await client.delete(f"{ADMIN}/photos/{second['id']}", headers=admin), 204)
    assert await _written(db_session) == (0, 0, 4)  # create 2 + delete 2
    problem_of(
        await client.get(second["href"], headers=admin), 404, "/problems/not_found"
    )
    problem_of(
        await client.delete(f"{ADMIN}/photos/{second['id']}", headers=admin),
        404,
        "/problems/not_found",
    )
    body = problem_of(
        await client.delete(f"{ADMIN}/photos/{OVERFLOW}", headers=admin), 422
    )
    assert locs(body) == [["path", "photo_id"]]
    assert await _audits(db_session, "photo.delete") == [
        (by_x, str(first["id"]), {"session_id": me.session_id}),
        (f"admin:{admin_id}", str(second["id"]), {"session_id": me.session_id}),
    ]

    # 같은 바이트의 두 사진 — 하나를 지워도 남은 사진은 열린다
    shared = _sample(".jpg")
    kept, gone = [
        _ok(
            await upload_photo(client, me.headers, me.session_id, name, shared),
            201,
        )
        for name in ("c.jpg", "d.jpg")
    ]
    assert kept["href"] != gone["href"]
    _ok(await client.delete(f"{ME}/photos/{gone['id']}", headers=me.headers), 204)
    got = await client.get(kept["href"], headers=me.headers)
    assert (got.status_code, got.content) == (200, shared)
    problem_of(
        await client.get(gone["href"], headers=me.headers), 404, "/problems/not_found"
    )


async def test_photo_admin_gallery_filters(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    set_today(app)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, settings, email="x@example.com")  # A사 · 시험 강의
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    await _rename(db_session, y, Y_NAME)
    b_course, b_section = await course_with_section(
        db_session, title="B 강의", client_name="B사"
    )
    b_session = await _owned(
        client, admin, b_course.id, b_section.id, y, title="B 교시", day_no=1, slot=1
    )
    p1 = (await _upload(client, me.headers, me.session_id, caption="도구 실습 100%"))[
        "id"
    ]
    p2 = (
        await _upload(client, me.headers, me.session_id, ".jpg", caption="점심_시간")
    )["id"]
    p3 = (await _upload(client, me.headers, me.session_id, ".webp"))["id"]
    p4 = (await _upload(client, y_auth, b_session, caption="발표"))["id"]
    p5 = (await _upload(client, y_auth, b_session, ".jpeg"))["id"]
    url = f"{ADMIN}/photos"

    async def ids(**params: Any) -> list[int]:
        body = _ok(await client.get(url, headers=admin, params=params))
        assert set(body) == PAGE_KEYS
        return [i["id"] for i in body["items"]]

    body = _ok(await client.get(url, headers=admin))
    assert set(body) == PAGE_KEYS
    # 올린 시각 내림차순(같은 트랜잭션이라 시각이 같으면 id 내림차순)
    assert [i["id"] for i in body["items"]] == [p5, p4, p3, p2, p1]
    assert (body["has_more"], body["next_cursor"]) == (False, None)
    for item in body["items"]:
        assert set(item) == GALLERY_KEYS, item
    oldest = body["items"][-1]
    assert {
        k: oldest[k]
        for k in (
            "course_id",
            "course_title",
            "client_name",
            "session_id",
            "session_title",
            "day_no",
            "taken_on",
            "caption",
            "uploaded_by",
            "uploader_name",
            "seen",
        )
    } == {
        "course_id": me.course_id,
        "course_title": "시험 강의",
        "client_name": "A사",
        "session_id": me.session_id,
        "session_title": "교육",
        "day_no": 1,
        "taken_on": "2026-11-02",
        "caption": "도구 실습 100%",
        "uploaded_by": "instructor",
        "uploader_name": X_NAME,
        "seen": False,
    }
    assert json_keys(body) & PRIVATE_KEYS == set()

    assert await ids(company="A사") == [p3, p2, p1]
    assert await ids(company="B사") == [p5, p4]
    assert await ids(course_id=b_course.id) == [p5, p4]
    assert await ids(q="실습") == [p1]  # 설명
    assert await ids(q="100%") == [p1]
    assert await ids(q="%") == [p1]  # % 는 글자다
    assert await ids(q="_") == [p2]  # _ 는 글자다
    assert await ids(q=Y_NAME) == [p5, p4]  # 올린 강사 이름
    assert await ids(q="B 강의") == [p5, p4]  # 강의 제목
    assert await ids(q="B 교시") == [p5, p4]  # 세션 제목
    assert await ids(q="b사") == [p5, p4]  # 고객사(대소문자 무시)
    assert await ids(company="A사", q="점심") == [p2]
    assert _ok(
        await client.post(f"{url}:mark-seen", headers=admin, json={"ids": [p1, p4]})
    ) == {"marked": 2}
    assert await ids(new_only="true") == [p5, p3, p2]

    pages, cursor = [], None
    for expected_more in (True, True, False):
        params: dict[str, Any] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = _ok(await client.get(url, headers=admin, params=params))
        assert page["has_more"] is expected_more
        pages.append([i["id"] for i in page["items"]])
        cursor = page["next_cursor"]
    assert pages == [[p5, p4], [p3, p2], [p1]]  # 겹치지 않는다
    assert cursor is None

    bad = problem_of(
        await client.get(url, headers=admin, params={"cursor": "깨진커서"}), 422
    )
    assert locs(bad) == [["query", "cursor"]]
    body = problem_of(
        await client.get(url, headers=admin, params={"course_id": OVERFLOW}), 422
    )
    assert locs(body) == [["query", "course_id"]]
    for params in ({"q": ""}, {"q": "가" * 101}, {"company": ""}, {"limit": 101}):
        problem_of(await client.get(url, headers=admin, params=params), 422)
    problem_of(await client.get(url, headers=me.headers), 403, "/problems/forbidden")


async def test_photo_mark_seen_and_download(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    set_today(app)
    _, admin = await admin_headers(db_session)
    me = await assigned(db_session, app.state.settings, email="x@example.com")
    p1 = (await _upload(client, me.headers, me.session_id, ".png"))["id"]
    p2_bytes = _sample(".jpg")
    p2 = _ok(
        await upload_photo(client, me.headers, me.session_id, "b.jpg", p2_bytes), 201
    )["id"]
    p3 = (await _upload(client, me.headers, me.session_id, ".webp"))["id"]
    audits = await count(db_session, AuditLog)
    seen = f"{ADMIN}/photos:mark-seen"

    async def new_ids() -> list[int]:
        body = _ok(
            await client.get(
                f"{ADMIN}/photos", headers=admin, params={"new_only": True}
            )
        )
        return [i["id"] for i in body["items"]]

    assert _ok(await client.post(seen, headers=admin, json={"ids": [p1, p2]})) == {
        "marked": 2
    }
    assert await new_ids() == [p3]
    assert _ok(await client.post(seen, headers=admin, json={"ids": [p1, p2]})) == {
        "marked": 0
    }
    assert _ok(  # 없는 id 는 빠지고, 겹친 id 는 하나로
        await client.post(seen, headers=admin, json={"ids": [p3, LARGEST, p3]})
    ) == {"marked": 1}
    assert await new_ids() == []
    for ids in ([], list(range(1, 502))):
        body = problem_of(
            await client.post(seen, headers=admin, json={"ids": ids}), 422
        )
        assert locs(body) == [["body", "ids"]], len(ids)
    body = problem_of(
        await client.post(seen, headers=admin, json={"ids": [OVERFLOW]}), 422
    )
    assert locs(body) == [["body", "ids", 0]]

    listed = {
        i["id"]: i
        for i in _ok(await client.get(f"{ADMIN}/photos", headers=admin))["items"]
    }
    download = f"{ADMIN}/photos:download"
    body = _ok(
        await client.post(download, headers=admin, json={"ids": [p2, p1, p2, LARGEST]})
    )
    assert body == {
        "items": [  # 준 차례 · 겹친 id 는 하나
            {
                "id": p2,
                "href": listed[p2]["href"],
                "filename": "A사_20261102_1일차_01.jpg",
            },
            {
                "id": p1,
                "href": listed[p1]["href"],
                "filename": "A사_20261102_1일차_02.png",
            },
        ],
        "missing": [LARGEST],
    }
    got = await client.get(body["items"][0]["href"], headers=admin)
    assert (got.status_code, got.content) == (200, p2_bytes)
    for ids in ([], list(range(1, 102))):
        body = problem_of(
            await client.post(download, headers=admin, json={"ids": ids}), 422
        )
        assert locs(body) == [["body", "ids"]], len(ids)
    for path in (seen, download):
        problem_of(
            await client.post(path, headers=me.headers, json={"ids": [p1]}),
            403,
            "/problems/forbidden",
        )
    assert (
        await count(db_session, AuditLog) == audits
    )  # 확인 표시·내려받기 목록은 audit 없음
