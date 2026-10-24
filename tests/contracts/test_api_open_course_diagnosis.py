"""개설 시작점 ③(확정 진단) — POST /v1/admin/courses {start: "diagnosis", diagnosis_id}(T9a 계획 결정 vii · 증명 21·22).

확정 회차의 권장 구성이 섹션·세션이 된다: 「공통교육」(공통 항목) + 트랙마다 섹션(이름은 트랙 이름의 " (" 앞 · 과정 + 캡스톤
세션). 세션은 일차 미정 · 강사 미배정 · 비공개 · 교시 분(slot_min) · 풀 참조 없음이다. 강의는 회차의 회사에 연결된다.
확정 전(draft·review) 회차는 409 다. ①②④ 는 company_id 를 선택으로 받고 ③ 은 받지 않는다(회사는 회차에서).
"""

from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import AuditLog, Course, CourseSession, InviteCode, Section
from classfit.schemas.course import CourseOut
from classfit.service.rules.reco import reco_sections
from tests.fixtures.courses import admin_headers
from tests.fixtures.diagnosis import (
    ANSWERS_ALL_5,
    ANSWERS_MIXED,
    COMPANY_BODY,
    RECO_SAMPLE,
    RESPONDENT,
    TODAY,
    UNDATED_BODY,
    set_today,
)
from tests.fixtures.instructors import count, locs, problem_of

ADMIN = "/v1/admin"
URL = f"{ADMIN}/courses"
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _company(client: httpx.AsyncClient, auth: dict[str, str]) -> int:
    r = await client.post(f"{ADMIN}/companies", headers=auth, json=COMPANY_BODY)
    return int(_ok(r, 201)["id"])


async def _round(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    company_id: int,
    *,
    reco: dict[str, Any] | None = None,
    finalize: bool = True,
) -> int:
    r = await client.post(
        f"{ADMIN}/companies/{company_id}/diagnoses", headers=auth, json={"phase": "pre"}
    )
    rid = int(_ok(r, 201)["id"])
    r = await client.patch(
        f"{ADMIN}/diagnoses/{rid}", headers=auth, json={"answers": ANSWERS_ALL_5}
    )
    _ok(r)
    if reco is not None:
        _ok(
            await client.patch(f"{ADMIN}/diagnoses/{rid}/reco", headers=auth, json=reco)
        )
    if finalize:
        _ok(await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth))
    return rid


async def _sections(
    session: AsyncSession, course_id: int
) -> list[tuple[str, list[Any]]]:
    """(섹션 제목, 세션 행들) — 섹션 sort 순, 세션은 제목 순."""
    sections = await session.execute(
        select(Section.id, Section.title)
        .where(Section.course_id == course_id)
        .order_by(Section.sort, Section.id)
    )
    out = []
    for section_id, title in sections.all():
        rows = await session.scalars(
            select(CourseSession).where(CourseSession.section_id == section_id)
        )
        out.append((title, sorted(rows, key=lambda s: s.title)))
    return out


