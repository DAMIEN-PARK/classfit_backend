"""강사 커리큘럼(/v1/me/curricula…) · 차시표 · 커리큘럼 파일, T4 계획 결정 i·vi·xi·xv·xix · 증명 6·10·12·13.

하루 격자는 slots_per_day(강사.html:670)다: 13:00~17:00 · 50분 교시 · 10분 쉬는 시간이면 4교시.
차시표 PUT 은 통째 교체이고 격자 밖·(day, slot) 중복은 422 loc ["body", "slots", i]. 일수를 줄여 기존 차시가
격자 밖이 되면 PATCH 가 422 다. 내용·차시표가 바뀌면 reviewed 만 거짓으로 돌아간다(pub·active 유지).
"""

import re
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.models import Curriculum, CurriculumFile, CurriculumSlot, StoredFile
from tests.fixtures.courses import _bearer, admin_headers, open_test_course
from tests.fixtures.instructors import count, locs, problem_of
from tests.fixtures.pool import (
    ADMIN,
    CURRICULUM_DEFAULTS,
    ME,
    add_pool_pdf,
    audit_rows,
    curriculum_body,
    instructor_pair,
    set_flags,
)

CUR = f"{ME}/curricula"


@pytest.fixture
def store_root(app: FastAPI, tmp_path: Path) -> Path:
    app.state.settings = Settings(file_store_root=tmp_path)
    return tmp_path


def _slots(*cells: tuple[int, int]) -> dict[str, Any]:
    return {
        "slots": [{"day": d, "slot": s, "title": f"{d}일차 {s}교시"} for d, s in cells]
    }


async def _create(
    client: httpx.AsyncClient, headers: dict[str, str], **over: Any
) -> str:
    r = await client.post(CUR, headers=headers, json=curriculum_body(**over))
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _row(session: AsyncSession, curriculum_id: str) -> Curriculum:
    row = await session.scalar(
        select(Curriculum)
        .where(Curriculum.id == curriculum_id)
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def test_pool_curriculum_same_value_patch_no_audit(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    cur_id = await _create(client, auth)
    cells = _slots((1, 1), (1, 2), (2, 1))
    assert (
        await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=cells)
    ).status_code == 200
    await set_flags(db_session, await _row(db_session, cur_id), reviewed=True)
    before = await audit_rows(db_session, "curriculum.")
    same = curriculum_body()
    r = await client.patch(f"{CUR}/{cur_id}", headers=auth, json=same)
    assert (r.status_code, r.json()["reviewed"]) == (200, True), r.text
    r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=cells)
    assert (r.status_code, r.json()["reviewed"]) == (200, True), r.text
    assert await audit_rows(db_session, "curriculum.") == before
    assert await count(db_session, CurriculumSlot) == 3


async def test_pool_curriculum_create_and_slots_put(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (aid, auth), _ = await instructor_pair(db_session, app.state.settings)
    r = await client.post(CUR, headers=auth, json=curriculum_body())
    assert r.status_code == 201, r.text
    body = r.json()
    cur_id = body["id"]
    assert re.fullmatch(rf"cur-{aid}-[0-9]+", cur_id), cur_id
    assert (body["slots_per_day"], body["start_time"], body["end_time"]) == (
        4,
        "13:00:00",
        "17:00:00",
    )
    assert (body["slots"], body["reviewed"], body["pub"], body["active"]) == (
        [],
        False,
        False,
        True,
    )
    # 4일 × 4교시 = 16칸 중 10칸(역순으로 보내도 응답은 (day, slot) 순)
    ten = [(d, s) for d in range(1, 5) for s in range(1, 5)][:10]
    r = await client.put(
        f"{CUR}/{cur_id}/slots", headers=auth, json=_slots(*reversed(ten))
    )
    assert r.status_code == 200, r.text
    assert [(s["day"], s["slot"]) for s in r.json()["slots"]] == ten
    assert await count(db_session, CurriculumSlot) == 10
    eight = ten[:8]
    r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=_slots(*eight))
    assert [(s["day"], s["slot"]) for s in r.json()["slots"]] == eight
    assert await count(db_session, CurriculumSlot) == 8
    got = (await client.get(f"{CUR}/{cur_id}", headers=auth)).json()
    assert len(got["slots"]) == 8 and got["slots"][0]["title"] == "1일차 1교시"


