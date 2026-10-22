"""강사 역량(PUT·DELETE /v1/me/capabilities/{pool_id}) · 역량 파일, T4 계획 결정 i·viii·ix·x · 증명 10·11·17.

PUT 은 만들기 201 · 메모 바꾸기 200 이고 남의 고유 과정에도 된다(소유 판정 없음). 비활성 과정은 409.
DELETE 는 역량 행과 그 파일 행·stored_file 행을 같은 트랜잭션에서 지운다. 파일 넣기 판정 순서는 T2b 첨부와 같고,
소유자(역량 1건)당 파일 20개를 넘으면 바이트를 읽기 전에 409 + limit 20 이다.
역량 파일 href 는 관리자 ∨ 본인 강사만 연다(같은 id 의 수강생 토큰은 403).
"""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import Capability, CapabilityFile, StoredFile
from classfit.service.files.store import path_for
from tests.fixtures.courses import _bearer, admin_headers, open_test_course
from tests.fixtures.enter import PDF, json_keys
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.pool import (
    ME,
    NAME_B,
    PERSONAL_POOL_KEYS,
    add_pool_link,
    add_pool_pdf,
    audit_rows,
    instructor_pair,
    make_pool_course,
    set_flags,
)

MIB = 1024 * 1024


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _files(pool_id: str) -> str:
    return f"{ME}/capabilities/{pool_id}/files"


async def _capable(
    client: httpx.AsyncClient, headers: dict[str, str], pool_id: str
) -> None:
    r = await client.put(f"{ME}/capabilities/{pool_id}", headers=headers, json={})
    assert r.status_code == 201, r.text


async def _nothing_written(session: AsyncSession, root: Path | None = None) -> None:
    assert await count(session, CapabilityFile) == 0
    assert await count(session, StoredFile) == 0
    if root is not None:
        assert not any(p.is_file() for p in root.rglob("*"))