async def test_open_course_diagnosis_builds_sections(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)
    rid = await _round(client, auth, co, reco=RECO_SAMPLE)

    r = await client.post(
        URL,
        headers=auth,
        json={**UNDATED_BODY, "start": "diagnosis", "diagnosis_id": rid},
    )
    opened = _ok(r, 201)
    course = opened["course"]
    assert set(course) == set(CourseOut.model_fields)
    assert course["company_id"] == co
    assert opened["invite_code"]["code"]
    cid = course["id"]

    expected = reco_sections(RECO_SAMPLE)
    assert [title for title, _ in expected] == [
        "공통교육",
        "고객 접점 · 수주",
        "생산기술 · 제조",
    ]
    schedule = _ok(await client.get(f"{URL}/{cid}/schedule", headers=auth))
    assert schedule["days"] == []
    undated = schedule["undated"]
    assert len(undated) == 9
    assert sorted(s["title"] for s in undated) == sorted(
        t for _, ts in expected for t in ts
    )
    assert {(s["instructor_id"], s["instructor_name"]) for s in undated} == {
        (None, None)
    }

    built = await _sections(db_session, cid)
    assert [(title, sorted(s.title for s in rows)) for title, rows in built] == [
        (title, sorted(ts)) for title, ts in expected
    ]
    assert [len(rows) for _, rows in built] == [3, 3, 3]
    sessions = [s for _, rows in built for s in rows]
    slot_min = course["slot_min"]
    assert "캡스톤 교육 세션" in {s.title for s in sessions}
    for s in sessions:
        assert (s.day_no, s.slot, s.is_open, s.minutes) == (None, None, False, slot_min)
        assert (s.instructor_id, s.pool_course_id, s.curriculum_id) == (
            None,
            None,
            None,
        )
        assert (s.description, s.keywords) == (None, [])

    (detail,) = await db_session.scalars(
        select(AuditLog.detail).where(
            AuditLog.action == "course.open", AuditLog.target_id == str(cid)
        )
    )
    assert (detail["start"], detail["source"]) == ("diagnosis", rid)
    assert (detail["sections"], detail["sessions"]) == (3, 9)
    company = _ok(await client.get(f"{ADMIN}/companies/{co}", headers=auth))
    assert company["courses"] == [{"id": cid, "title": UNDATED_BODY["title"]}]
    assert await count(db_session, InviteCode, InviteCode.course_id == cid) == 1


async def test_open_course_diagnosis_not_final_409(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)
    draft = await _round(client, auth, co, finalize=False)
    r = await client.post(
        f"{ADMIN}/companies/{co}/links", headers=auth, json={"phase": "post"}
    )
    token = _ok(r, 201)["token"]
    r = await client.post(
        f"/v1/ax/{token}", json={"answers": ANSWERS_MIXED, "respondent": RESPONDENT}
    )
    _ok(r, 201)
    detail = _ok(await client.get(f"{ADMIN}/companies/{co}", headers=auth))
    (review,) = [x["id"] for x in detail["rounds"] if x["status"] == "review"]
    # reco 를 저장해 두어 확정 가드만의 몫을 잰다(reco 없음 가드에 걸리지 않게)
    _ok(
        await client.patch(
            f"{ADMIN}/diagnoses/{review}/reco", headers=auth, json=RECO_SAMPLE
        )
    )
    final = await _round(client, auth, co)
    counts = (await count(db_session, Course), await count(db_session, InviteCode))

    async def rejected(
        body: dict[str, Any], status: int, type_: str | None = None
    ) -> dict[str, Any]:
        got = problem_of(await client.post(URL, headers=auth, json=body), status, type_)
        assert (
            await count(db_session, Course),
            await count(db_session, InviteCode),
        ) == counts, body
        return got

    third = {**UNDATED_BODY, "start": "diagnosis"}
    blank = {**UNDATED_BODY, "start": "blank"}
    await rejected({**third, "diagnosis_id": draft}, 409, "/problems/conflict")
    await rejected({**third, "diagnosis_id": review}, 409, "/problems/conflict")
    await rejected({**third, "diagnosis_id": LARGEST}, 404, "/problems/not_found")
    got = await rejected({**third, "diagnosis_id": OVERFLOW}, 422)
    assert locs(got) == [["body", "diagnosis_id"]]
    await rejected(third, 422)
    await rejected({**blank, "diagnosis_id": final}, 422)
    await rejected({**third, "diagnosis_id": final, "company_id": co}, 422)
    await rejected({**UNDATED_BODY, "start": "clone", "diagnosis_id": final}, 422)
    await rejected({**blank, "company_id": LARGEST}, 404, "/problems/not_found")

    linked = _ok(
        await client.post(URL, headers=auth, json={**blank, "company_id": co}),
        201,
    )
    assert linked["course"]["company_id"] == co
    plain = _ok(await client.post(URL, headers=auth, json=blank), 201)
    assert plain["course"]["company_id"] is None
    _ok(
        await client.post(URL, headers=auth, json={**third, "diagnosis_id": final}),
        201,
    )
