"""강사 첨부 넣기·고치기·바꾸기·지우기·목록과 파일 열람(T6 계획 결정 i~xii · 증명 1·2·5~12).

쓰기는 그 세션의 현재 담당 강사만이다(남의 세션·미배정 403, 없는 것 404, 경로 id 2**63 이상 422). 종류는 파일 이름의
확장자로 정하고 첫 바이트가 그 모양이어야 한다. content_type 은 확장자 표의 값이다. 교체는 같은 행의 파일만 바꾸고 옛
파일 행을 같은 트랜잭션에서 지워 옛 href 가 404 다. HTML 패키지(zip)는 범위 판정 뒤 501 이다. 강사의 파일 열람은 범위
강의의 내 세션 ∨ 열린 세션이다. 저장소 루트가 필요한 시험은 app.state.settings 를 file_store_root=tmp_path 로 바꾼다.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import AuditLog, SessionAttachment, StoredFile
from classfit.service.files.store import href_for
from tests.fixtures.assign import (
    LINK_URL,
    PDF,
    approved,
    capability_files,
    course_with_section,
    pool_session,
)
from tests.fixtures.courses import admin_headers, learner_headers, open_test_course
from tests.fixtures.enter import add_pdf, add_session
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.my_attachments import (
    MY_ATTACHMENT_KEYS,
    SAMPLES,
    instructor_session,
    link,
    upload,
)
from tests.fixtures.pool import make_pool_course

ADMIN = "/v1/admin"
ME = "/v1/me"
MIB = 1024 * 1024
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422
OOXML = "application/vnd.openxmlformats-officedocument."
# 확장자 → (kind, content_type). 결정 iii 의 표를 시험이 따로 적는다(규칙 모듈의 표를 읽지 않는다)
KINDS = {
    ".pdf": ("pdf", "application/pdf"),
    ".pptx": ("office", OOXML + "presentationml.presentation"),
    ".docx": ("office", OOXML + "wordprocessingml.document"),
    ".xlsx": ("office", OOXML + "spreadsheetml.sheet"),
    ".csv": ("office", "text/csv"),
    ".zip": ("html", "application/zip"),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".jpeg": ("image", "image/jpeg"),
}


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _list_url(session_id: int) -> str:
    return f"{ME}/sessions/{session_id}/attachments"


def _one_url(attachment_id: int) -> str:
    return f"{ME}/attachments/{attachment_id}"


async def _replace(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    attachment_id: int,
    name: str,
    data: bytes,
) -> httpx.Response:
    return await client.post(
        f"{ME}/attachments/{attachment_id}:replace",
        headers=headers,
        files={"file": (name, data, "application/octet-stream")},
    )


async def _assign(
    client: httpx.AsyncClient, auth: dict[str, str], session_id: int, iid: int | None
) -> None:
    r = await client.patch(
        f"{ADMIN}/sessions/{session_id}", headers=auth, json={"instructor_id": iid}
    )
    assert r.status_code == 200, r.text


async def _listed(
    client: httpx.AsyncClient, headers: dict[str, str], session_id: int
) -> list[dict[str, Any]]:
    r = await client.get(_list_url(session_id), headers=headers)
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


async def _written(session: AsyncSession) -> tuple[int, int, int]:
    """(첨부 행, 파일 행, 첨부 audit) 수."""
    return (
        await count(session, SessionAttachment),
        await count(session, StoredFile),
        await count(session, AuditLog, AuditLog.target_type == "session_attachment"),
    )


async def _stored_of(session: AsyncSession, href: str) -> StoredFile:
    key = href.rsplit("/", 1)[-1]
    return (
        await session.execute(select(StoredFile).where(StoredFile.key == key))
    ).scalar_one()


async def _audits(session: AsyncSession, action: str) -> list[tuple[Any, ...]]:
    """그 action 의 (actor, target_id, detail), id 순."""
    rows = await session.execute(
        select(AuditLog.actor, AuditLog.target_id, AuditLog.detail)
        .where(AuditLog.action == action)
        .order_by(AuditLog.id)
    )
    return [tuple(r) for r in rows]


async def _copy_session(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin: dict[str, str],
    root: Path | None,
    *,
    instructor_id: int,
    section_id: int,
    kinds: tuple[str, ...],
) -> int:
    """그 강사의 AX 역량 원본(kinds)이 있는 풀 세션을 그 강사에게 배정해 기본 강의안 사본이 붙은 세션 id."""
    ax = await make_pool_course(db_session, source="ax")
    await capability_files(
        db_session, root, instructor_id=instructor_id, pool_id=ax.id, kinds=kinds
    )
    pooled = await pool_session(db_session, section_id=section_id, pool_id=ax.id)
    await _assign(client, admin, pooled.id, instructor_id)
    return pooled.id


async def test_attachment_upload_kinds_201(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    me = await instructor_session(db_session, app.state.settings, email="x@example.com")
    cases = [
        (f"자료{ext}", SAMPLES[ext], kind, content_type)
        for ext, (kind, content_type) in KINDS.items()
    ]
    cases.append(
        ("보고서.PDF", SAMPLES[".pdf"] + b"%upper\n", "pdf", "application/pdf")
    )
    made: list[tuple[dict[str, Any], bytes]] = []
    for n, (name, data, kind, content_type) in enumerate(cases):
        # upload 는 파트 content_type 을 application/octet-stream 으로 보낸다 — 저장값은 확장자 표의 값
        r = await upload(
            client, me.headers, me.session_id, name, data, title=f"자료 {n}"
        )
        assert r.status_code == 201, (name, r.text)
        body = r.json()
        assert set(body) == MY_ATTACHMENT_KEYS, name
        assert (body["kind"], body["title"], body["origin"], body["size"]) == (
            kind,
            f"자료 {n}",
            None,
            len(data),
        ), name
        stored = await _stored_of(db_session, body["href"])
        assert (
            stored.content_type,
            stored.owner_kind,
            stored.owner_id,
            stored.size,
        ) == (content_type, "session_attachment", body["id"], len(data)), name
        file_id = await db_session.scalar(
            select(SessionAttachment.file_id).where(SessionAttachment.id == body["id"])
        )
        assert file_id == stored.id, name
        made.append((body, data))

    assert await _audits(db_session, "session_attachment.create") == [
        (
            f"instructor:{me.instructor_id}",
            str(body["id"]),
            {"session_id": me.session_id, "kind": body["kind"]},
        )
        for body, _ in made
    ]
    listed = await _listed(client, me.headers, me.session_id)
    assert [i["id"] for i in listed] == [body["id"] for body, _ in made]
    for body, data in made:
        if (
            body["kind"] == "html"
        ):  # HTML 패키지는 열지 않는다(test_attachment_html_open_501)
            continue
        got = await client.get(body["href"], headers=me.headers)
        assert (got.status_code, got.content) == (200, data), body["href"]


async def test_attachment_upload_rejections(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    app.state.settings = Settings(file_store_root=tmp_path, attachment_image_max_mb=1)
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await instructor_session(db_session, settings, email="x@example.com")
    y, _ = await approved(db_session, settings, email="y@example.com")
    theirs = await add_session(
        client, admin, me.course_id, section_id=me.section_id, title="Y 세션"
    )
    await _assign(client, admin, theirs, y)
    nobody = await add_session(
        client, admin, me.course_id, section_id=me.section_id, title="미배정"
    )
    learner = await learner_headers(db_session, me.course_id)
    pdf = SAMPLES[".pdf"]
    before = await _written(db_session)

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

    for sid in (theirs, nobody):  # 남의 세션 · 미배정
        await rejected(
            await upload(client, me.headers, sid, "a.pdf", pdf),
            403,
            "/problems/forbidden",
        )
    await rejected(
        await upload(client, me.headers, LARGEST, "a.pdf", pdf),
        404,
        "/problems/not_found",
    )
    body = await rejected(
        await upload(client, me.headers, OVERFLOW, "a.pdf", pdf),
        422,
        loc=["path", "session_id"],
    )
    assert [v["type"] for v in body["violations"]] == ["less_than"]
    await rejected(
        await upload(client, learner, me.session_id, "a.pdf", pdf),
        403,
        "/problems/forbidden",
    )
    for name in ("run.exe", "그림.svg", "옛 슬라이드.ppt"):  # 받지 않는 확장자
        await rejected(
            await upload(client, me.headers, me.session_id, name, pdf),
            422,
            loc=["body", "file"],
        )
    await rejected(  # 확장자와 첫 바이트가 다름
        await upload(client, me.headers, me.session_id, "그림.png", pdf),
        422,
        loc=["body", "file"],
    )
    await rejected(
        await upload(client, me.headers, me.session_id, "표.csv", b"a,b\n1,\x00\n"),
        422,
        loc=["body", "file"],
    )
    await rejected(  # title 없음
        await client.post(
            _list_url(me.session_id),
            headers=me.headers,
            files={"file": ("a.pdf", pdf, "application/pdf")},
        ),
        422,
        loc=["body", "title"],
    )
    await rejected(  # file 파트 없음
        await client.post(
            _list_url(me.session_id), headers=me.headers, data={"title": "x"}
        ),
        422,
        loc=["body", "file"],
    )
    image = SAMPLES[".png"]
    big = image + b"\0" * (MIB + 1 - len(image))  # 이미지 상한 1MiB + 1바이트
    await rejected(await upload(client, me.headers, me.session_id, "큰.png", big), 413)

    async def chunks() -> AsyncIterator[bytes]:
        yield b'--x\r\nContent-Disposition: form-data; name="title"\r\n\r\nx\r\n--x--\r\n'

    r = await client.post(
        _list_url(me.session_id),
        headers={**me.headers, "content-type": "multipart/form-data; boundary=x"},
        content=chunks(),
    )
    assert "content-length" not in r.request.headers
    await rejected(r, 411)
    assert not any(p.is_file() for p in tmp_path.rglob("*"))  # 바이트도 쓰지 않았다

    app.state.settings = Settings(attachment_image_max_mb=1)  # 저장소 미구성
    body = await rejected(
        await upload(client, me.headers, me.session_id, "a.pdf", pdf),
        501,
        "/problems/not_configured",
    )
    assert body["missing"] == ["CLASSFIT_FILE_STORE_ROOT"]


async def test_attachment_link_201_and_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 링크는 파일 저장소가 없어도 된다
    settings = app.state.settings
    me = await instructor_session(db_session, settings, email="x@example.com")
    _, y_auth = await approved(db_session, settings, email="y@example.com")
    r = await link(
        client, me.headers, me.session_id, " https://example.com/a?b=1 ", title="참고"
    )
    assert r.status_code == 201, r.text
    assert r.json() == {
        "id": r.json()["id"],
        "kind": "link",
        "title": "참고",
        "description": None,
        "href": "https://example.com/a?b=1",
        "size": None,
        "origin": None,
    }
    assert await _audits(db_session, "session_attachment.create") == [
        (
            f"instructor:{me.instructor_id}",
            str(r.json()["id"]),
            {"session_id": me.session_id, "kind": "link"},
        )
    ]
    before = await _written(db_session)
    url = _list_url(me.session_id) + ":link"
    for payload, loc, type_ in (
        ({"title": "x", "url": "ftp://example.com/a"}, ["body", "url"], None),
        ({"title": "x", "url": "javascript:alert(1)"}, ["body", "url"], None),
        (
            {"title": "x", "url": "https://example.com/a", "kind": "pdf"},
            ["body", "kind"],
            "extra_forbidden",
        ),
        ({"url": "https://example.com/a"}, ["body", "title"], "missing"),
        ({"title": " ", "url": "https://example.com/a"}, ["body", "title"], None),
    ):
        body = problem_of(await client.post(url, headers=me.headers, json=payload), 422)
        assert locs(body) == [loc], payload
        if type_ is not None:
            assert [v["type"] for v in body["violations"]] == [type_], payload
    problem_of(
        await link(client, y_auth, me.session_id, "https://example.com/y"),
        403,
        "/problems/forbidden",
    )
    assert await _written(db_session) == before


async def test_attachment_html_open_501(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _, admin = await admin_headers(db_session)
    me = await instructor_session(db_session, app.state.settings, email="x@example.com")
    package = await upload(
        client, me.headers, me.session_id, "강의.zip", SAMPLES[".zip"]
    )
    pdf = await upload(client, me.headers, me.session_id, "강의.pdf", SAMPLES[".pdf"])
    assert (package.status_code, pdf.status_code) == (201, 201), (
        package.text,
        pdf.text,
    )
    assert package.json()["kind"] == "html"
    r = await client.patch(
        f"{ME}/sessions/{me.session_id}", headers=me.headers, json={"is_open": True}
    )
    assert r.status_code == 200, r.text
    learner = await learner_headers(db_session, me.course_id)
    other, _ = await open_test_course(db_session, title="다른 강의")
    stranger = await learner_headers(db_session, other.id)

    href = package.json()["href"]
    for headers in (me.headers, learner, admin):  # 주체를 가리지 않는다
        problem_of(
            await client.get(href, headers=headers), 501, "/problems/not-implemented"
        )
    # 범위 판정이 먼저다 — 남의 강의 수강생은 있는지도 모른다
    problem_of(await client.get(href, headers=stranger), 403, "/problems/forbidden")
    got = await client.get(pdf.json()["href"], headers=learner)
    assert (got.status_code, got.content) == (200, SAMPLES[".pdf"])


async def test_attachment_replace_old_href_404(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await instructor_session(db_session, settings, email="x@example.com")
    _, y_auth = await approved(db_session, settings, email="y@example.com")
    old, new = SAMPLES[".pdf"] + b"%v1\n", SAMPLES[".pdf"] + b"%v2\n"
    first = await upload(client, me.headers, me.session_id, "앞.pdf", SAMPLES[".pdf"])
    target = await upload(
        client, me.headers, me.session_id, "강의안.pdf", old, title="강의안"
    )
    last = await link(client, me.headers, me.session_id, "https://example.com/z")
    for r in (first, target, last):
        assert r.status_code == 201, r.text
    aid, old_href = target.json()["id"], target.json()["href"]

    r = await _replace(client, me.headers, aid, "새 강의안.pdf", new)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == MY_ATTACHMENT_KEYS
    assert (body["id"], body["kind"], body["title"], body["size"], body["origin"]) == (
        aid,
        "pdf",
        "강의안",
        len(new),
        None,
    )
    assert body["href"] != old_href
    problem_of(
        await client.get(old_href, headers=me.headers), 404, "/problems/not_found"
    )
    got = await client.get(body["href"], headers=me.headers)
    assert (got.status_code, got.content) == (200, new)
    listed = await _listed(client, me.headers, me.session_id)
    assert [i["id"] for i in listed] == [
        first.json()["id"],
        aid,
        last.json()["id"],
    ]  # 자리도 그대로
    assert (
        await count(
            db_session,
            StoredFile,
            StoredFile.owner_kind == "session_attachment",
            StoredFile.owner_id == aid,
        )
        == 1
    )
    assert await _audits(db_session, "session_attachment.update") == [
        (
            f"instructor:{me.instructor_id}",
            str(aid),
            {"session_id": me.session_id, "kind": "pdf", "fields": ["file"]},
        )
    ]

    before = await _written(db_session)
    body = problem_of(
        await _replace(client, me.headers, aid, "그림.png", SAMPLES[".png"]), 422
    )
    assert locs(body) == [["body", "file"]]  # 종류를 바꾸지 않는다
    problem_of(
        await _replace(client, me.headers, last.json()["id"], "a.pdf", new),
        409,
        "/problems/conflict",
    )
    problem_of(
        await _replace(client, y_auth, aid, "a.pdf", new), 403, "/problems/forbidden"
    )
    problem_of(
        await _replace(client, me.headers, LARGEST, "a.pdf", new),
        404,
        "/problems/not_found",
    )
    body = problem_of(await _replace(client, me.headers, OVERFLOW, "a.pdf", new), 422)
    assert locs(body) == [["path", "attachment_id"]]
    assert await _written(db_session) == before

    # 기본 강의안 사본을 바꾸면 더는 사본이 아니다
    copied = await _copy_session(
        client,
        db_session,
        admin,
        store_root,
        instructor_id=me.instructor_id,
        section_id=me.section_id,
        kinds=("pdf",),
    )
    [copy] = await _listed(client, me.headers, copied)
    assert (copy["kind"], copy["origin"]) == ("pdf", "capability_file")
    source_key = await db_session.scalar(
        select(StoredFile.key).where(StoredFile.owner_kind == "capability_file")
    )
    assert source_key is not None
    r = await _replace(client, me.headers, copy["id"], "내 강의안.pdf", new + b"%v3\n")
    assert r.status_code == 200, r.text
    assert r.json()["origin"] is None
    assert [
        (i["id"], i["origin"]) for i in await _listed(client, me.headers, copied)
    ] == [(copy["id"], None)]
    # 사본의 파일만 바뀐다 — 역량 원본 파일 행과 바이트는 그대로 열린다
    got = await client.get(href_for(source_key), headers=me.headers)
    assert (got.status_code, got.content) == (200, PDF)


async def test_attachment_patch_title_position(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await instructor_session(db_session, settings, email="x@example.com")
    _, y_auth = await approved(db_session, settings, email="y@example.com")
    made = [
        await upload(client, me.headers, me.session_id, "가.pdf", SAMPLES[".pdf"]),
        await link(client, me.headers, me.session_id, "https://example.com/b"),
        await link(client, me.headers, me.session_id, "https://example.com/c"),
    ]
    for r in made:
        assert r.status_code == 201, r.text
    a, b, c = (r.json()["id"] for r in made)

    async def patch(
        aid: int, payload: dict[str, Any], headers: dict[str, str] = me.headers
    ) -> httpx.Response:
        return await client.patch(_one_url(aid), headers=headers, json=payload)

    async def order() -> list[int]:
        return [i["id"] for i in await _listed(client, me.headers, me.session_id)]

    r = await patch(c, {"position": 0})
    assert r.status_code == 200, r.text
    assert set(r.json()) == MY_ATTACHMENT_KEYS
    assert await order() == [c, a, b]
    assert (await patch(a, {"position": 99})).status_code == 200  # 넘치면 끝
    assert await order() == [c, b, a]
    r = await patch(a, {"title": " 새 제목 ", "description": "설명"})
    assert r.status_code == 200, r.text
    assert (r.json()["title"], r.json()["description"]) == ("새 제목", "설명")
    r = await patch(a, {"description": None})  # null 은 지운다
    assert (r.status_code, r.json()["description"]) == (200, None)
    r = await patch(b, {"url": "https://example.com/b2"})
    assert (r.status_code, r.json()["href"]) == (200, "https://example.com/b2")
    assert [
        sorted(detail["fields"])
        for _, _, detail in await _audits(db_session, "session_attachment.update")
    ] == [
        ["position"],
        ["position"],
        ["description", "title"],
        ["description"],
        ["url"],
    ]

    before = await _written(db_session)
    rows = (
        await db_session.execute(
            select(
                SessionAttachment.id,
                SessionAttachment.title,
                SessionAttachment.description,
                SessionAttachment.url,
                SessionAttachment.sort,
            ).order_by(SessionAttachment.id)
        )
    ).all()
    problem_of(
        await patch(a, {"url": "https://example.com/x"}), 409, "/problems/conflict"
    )  # pdf 에 url
    body = problem_of(await patch(a, {"kind": "link"}), 422)
    assert locs(body) == [["body", "kind"]]
    assert [v["type"] for v in body["violations"]] == ["extra_forbidden"]
    for bad in (
        {"title": None},
        {"url": None},
        {"position": None},
        {"position": -1},
        {"title": " "},
        {"url": "ftp://example.com/a"},
    ):
        problem_of(await patch(b, bad), 422)
    r = await patch(a, {"title": "새 제목"})  # 같은 값
    assert r.status_code == 200, r.text
    problem_of(await patch(a, {"title": "남의 것"}, y_auth), 403, "/problems/forbidden")
    problem_of(await patch(LARGEST, {"title": "x"}), 404, "/problems/not_found")
    assert await _written(db_session) == before
    assert (
        await db_session.execute(
            select(
                SessionAttachment.id,
                SessionAttachment.title,
                SessionAttachment.description,
                SessionAttachment.url,
                SessionAttachment.sort,
            ).order_by(SessionAttachment.id)
        )
    ).all() == rows

    # 복사된 링크: 정규화한 주소가 같거나 제목만 바꾸면 사본 그대로, 다른 주소면 사본이 아니다
    copied = await _copy_session(
        client,
        db_session,
        admin,
        None,
        instructor_id=me.instructor_id,
        section_id=me.section_id,
        kinds=("link",),
    )
    [copy] = await _listed(client, me.headers, copied)
    assert (copy["kind"], copy["origin"], copy["href"]) == (
        "link",
        "capability_file",
        LINK_URL,
    )
    updates = len(await _audits(db_session, "session_attachment.update"))
    r = await patch(copy["id"], {"url": f" {LINK_URL} "})
    assert (r.status_code, r.json()["origin"], r.json()["href"]) == (
        200,
        "capability_file",
        LINK_URL,
    )
    assert len(await _audits(db_session, "session_attachment.update")) == updates
    r = await patch(copy["id"], {"title": "새 이름"})
    assert (r.status_code, r.json()["origin"]) == (200, "capability_file")
    r = await patch(copy["id"], {"url": "https://example.com/other"})
    assert (r.status_code, r.json()["origin"], r.json()["href"]) == (
        200,
        None,
        "https://example.com/other",
    )
    assert [i["origin"] for i in await _listed(client, me.headers, copied)] == [None]
    assert (await _audits(db_session, "session_attachment.update"))[-1] == (
        f"instructor:{me.instructor_id}",
        str(copy["id"]),
        {"session_id": copied, "kind": "link", "fields": ["url"]},
    )


async def test_attachment_delete_204(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    me = await instructor_session(db_session, settings, email="x@example.com")
    _, y_auth = await approved(db_session, settings, email="y@example.com")

    async def gone(aid: int) -> None:
        assert (
            await count(db_session, SessionAttachment, SessionAttachment.id == aid) == 0
        )
        assert (
            await count(
                db_session,
                StoredFile,
                StoredFile.owner_kind == "session_attachment",
                StoredFile.owner_id == aid,
            )
            == 0
        )

    mine = await upload(client, me.headers, me.session_id, "가.pdf", SAMPLES[".pdf"])
    assert mine.status_code == 201, mine.text
    r = await client.delete(_one_url(mine.json()["id"]), headers=me.headers)
    assert r.status_code == 204, r.text
    await gone(mine.json()["id"])
    problem_of(
        await client.get(mine.json()["href"], headers=me.headers),
        404,
        "/problems/not_found",
    )

    # 관리자가 T2b 로 넣은 첨부도 담당 강사가 지운다
    by_admin = await add_pdf(client, admin, me.session_id, PDF + b"% admin\n")
    assert by_admin.status_code == 201, by_admin.text
    r = await client.delete(_one_url(by_admin.json()["id"]), headers=me.headers)
    assert r.status_code == 204, r.text
    await gone(by_admin.json()["id"])

    # 기본 강의안 사본을 지워도 원본 파일은 남는다
    ax = await make_pool_course(db_session, source="ax")
    [source_id] = await capability_files(
        db_session,
        store_root,
        instructor_id=me.instructor_id,
        pool_id=ax.id,
        kinds=("pdf",),
    )
    pooled = await pool_session(db_session, section_id=me.section_id, pool_id=ax.id)
    await _assign(client, admin, pooled.id, me.instructor_id)
    [copy] = await _listed(client, me.headers, pooled.id)
    assert copy["origin"] == "capability_file"
    r = await client.delete(_one_url(copy["id"]), headers=me.headers)
    assert r.status_code == 204, r.text
    await gone(copy["id"])
    source_key = await db_session.scalar(
        select(StoredFile.key).where(
            StoredFile.owner_kind == "capability_file",
            StoredFile.owner_id == source_id,
        )
    )
    assert source_key is not None
    got = await client.get(href_for(source_key), headers=me.headers)
    assert (got.status_code, got.content) == (200, PDF)

    kept = await link(client, me.headers, me.session_id, "https://example.com/a")
    kept_id = kept.json()["id"]
    before = await _written(db_session)
    problem_of(
        await client.delete(_one_url(kept_id), headers=y_auth),
        403,
        "/problems/forbidden",
    )
    problem_of(
        await client.delete(_one_url(LARGEST), headers=me.headers),
        404,
        "/problems/not_found",
    )
    body = problem_of(await client.delete(_one_url(OVERFLOW), headers=me.headers), 422)
    assert locs(body) == [["path", "attachment_id"]]
    assert await _written(db_session) == before
    actor = f"instructor:{me.instructor_id}"
    assert await _audits(db_session, "session_attachment.delete") == [
        (actor, str(mine.json()["id"]), {"session_id": me.session_id, "kind": "pdf"}),
        (
            actor,
            str(by_admin.json()["id"]),
            {"session_id": me.session_id, "kind": "pdf"},
        ),
        (actor, str(copy["id"]), {"session_id": pooled.id, "kind": "pdf"}),
    ]


async def test_attachment_list_own_session_with_origin(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    course, section = await course_with_section(db_session)
    copied = await _copy_session(
        client,
        db_session,
        admin,
        store_root,
        instructor_id=x,
        section_id=section.id,
        kinds=("pdf",),
    )
    theirs = await add_session(
        client, admin, course.id, section_id=section.id, title="Y 세션"
    )
    await _assign(client, admin, theirs, y)
    mine = await upload(client, x_auth, copied, "내 강의안.pdf", SAMPLES[".pdf"])
    assert mine.status_code == 201, mine.text

    r = await client.get(_list_url(copied), headers=x_auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"items", "next_cursor", "has_more"}
    assert (body["next_cursor"], body["has_more"]) == (None, False)
    assert [set(i) for i in body["items"]] == [MY_ATTACHMENT_KEYS, MY_ATTACHMENT_KEYS]
    assert [(i["kind"], i["origin"]) for i in body["items"]] == [
        ("pdf", "capability_file"),  # 사본이 첫째
        ("pdf", None),
    ]
    assert body["items"][1]["id"] == mine.json()["id"]
    for item in body["items"]:
        assert (await client.get(item["href"], headers=x_auth)).status_code == 200

    problem_of(
        await client.get(_list_url(copied), headers=y_auth), 403, "/problems/forbidden"
    )
    problem_of(
        await client.get(_list_url(LARGEST), headers=x_auth), 404, "/problems/not_found"
    )
    assert await _listed(client, y_auth, theirs) == []


async def test_attachment_owner_kind_instructor_files(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    settings = app.state.settings
    _, admin = await admin_headers(db_session)
    x, x_auth = await approved(db_session, settings, email="x@example.com")
    y, y_auth = await approved(db_session, settings, email="y@example.com")
    z, z_auth = await approved(db_session, settings, email="z@example.com")
    course, section = await course_with_section(db_session)
    owners = {}
    for title, iid, is_open in (
        ("X 닫힘", x, False),
        ("Y 열림", y, True),
        ("Y 닫힘", y, False),
    ):
        sid = await add_session(
            client,
            admin,
            course.id,
            section_id=section.id,
            title=title,
            is_open=is_open,
        )
        await _assign(client, admin, sid, iid)
        owners[title] = sid
    other, other_section = await course_with_section(db_session, title="다른 강의")
    await _assign(
        client,
        admin,
        await add_session(client, admin, other.id, section_id=other_section.id),
        z,
    )
    hrefs = {}
    for title, auth in (("X 닫힘", x_auth), ("Y 열림", y_auth), ("Y 닫힘", y_auth)):
        r = await upload(
            client, auth, owners[title], "자료.pdf", SAMPLES[".pdf"] + title.encode()
        )
        assert r.status_code == 201, r.text
        hrefs[title] = r.json()["href"]

    async def opened(auth: dict[str, str]) -> dict[str, int]:
        return {
            title: (await client.get(href, headers=auth)).status_code
            for title, href in hrefs.items()
        }

    # 내 세션은 공개 전에도, 같은 강의 남의 세션은 열린 것만
    assert await opened(x_auth) == {"X 닫힘": 200, "Y 열림": 200, "Y 닫힘": 403}
    assert await opened(z_auth) == {"X 닫힘": 403, "Y 열림": 403, "Y 닫힘": 403}
    await _assign(client, admin, owners["X 닫힘"], y)  # X 의 그 강의 유일한 세션
    assert await opened(x_auth) == {"X 닫힘": 403, "Y 열림": 403, "Y 닫힘": 403}
    assert await opened(y_auth) == {"X 닫힘": 200, "Y 열림": 200, "Y 닫힘": 200}


async def test_attachment_cap_20_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    me = await instructor_session(db_session, app.state.settings, email="x@example.com")
    made = [
        await link(client, me.headers, me.session_id, f"https://example.com/{n}")
        for n in range(20)
    ]
    assert [r.status_code for r in made] == [201] * 20
    before = await _written(db_session)
    body = problem_of(
        await link(client, me.headers, me.session_id, "https://example.com/21"),
        409,
        "/problems/conflict",
    )
    assert body["limit"] == 20
    body = problem_of(
        await upload(client, me.headers, me.session_id, "a.pdf", SAMPLES[".pdf"]),
        409,
        "/problems/conflict",
    )
    assert body["limit"] == 20
    assert await _written(db_session) == before
    assert not any(
        p.is_file() for p in store_root.rglob("*")
    )  # 바이트를 읽기 전에 막는다
    r = await client.delete(_one_url(made[0].json()["id"]), headers=me.headers)
    assert r.status_code == 204, r.text
    r = await upload(client, me.headers, me.session_id, "a.pdf", SAMPLES[".pdf"])
    assert r.status_code == 201, r.text
