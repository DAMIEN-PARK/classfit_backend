"""강사 서류(PUT·DELETE /v1/me/documents/{type_id} · 관리자 열람), T3 계획 결정 ix·x · 증명 11·12·13.

판정 순서: 401 → 403 → 404(종류) → 411 · 413(Content-Length) → 400(깨진 폼) → 422(file 없음) → 501 → 413(실제 크기)
→ 422(%PDF- 아님) → 201 · 교체 200. stored_file.owner_id 는 강사 id 이고 /v1/files/{key} 는 본인 강사만 연다
(같은 id 의 관리자·수강생 토큰도 403). 관리자는 audit 끝점으로만 열고, 그 요청마다 audit 1행이다.
저장소 루트가 필요한 시험은 app.state.settings 를 file_store_root=tmp_path 로 바꾼다(T1·T2b 전례).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import AuditLog, InstructorDocument, StoredFile
from tests.fixtures.courses import _bearer, admin_headers, open_test_course
from tests.fixtures.instructors import (
    count,
    instructor_headers,
    locs,
    make_instructor,
    pdf_bytes,
    problem_of,
)

ME_DOCS = "/v1/me/documents"
EMAIL = "instructor-a@example.com"
MIB = 1024 * 1024


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


async def _put(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    type_id: str = "resume",
    data: bytes | None = None,
    content_type: str = "application/pdf",
) -> httpx.Response:
    payload = pdf_bytes() if data is None else data
    return await client.put(
        f"{ME_DOCS}/{type_id}",
        headers=headers,
        files={"file": ("a.pdf", payload, content_type)},
    )


async def _instructor(
    app: FastAPI, session: AsyncSession, email: str = EMAIL
) -> tuple[int, dict[str, str]]:
    iid = await make_instructor(session, app.state.settings, email=email)
    return iid, await instructor_headers(session, iid)


async def _nothing_written(session: AsyncSession, root: Path | None = None) -> None:
    assert await count(session, InstructorDocument) == 0
    assert await count(session, StoredFile) == 0
    if root is not None:
        assert not any(p.is_file() for p in root.rglob("*"))


def _view(iid: int, type_id: str = "resume") -> str:
    return f"/v1/admin/instructors/{iid}/documents/{type_id}"


async def test_instructor_document_put_creates_file_row_and_href(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    iid, auth = await _instructor(app, db_session)
    # 올린 사람이 준 content_type 은 쓰지 않는다
    r = await _put(client, auth, content_type="text/html")
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["type_id"], body["name"], body["required"], body["size"]) == (
        "resume",
        "이력서",
        True,
        len(pdf_bytes()),
    )
    files = (await db_session.execute(select(StoredFile))).scalars().all()
    assert len(files) == 1
    stored = files[0]
    assert (stored.owner_kind, stored.owner_id, stored.content_type) == (
        "instructor_document",
        iid,
        "application/pdf",
    )
    file_id = await db_session.scalar(
        select(InstructorDocument.file_id).where(
            InstructorDocument.instructor_id == iid
        )
    )
    assert file_id == stored.id
    assert body["href"] == f"/v1/files/{stored.key}"
    me = (await client.get("/v1/me", headers=auth)).json()
    resume = next(d for d in me["documents"] if d["type_id"] == "resume")
    assert resume["href"] == body["href"] and resume["submitted_at"]
    got = await client.get(body["href"], headers=auth)
    assert got.status_code == 200 and got.content == pdf_bytes()
    _, admin = await admin_headers(db_session)
    detail = (await client.get(f"/v1/admin/instructors/{iid}", headers=admin)).json()
    assert detail["documents_submitted"] == 1


async def test_instructor_document_put_replace_deletes_old_file_row(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _, auth = await _instructor(app, db_session)
    first = await _put(client, auth)
    assert first.status_code == 201, first.text
    newer = pdf_bytes() + b"% v2\n"
    second = await _put(client, auth, data=newer)
    assert second.status_code == 200, second.text
    assert second.json()["size"] == len(newer)
    assert second.json()["href"] != first.json()["href"]
    assert await count(db_session, StoredFile) == 1
    assert await count(db_session, InstructorDocument) == 1
    problem_of(await client.get(first.json()["href"], headers=auth), 404)
    got = await client.get(second.json()["href"], headers=auth)
    assert got.status_code == 200 and got.content == newer


async def test_instructor_document_delete_removes_file_row(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _, auth = await _instructor(app, db_session)
    up = await _put(client, auth, "pledge")
    assert up.status_code == 201, up.text
    r = await client.delete(f"{ME_DOCS}/pledge", headers=auth)
    assert r.status_code == 204, r.text
    await _nothing_written(db_session)
    problem_of(await client.get(up.json()["href"], headers=auth), 404)
    problem_of(await client.delete(f"{ME_DOCS}/pledge", headers=auth), 404)
    me = (await client.get("/v1/me", headers=auth)).json()
    pledge = next(d for d in me["documents"] if d["type_id"] == "pledge")
    assert (pledge["submitted_at"], pledge["size"], pledge["href"]) == (
        None,
        None,
        None,
    )


async def test_instructor_document_other_instructor_403(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    owner, owner_auth = await _instructor(app, db_session)
    _, other_auth = await _instructor(app, db_session, "instructor-b@example.com")
    up = await _put(client, owner_auth)
    assert up.status_code == 201, up.text
    href = up.json()["href"]
    _, admin = await admin_headers(db_session)
    course, _ = await open_test_course(db_session)
    # principal id 가 강사 id 와 같은 다른 종류의 토큰(id 만 비교하면 통과해 버린다)
    same_id_admin = await _bearer(db_session, "same-id-admin", "admin", owner, None)
    same_id_learner = await _bearer(
        db_session, "same-id-learner", "learner", owner, course.id
    )
    tokens = {
        "다른 강사": other_auth,
        "관리자": admin,
        "같은 id 관리자": same_id_admin,
        "같은 id 수강생": same_id_learner,
    }
    statuses = {
        name: (await client.get(href, headers=headers)).status_code
        for name, headers in tokens.items()
    }
    assert statuses == dict.fromkeys(tokens, 403)
    got = await client.get(href, headers=owner_auth)
    assert got.status_code == 200 and got.content == pdf_bytes()
    # 남의 서류를 지우거나 덮지 못한다: 같은 종류를 올려도 자기 서류다
    assert (await _put(client, other_auth)).status_code == 201
    assert await count(db_session, StoredFile, StoredFile.owner_id == owner) == 1


async def test_instructor_document_admin_view_audit_each_time(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    iid, auth = await _instructor(app, db_session)
    assert (await _put(client, auth)).status_code == 201
    doc_id = await db_session.scalar(select(InstructorDocument.id))
    aid, admin = await admin_headers(db_session)
    for _ in range(2):
        r = await client.get(_view(iid), headers=admin)
        assert r.status_code == 200, r.text
        assert r.content == pdf_bytes()
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "private, no-store"
        assert r.headers["content-disposition"].startswith("attachment")
    audit = (
        await db_session.execute(
            select(
                AuditLog.action,
                AuditLog.actor,
                AuditLog.target_type,
                AuditLog.target_id,
                AuditLog.detail,
            ).where(AuditLog.action == "instructor_document.view")
        )
    ).all()
    assert [tuple(a) for a in audit] == [
        (
            "instructor_document.view",
            f"admin:{aid}",
            "instructor_document",
            str(doc_id),
            {"instructor_id": iid, "type_id": "resume"},
        )
    ] * 2
    # 강사 토큰은 관리자 열람 끝점을 못 쓴다
    problem_of(await client.get(_view(iid), headers=auth), 403)


async def test_instructor_document_unknown_type_404(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    iid, auth = await _instructor(app, db_session)
    _, admin = await admin_headers(db_session)
    for type_id in ("degree", "RESUME", "re%00sume"):
        problem_of(await _put(client, auth, type_id), 404, "/problems/not_found")
        problem_of(await client.delete(f"{ME_DOCS}/{type_id}", headers=auth), 404)
        problem_of(await client.get(_view(iid, type_id), headers=admin), 404)
    problem_of(await client.get(_view(999_999_999), headers=admin), 404)  # 없는 강사
    problem_of(await client.get(_view(iid), headers=admin), 404)  # 아직 안 낸 서류
    await _nothing_written(db_session, store_root)


async def test_instructor_document_not_pdf_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _, auth = await _instructor(app, db_session)
    r = await _put(client, auth, data=b"hello, not a pdf")
    assert locs(problem_of(r, 422)) == [["body", "file"]]
    # file 파트가 없어도 422
    r = await client.put(f"{ME_DOCS}/resume", headers=auth, data={"note": "x"})
    assert locs(problem_of(r, 422)) == [["body", "file"]]
    await _nothing_written(db_session, store_root)


async def test_instructor_document_too_large_413(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    app.state.settings = Settings(file_store_root=tmp_path, document_pdf_max_mb=1)
    _, auth = await _instructor(app, db_session)
    # 실제 크기: 본문은 상한 + 1MiB 안이지만 파일이 1MiB 를 넘는다
    just_over = pdf_bytes() + b"0" * (MIB - len(pdf_bytes()) + 1)
    problem_of(await _put(client, auth, data=just_over), 413)
    # Content-Length 가 상한 + 1MiB 를 넘으면 본문을 읽지 않고 413
    problem_of(await _put(client, auth, data=pdf_bytes() + b"0" * (2 * MIB)), 413)
    await _nothing_written(db_session, tmp_path)
    exact = pdf_bytes() + b"0" * (MIB - len(pdf_bytes()))
    assert (await _put(client, auth, data=exact)).status_code == 201


async def test_instructor_document_store_root_unset_501(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    _, auth = await _instructor(app, db_session)
    body = problem_of(await _put(client, auth), 501, "/problems/not_configured")
    assert body["missing"] == ["CLASSFIT_FILE_STORE_ROOT"]
    await _nothing_written(db_session)
    problem_of(
        await _put(client, auth, "degree"), 404
    )  # 종류 판정이 저장소 판정보다 앞


async def test_instructor_document_without_length_411(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, store_root: Path
) -> None:
    _, auth = await _instructor(app, db_session)

    async def chunks() -> AsyncIterator[bytes]:
        yield b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'
        yield pdf_bytes() + b"\r\n--x--\r\n"

    r = await client.put(
        f"{ME_DOCS}/resume",
        headers={**auth, "content-type": "multipart/form-data; boundary=x"},
        content=chunks(),
    )
    assert "content-length" not in r.request.headers
    problem_of(r, 411)
    await _nothing_written(db_session, store_root)
