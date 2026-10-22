"""관리자 세션 첨부(POST /v1/admin/sessions/{id}/attachments · DELETE /v1/admin/attachments/{id}), T2b 계획 결정 viii·ix·xii.

판정 순서: 401 → 403 → 404(세션) → 411 · 413(Content-Length) → 400(깨진 폼) → 422(모양) → 501(저장소) → 413(실제 크기)
→ 422(%PDF- 아님) → 201. 소유자(세션·섹션·강의) 삭제는 첨부와 그 stored_file 행을 같은 트랜잭션에서 먼저 지운다.
저장소 루트가 필요한 시험은 app.state.settings 를 file_store_root=tmp_path 로 바꾼다(T1 files 시험 전례).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import AuditLog, SessionAttachment, StoredFile
from tests.fixtures.courses import admin_headers, open_test_course
from tests.fixtures.enter import PDF, add_pdf, add_section, add_session

ADMIN = "/v1/admin"
MIB = 1024 * 1024


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    return (
        await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
    )


def _problem(r: httpx.Response, status: int, type_: str | None = None) -> dict:
    assert r.status_code == status, (r.status_code, r.text)
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    if type_ is not None:
        assert body["type"] == type_, body
    return body


async def _setup(
    client: httpx.AsyncClient, session: AsyncSession
) -> tuple[dict[str, str], int, int]:
    """(관리자 헤더, 강의 id, 세션 id)."""
    _, auth = await admin_headers(session)
    course, _ = await open_test_course(session)
    sid = await add_session(client, auth, course.id, day_no=1, slot=1, is_open=True)
    return auth, course.id, sid


async def _nothing_written(session: AsyncSession) -> None:
    assert await _count(session, SessionAttachment) == 0
    assert await _count(session, StoredFile) == 0
    assert (
        await _count(session, AuditLog, AuditLog.target_type == "session_attachment")
        == 0
    )


async def test_admin_attachment_pdf_upload_201(
    client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    auth, _, sid = await _setup(client, db_session)
    # 올린 사람이 준 content_type 은 쓰지 않는다
    r = await add_pdf(client, auth, sid, PDF, content_type="text/html")
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["kind"], body["title"], body["size"]) == (
        "pdf",
        "1교시 강의안",
        len(PDF),
    )
    files = (await db_session.execute(select(StoredFile))).scalars().all()
    assert len(files) == 1
    stored = files[0]
    assert (stored.owner_kind, stored.owner_id) == ("session_attachment", body["id"])
    assert (stored.content_type, stored.size) == ("application/pdf", len(PDF))
    file_id = await db_session.scalar(
        select(SessionAttachment.file_id).where(SessionAttachment.id == body["id"])
    )
    assert file_id == stored.id
    assert body["href"] == f"/v1/files/{stored.key}"
    got = await client.get(body["href"], headers=auth)
    assert got.status_code == 200 and got.content == PDF
    audit = (
        await db_session.execute(
            select(
                AuditLog.action, AuditLog.actor, AuditLog.target_id, AuditLog.detail
            ).where(AuditLog.target_type == "session_attachment")
        )
    ).all()
    assert [tuple(a) for a in audit] == [
        (
            "session_attachment.create",
            audit[0].actor,
            str(body["id"]),
            {"session_id": sid, "kind": "pdf"},
        )
    ]
    assert audit[0].actor.startswith("admin:")


async def test_admin_attachment_link_201(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 링크는 파일 저장소가 없어도 된다. urlencoded 폼도 받는다
    auth, _, sid = await _setup(client, db_session)
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={
            "kind": "link",
            "title": "참고",
            "description": "  읽을거리 ",
            "url": "https://example.com/a?b=1",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json() == {
        "id": r.json()["id"],
        "kind": "link",
        "title": "참고",
        "description": "읽을거리",
        "href": "https://example.com/a?b=1",
        "size": None,
    }
    second = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        files={
            "kind": (None, "link"),
            "title": (None, "둘째"),
            "url": (None, "http://example.com/b"),
        },
    )
    assert second.status_code == 201, second.text
    sorts = (
        await db_session.scalars(
            select(SessionAttachment.sort)
            .where(SessionAttachment.session_id == sid)
            .order_by(SessionAttachment.id)
        )
    ).all()
    assert list(sorts) == [0, 1]  # 끝에 붙는다
    assert await _count(db_session, StoredFile) == 0


async def test_admin_attachment_not_pdf_422(
    client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    auth, _, sid = await _setup(client, db_session)
    body = _problem(await add_pdf(client, auth, sid, b"hello, not a pdf"), 422)
    assert [v["loc"] for v in body["violations"]] == [["body", "file"]]
    # file 파트 없는 pdf · 모르는 kind · 빈 제목도 422
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={"kind": "pdf", "title": "x"},
    )
    assert [v["loc"] for v in _problem(r, 422)["violations"]] == [["body", "file"]]
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={"kind": "image", "title": "x"},
    )
    assert [v["loc"] for v in _problem(r, 422)["violations"]] == [["body", "kind"]]
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={"kind": "link", "title": " ", "url": "https://example.com"},
    )
    assert [v["loc"] for v in _problem(r, 422)["violations"]] == [["body", "title"]]
    await _nothing_written(db_session)


async def test_admin_attachment_description_control_char_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # description 도 title 과 같이 제어 문자를 422 로 막는다(psycopg 로 넘기지 않는다)
    auth, _, sid = await _setup(client, db_session)
    for description in ("설명\x07", "\u0001설명", "가\x00나"):
        r = await client.post(
            f"{ADMIN}/sessions/{sid}/attachments",
            headers=auth,
            data={
                "kind": "link",
                "title": "참고",
                "description": description,
                "url": "https://example.com/a",
            },
        )
        body = _problem(r, 422)
        assert [v["loc"] for v in body["violations"]] == [["body", "description"]]
    await _nothing_written(db_session)


async def test_admin_attachment_link_scheme_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    auth, _, sid = await _setup(client, db_session)
    for url in (
        "javascript:alert(1)",
        "ftp://example.com/a",
        "https://",
        "example.com/a",
        "https://exa mple.com",
        None,
    ):
        data = {"kind": "link", "title": "참고"}
        if url is not None:
            data["url"] = url
        r = await client.post(
            f"{ADMIN}/sessions/{sid}/attachments", headers=auth, data=data
        )
        assert [v["loc"] for v in _problem(r, 422)["violations"]] == [
            ["body", "url"]
        ], url
    long = "https://example.com/" + "a" * 2030  # 2050자
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={"kind": "link", "title": "참고", "url": long},
    )
    _problem(r, 422)
    await _nothing_written(db_session)


async def test_admin_attachment_too_large_413(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    app.state.settings = Settings(file_store_root=tmp_path, attachment_pdf_max_mb=1)
    auth, _, sid = await _setup(client, db_session)
    # 실제 크기: 본문은 상한 + 1MiB 안이지만 파일이 1MiB 를 넘는다
    just_over = PDF + b"0" * (MIB - len(PDF) + 1)
    _problem(await add_pdf(client, auth, sid, just_over), 413)
    # Content-Length 가 상한 + 1MiB 를 넘으면 본문을 읽지 않고 413
    _problem(await add_pdf(client, auth, sid, PDF + b"0" * (2 * MIB)), 413)
    await _nothing_written(db_session)
    assert not any(p.is_file() for p in tmp_path.rglob("*"))  # 바이트도 쓰지 않았다
    # 딱 상한은 받는다
    exact = PDF + b"0" * (MIB - len(PDF))
    assert (await add_pdf(client, auth, sid, exact)).status_code == 201


async def test_admin_attachment_without_length_411(
    client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    auth, _, sid = await _setup(client, db_session)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"kind=link&title=x&url=https%3A%2F%2Fexample.com"

    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers={**auth, "content-type": "application/x-www-form-urlencoded"},
        content=chunks(),
    )
    assert "content-length" not in r.request.headers
    _problem(r, 411)
    await _nothing_written(db_session)


async def test_admin_attachment_bad_multipart_400(
    client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    auth, _, sid = await _setup(client, db_session)
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers={**auth, "content-type": "multipart/form-data"},
        content=b'--x\r\nContent-Disposition: form-data; name="kind"\r\n\r\npdf\r\n--x--\r\n',
    )
    _problem(r, 400, "/problems/bad-request")
    # 파일 파트가 둘이면(max_files=1) 역시 400
    r = await client.post(
        f"{ADMIN}/sessions/{sid}/attachments",
        headers=auth,
        data={"kind": "pdf", "title": "x"},
        files=[
            ("file", ("a.pdf", PDF, "application/pdf")),
            ("file", ("b.pdf", PDF, "application/pdf")),
        ],
    )
    _problem(r, 400, "/problems/bad-request")
    await _nothing_written(db_session)


async def test_admin_attachment_store_root_unset_501(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    auth, _, sid = await _setup(client, db_session)
    body = _problem(await add_pdf(client, auth, sid), 501, "/problems/not_configured")
    assert body["missing"] == ["CLASSFIT_FILE_STORE_ROOT"]
    await _nothing_written(db_session)
    # 없는 세션은 저장소 판정보다 앞의 404
    _problem(await add_pdf(client, auth, 999_999_999), 404)


async def test_admin_attachment_delete_removes_file_row(
    client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    auth, _, sid = await _setup(client, db_session)
    up = await add_pdf(client, auth, sid)
    assert up.status_code == 201, up.text
    aid, href = up.json()["id"], up.json()["href"]
    r = await client.delete(f"{ADMIN}/attachments/{aid}", headers=auth)
    assert r.status_code == 204, r.text
    assert await _count(db_session, SessionAttachment) == 0
    assert await _count(db_session, StoredFile) == 0
    _problem(await client.get(href, headers=auth), 404)
    audit = (
        await db_session.execute(
            select(AuditLog.action, AuditLog.target_id, AuditLog.detail)
            .where(AuditLog.target_type == "session_attachment")
            .order_by(AuditLog.id)
        )
    ).all()
    assert [tuple(a) for a in audit] == [
        ("session_attachment.create", str(aid), {"session_id": sid, "kind": "pdf"}),
        ("session_attachment.delete", str(aid), {"session_id": sid, "kind": "pdf"}),
    ]
    _problem(await client.delete(f"{ADMIN}/attachments/{aid}", headers=auth), 404)


async def test_admin_attachment_owner_delete_removes_file_rows(
    client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _, auth = await admin_headers(db_session)

    async def course_with_pdf(title: str) -> tuple[int, int, int]:
        course, _ = await open_test_course(db_session, title=title)
        sec = await add_section(client, auth, course.id)
        sid = await add_session(client, auth, course.id, section_id=sec, is_open=True)
        r = await add_pdf(client, auth, sid, PDF + title.encode())
        assert r.status_code == 201, r.text
        return course.id, sec, sid

    async def files_of(sid: int) -> int:
        owned = select(SessionAttachment.id).where(SessionAttachment.session_id == sid)
        return await _count(
            db_session,
            StoredFile,
            StoredFile.owner_kind == "session_attachment",
            StoredFile.owner_id.in_(owned),
        )

    kept_cid, _, kept_sid = await course_with_pdf("남는 강의")
    kept_files = await _count(db_session, StoredFile)
    assert kept_files == 1

    cid, _, sid = await course_with_pdf("세션 삭제")
    assert (
        await client.delete(f"{ADMIN}/sessions/{sid}", headers=auth)
    ).status_code == 204
    assert (
        await _count(db_session, SessionAttachment, SessionAttachment.session_id == sid)
        == 0
    )

    cid, sec, sid = await course_with_pdf("섹션 삭제")
    r = await client.delete(f"{ADMIN}/courses/{cid}/sections/{sec}", headers=auth)
    assert r.status_code == 204, r.text
    assert (
        await _count(db_session, SessionAttachment, SessionAttachment.session_id == sid)
        == 0
    )

    cid, _, sid = await course_with_pdf("강의 삭제")
    assert (
        await client.delete(f"{ADMIN}/courses/{cid}", headers=auth)
    ).status_code == 204
    assert (
        await _count(db_session, SessionAttachment, SessionAttachment.session_id == sid)
        == 0
    )

    # 지운 소유자의 파일 행은 0, 남는 강의의 첨부·파일 행은 그대로
    assert await _count(db_session, StoredFile) == kept_files
    assert await files_of(kept_sid) == 1
    assert await _count(db_session, SessionAttachment) == 1
    assert kept_cid