async def test_pool_curriculum_slot_out_of_grid_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    cur_id = await _create(client, auth)
    for cells, bad in (
        (((1, 1), (1, 5)), 1),  # 5교시: 하루 4교시 밖
        (((5, 1),), 0),  # 5일차: 4일 밖
    ):
        r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=_slots(*cells))
        found = locs(problem_of(r, 422))
        assert found and all(loc[:3] == ["body", "slots", bad] for loc in found), found
    # 모양(0 이하)은 스키마가 막는다
    r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=_slots((0, 1)))
    assert locs(problem_of(r, 422))[0][:4] == ["body", "slots", 0, "day"]
    assert await count(db_session, CurriculumSlot) == 0


async def test_pool_curriculum_slots_duplicate_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    cur_id = await _create(client, auth)
    r = await client.put(
        f"{CUR}/{cur_id}/slots", headers=auth, json=_slots((1, 1), (2, 2), (1, 1))
    )
    found = locs(problem_of(r, 422))
    assert found and all(loc[:3] == ["body", "slots", 2] for loc in found), found
    assert await count(db_session, CurriculumSlot) == 0


async def test_pool_curriculum_patch_shrink_days_with_slots_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    cur_id = await _create(client, auth)
    r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=_slots((4, 1)))
    assert r.status_code == 200, r.text
    r = await client.patch(f"{CUR}/{cur_id}", headers=auth, json={"days": 3})
    assert locs(problem_of(r, 422)) == [["body", "days"]]
    # 교시를 늘려 하루 교시 수가 줄어도 같다(13:00~17:00 · 110분 + 10분 → 2교시)
    r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=_slots((1, 4)))
    assert r.status_code == 200, r.text
    r = await client.patch(f"{CUR}/{cur_id}", headers=auth, json={"slot_min": 110})
    assert locs(problem_of(r, 422)) == [["body", "slot_min"]]
    row = await _row(db_session, cur_id)
    assert (row.days, row.slot_min) == (4, 50)
    # 차시표를 먼저 비우면 줄일 수 있다
    r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json={"slots": []})
    assert r.status_code == 200, r.text
    r = await client.patch(f"{CUR}/{cur_id}", headers=auth, json={"days": 3})
    assert (r.status_code, r.json()["days"]) == (200, 3), r.text


async def test_pool_curriculum_patch_or_slots_reset_reviewed_keeps_pub(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth), _ = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    cur_id = await _create(client, auth)

    async def review() -> str:
        r = await client.patch(
            f"{ADMIN}/curricula/{cur_id}",
            headers=admin,
            json={"reviewed": True, "pub": True},
        )
        assert r.status_code == 200, r.text
        assert (r.json()["reviewed"], r.json()["pub"]) == (True, True)
        return str(r.json()["reviewed_at"])

    reviewed_at = await review()
    r = await client.patch(f"{CUR}/{cur_id}", headers=auth, json={"title": "고친 제목"})
    body = r.json()
    assert (body["reviewed"], body["reviewed_at"], body["pub"], body["active"]) == (
        False,
        reviewed_at,
        True,
        True,
    )
    reviewed_at = await review()
    r = await client.put(f"{CUR}/{cur_id}/slots", headers=auth, json=_slots((1, 1)))
    body = r.json()
    assert (body["reviewed"], body["reviewed_at"], body["pub"], body["active"]) == (
        False,
        reviewed_at,
        True,
        True,
    )
    actions = [a[0] for a in await audit_rows(db_session, "curriculum.")]
    assert "curriculum.update" in actions and "curriculum.slots" in actions
    # 관리자가 active 만 껐다 켜도 검토 뒤 고친 공개 커리큘럼의 pub 은 그대로다(리뷰 Nit 1)
    for active in (False, True):
        r = await client.patch(
            f"{ADMIN}/curricula/{cur_id}", headers=admin, json={"active": active}
        )
        assert r.status_code == 200, r.text
        assert (r.json()["reviewed"], r.json()["pub"], r.json()["active"]) == (
            False,
            True,
            active,
        )