async def test_pool_capability_put_creates_then_updates_memo(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (aid, auth), _ = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax", title="AX 과정 가")
    path = f"{ME}/capabilities/{row.id}"
    first = await client.put(path, headers=auth, json={"memo": " 현장 사례 중심 "})
    assert first.status_code == 201, first.text
    assert (first.json()["pool_id"], first.json()["title"], first.json()["memo"]) == (
        row.id,
        "AX 과정 가",
        "현장 사례 중심",
    )
    second = await client.put(path, headers=auth, json={"memo": "실습 위주"})
    assert second.status_code == 200, second.text
    assert second.json()["memo"] == "실습 위주"
    assert second.json()["created_at"] == first.json()["created_at"]
    assert await count(db_session, Capability) == 1
    expected = [
        ("capability.create", f"instructor:{aid}"),
        ("capability.update", f"instructor:{aid}"),
    ]
    assert [a[:2] for a in await audit_rows(db_session, "capability.")] == expected
    # 같은 메모는 200 이고 audit 이 늘지 않는다
    again = await client.put(path, headers=auth, json={"memo": "실습 위주"})
    assert again.status_code == 200, again.text
    assert [a[:2] for a in await audit_rows(db_session, "capability.")] == expected
    # 본문 없이 PUT 하면 메모를 비운다
    cleared = await client.put(path, headers=auth)
    assert (cleared.status_code, cleared.json()["memo"]) == (200, None)


async def test_pool_capability_put_on_other_own_course_201(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (aid, auth_a), (bid, _) = await instructor_pair(db_session, app.state.settings)
    reviewed = await make_pool_course(
        db_session, owner_instructor_id=bid, title="B 과정"
    )
    await set_flags(db_session, reviewed, reviewed=True, pub=True)
    stopped = await make_pool_course(
        db_session, owner_instructor_id=bid, title="B 중지"
    )
    await set_flags(db_session, stopped, active=False)
    r = await client.put(f"{ME}/capabilities/{reviewed.id}", headers=auth_a, json={})
    assert r.status_code == 201, r.text
    problem_of(
        await client.put(f"{ME}/capabilities/{stopped.id}", headers=auth_a, json={}),
        409,
        "/problems/conflict",
    )
    listed = await client.get(f"{ME}/capabilities", headers=auth_a)
    assert [i["pool_id"] for i in listed.json()["items"]] == [reviewed.id]
    assert json_keys(listed.json()) & PERSONAL_POOL_KEYS == set()
    assert NAME_B not in listed.text
    owners = await db_session.scalars(select(Capability.instructor_id))
    assert list(owners) == [aid]


async def test_pool_capability_put_inactive_course_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax")
    await set_flags(db_session, row, active=False)
    problem_of(
        await client.put(f"{ME}/capabilities/{row.id}", headers=auth, json={}),
        409,
        "/problems/conflict",
    )
    for pool_id in ("ax-none-1", "BAD ID"):
        problem_of(
            await client.put(f"{ME}/capabilities/{pool_id}", headers=auth, json={}),
            404,
            "/problems/not_found",
        )
        problem_of(
            await client.delete(f"{ME}/capabilities/{pool_id}", headers=auth), 404
        )
    assert await count(db_session, Capability) == 0
    assert await audit_rows(db_session, "capability.") == []


async def test_pool_files_count_limit_409(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax")
    await _capable(client, auth, row.id)
    for n in range(10):
        pdf = await add_pool_pdf(client, auth, _files(row.id), PDF + f"%{n}\n".encode())
        assert pdf.status_code == 201, pdf.text
        link = await add_pool_link(
            client, auth, _files(row.id), url=f"https://example.com/{n}"
        )
        assert link.status_code == 201, link.text
    files_before = await count(db_session, StoredFile)
    assert (await count(db_session, CapabilityFile), files_before) == (20, 10)
    extra = PDF + b"%21st\n"
    body = problem_of(
        await add_pool_pdf(client, auth, _files(row.id), extra),
        409,
        "/problems/conflict",
    )
    assert body["limit"] == 20
    assert await count(db_session, StoredFile) == files_before
    assert not path_for(store_root, hashlib.sha256(extra).hexdigest()).exists()
    problem_of(await add_pool_link(client, auth, _files(row.id)), 409)
    # 하나 지우면 다시 받는다
    first = await db_session.scalar(
        select(CapabilityFile.id).order_by(CapabilityFile.id)
    )
    r = await client.delete(f"{ME}/capability-files/{first}", headers=auth)
    assert r.status_code == 204, r.text
    again = await add_pool_pdf(client, auth, _files(row.id), extra)
    assert again.status_code == 201, again.text


async def test_pool_capability_delete_removes_files_and_file_rows(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (aid, auth), _ = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax")
    await _capable(client, auth, row.id)
    hrefs = []
    for n in range(2):
        up = await add_pool_pdf(client, auth, _files(row.id), PDF + f"%{n}\n".encode())
        assert up.status_code == 201, up.text
        hrefs.append(up.json()["href"])
    r = await client.delete(f"{ME}/capabilities/{row.id}", headers=auth)
    assert r.status_code == 204, r.text
    assert await count(db_session, Capability) == 0
    await _nothing_written(db_session)
    for href in hrefs:
        problem_of(await client.get(href, headers=auth), 404)
    deleted = [
        a
        for a in await audit_rows(db_session, "capability.delete")
        if a[1] == f"instructor:{aid}"
    ]
    assert len(deleted) == 1
    # 다시 지우면 404
    problem_of(await client.delete(f"{ME}/capabilities/{row.id}", headers=auth), 404)


async def test_pool_capability_file_pdf_and_link(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (aid, auth), _ = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax")
    await _capable(client, auth, row.id)
    pdf = await add_pool_pdf(client, auth, _files(row.id), title="내 강의안")
    assert pdf.status_code == 201, pdf.text
    link = await add_pool_link(
        client, auth, _files(row.id), url="https://example.com/a"
    )
    assert link.status_code == 201, link.text
    assert (pdf.json()["kind"], pdf.json()["title"], pdf.json()["size"]) == (
        "pdf",
        "내 강의안",
        len(PDF),
    )
    assert (link.json()["kind"], link.json()["href"], link.json()["size"]) == (
        "link",
        "https://example.com/a",
        None,
    )
    stored = (await db_session.execute(select(StoredFile))).scalars().all()
    assert len(stored) == 1
    file_row = await db_session.scalar(
        select(CapabilityFile).where(CapabilityFile.id == pdf.json()["id"])
    )
    assert file_row is not None and file_row.file_id == stored[0].id
    assert (stored[0].owner_kind, stored[0].owner_id, stored[0].content_type) == (
        "capability_file",
        file_row.id,
        "application/pdf",
    )
    assert pdf.json()["href"] == f"/v1/files/{stored[0].key}"
    got = await client.get(pdf.json()["href"], headers=auth)
    assert got.status_code == 200 and got.content == PDF
    _, admin = await admin_headers(db_session)
    assert (await client.get(pdf.json()["href"], headers=admin)).status_code == 200
    listed = (await client.get(f"{ME}/capabilities", headers=auth)).json()["items"]
    assert [f["id"] for f in listed[0]["files"]] == [
        pdf.json()["id"],
        link.json()["id"],
    ]
    created = await audit_rows(db_session, "capability_file.create")
    assert [(a[1], a[2]) for a in created] == [
        (f"instructor:{aid}", "capability_file")
    ] * 2


async def test_pool_capability_file_other_instructor_403(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (aid, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax")
    await _capable(client, auth_a, row.id)
    up = await add_pool_pdf(client, auth_a, _files(row.id))
    assert up.status_code == 201, up.text
    href, file_id = up.json()["href"], up.json()["id"]
    course, _ = await open_test_course(db_session)
    # principal id 가 A 강사 id 와 같은 수강생 토큰(id 만 비교하면 통과해 버린다, 결정 ix)
    same_id_learner = await _bearer(
        db_session, "same-id-learner", "learner", aid, course.id
    )
    statuses = {
        "B 강사": (await client.get(href, headers=auth_b)).status_code,
        "같은 id 수강생": (await client.get(href, headers=same_id_learner)).status_code,
    }
    assert statuses == {"B 강사": 403, "같은 id 수강생": 403}
    got = await client.get(href, headers=auth_a)
    assert got.status_code == 200 and got.content == PDF
    # 남의 파일을 지우지 못한다. B 는 역량이 없으니 B 의 파일 넣기는 404 다
    problem_of(
        await client.delete(f"{ME}/capability-files/{file_id}", headers=auth_b),
        403,
        "/problems/forbidden",
    )
    problem_of(await add_pool_pdf(client, auth_b, _files(row.id)), 404)
    assert await count(db_session, CapabilityFile) == 1


async def test_pool_capability_file_upload_rejections(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    row = await make_pool_course(db_session, source="ax")
    await _capable(client, auth, row.id)
    path = _files(row.id)
    # 501: 저장소 미구성(pdf 만. 판정은 폼 뒤)
    body = problem_of(
        await add_pool_pdf(client, auth, path), 501, "/problems/not_configured"
    )
    assert body["missing"] == ["CLASSFIT_FILE_STORE_ROOT"]
    app.state.settings = Settings(file_store_root=tmp_path, attachment_pdf_max_mb=1)

    # 411: Content-Length 없음
    async def chunks() -> AsyncIterator[bytes]:
        yield b"kind=link&title=x&url=https%3A%2F%2Fexample.com"

    r = await client.post(
        path,
        headers={**auth, "content-type": "application/x-www-form-urlencoded"},
        content=chunks(),
    )
    assert "content-length" not in r.request.headers
    problem_of(r, 411)
    # 413: 실제 크기 · Content-Length
    just_over = PDF + b"0" * (MIB - len(PDF) + 1)
    problem_of(await add_pool_pdf(client, auth, path, just_over), 413)
    problem_of(await add_pool_pdf(client, auth, path, PDF + b"0" * (2 * MIB)), 413)
    # 422: %PDF- 아님 · kind 밖 · link 에 url 없음
    assert locs(
        problem_of(await add_pool_pdf(client, auth, path, b"not a pdf"), 422)
    ) == [["body", "file"]]
    r = await client.post(path, headers=auth, data={"kind": "html", "title": "x"})
    assert locs(problem_of(r, 422)) == [["body", "kind"]]
    r = await client.post(path, headers=auth, data={"kind": "link", "title": "x"})
    assert locs(problem_of(r, 422)) == [["body", "url"]]
    # 400: boundary 없는 multipart · 파일 파트 둘
    r = await client.post(
        path,
        headers={**auth, "content-type": "multipart/form-data"},
        content=b'--x\r\nContent-Disposition: form-data; name="kind"\r\n\r\npdf\r\n--x--\r\n',
    )
    problem_of(r, 400, "/problems/bad-request")
    r = await client.post(
        path,
        headers=auth,
        data={"kind": "pdf", "title": "x"},
        files=[
            ("file", ("a.pdf", PDF, "application/pdf")),
            ("file", ("b.pdf", PDF, "application/pdf")),
        ],
    )
    problem_of(r, 400, "/problems/bad-request")
    await _nothing_written(db_session, tmp_path)
    exact = PDF + b"0" * (MIB - len(PDF))
    assert (await add_pool_pdf(client, auth, path, exact)).status_code == 201