async def test_pool_curriculum_other_instructor_403_and_delete_deactivates(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    (_, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    cur_id = await _create(client, auth_b, title="B 커리큘럼")
    path = f"{CUR}/{cur_id}"
    for r in (
        await client.get(path, headers=auth_a),
        await client.patch(path, headers=auth_a, json={"title": "x"}),
        await client.put(f"{path}/slots", headers=auth_a, json=_slots((1, 1))),
        await client.delete(path, headers=auth_a),
    ):
        problem_of(r, 403, "/problems/forbidden")
    row = await _row(db_session, cur_id)
    assert (row.title, row.active) == ("B 커리큘럼", True)
    assert await count(db_session, CurriculumSlot) == 0
    problem_of(await client.get(f"{CUR}/cur-0-0", headers=auth_a), 404)
    # 본인 DELETE 는 사용 중지
    assert (await client.delete(path, headers=auth_b)).status_code == 204
    assert (await _row(db_session, cur_id)).active is False
    listed = (await client.get(CUR, headers=auth_b)).json()["items"]
    assert [(i["id"], i["active"]) for i in listed] == [(cur_id, False)]
    assert (await client.delete(path, headers=auth_b)).status_code == 204
    problem_of(
        await client.patch(path, headers=auth_b, json={"title": "x"}),
        409,
        "/problems/conflict",
    )
    problem_of(
        await client.put(f"{path}/slots", headers=auth_b, json=_slots((1, 1))), 409
    )
    assert await count(db_session, Curriculum) == 1
    assert CURRICULUM_DEFAULTS["days"] == (await _row(db_session, cur_id)).days


async def test_pool_curriculum_file_pdf_href_scope(
    app: FastAPI,
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    store_root: Path,
) -> None:
    (aid, auth_a), (_, auth_b) = await instructor_pair(db_session, app.state.settings)
    _, admin = await admin_headers(db_session)
    cur_id = await _create(client, auth_a)
    up = await add_pool_pdf(client, auth_a, f"{CUR}/{cur_id}/files")
    assert up.status_code == 201, up.text
    href, file_id = up.json()["href"], up.json()["id"]
    stored = await db_session.scalar(select(StoredFile))
    assert stored is not None
    assert (stored.owner_kind, stored.owner_id) == ("curriculum_file", file_id)
    course, _ = await open_test_course(db_session)
    same_id_learner = await _bearer(
        db_session, "same-id-learner", "learner", aid, course.id
    )
    statuses = {
        "본인": (await client.get(href, headers=auth_a)).status_code,
        "관리자": (await client.get(href, headers=admin)).status_code,
        "B 강사": (await client.get(href, headers=auth_b)).status_code,
        "같은 id 수강생": (await client.get(href, headers=same_id_learner)).status_code,
    }
    assert statuses == {
        "본인": 200,
        "관리자": 200,
        "B 강사": 403,
        "같은 id 수강생": 403,
    }
    got = (await client.get(f"{CUR}/{cur_id}", headers=auth_a)).json()
    assert [f["id"] for f in got["files"]] == [file_id]
    problem_of(await add_pool_pdf(client, auth_b, f"{CUR}/{cur_id}/files"), 403)
    problem_of(
        await client.delete(f"{ME}/curriculum-files/{file_id}", headers=auth_b), 403
    )
    r = await client.delete(f"{ME}/curriculum-files/{file_id}", headers=auth_a)
    assert r.status_code == 204, r.text
    assert await count(db_session, CurriculumFile) == 0
    assert await count(db_session, StoredFile) == 0
    problem_of(await client.get(href, headers=auth_a), 404)
