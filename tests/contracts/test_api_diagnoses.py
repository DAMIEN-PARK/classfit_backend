"""진단 회차: 생성·수정·확정·삭제·리포트·권장 구성(T9a 계획 결정 iv·v·viii·xii·xiii · 증명 14~20).

전이(결정 iv): 방문 회차 생성 draft(D1) · 바뀐 칸이 있는 PATCH(D2) · 같은 값 PATCH 는 audit 없음(D3) · 확정 뒤 PATCH·reco·
DELETE·재확정 409(D4·D7) · 17지표면 확정(D5) · 미응답이면 409 + missing(D6) · reco 편집(D8) · 삭제(D9 — 링크 회차면 링크 revoked,
번호는 당기지 않는다). 리포트는 영역 200 × 4 · 총 800 · 17지표 전이면 level null · 비교 대상은 앞 회차 가운데 17지표를 다 답한
가장 최근 final ∨ review 회차(draft 는 건너뛴다). 링크 회차의 제출일은 다른 값이면 422 frozen_field, 같은 값은 바뀐 칸이 아니다.
픽스처 오늘은 TODAY(2026-11-03)다. 권장 구성 후보는 pool_candidates 가 만든 공개 AX 과정이다(cs 2 · prod 4 → 앞 3).
"""

from datetime import date
from typing import Any, get_args

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import AuditLog, CourseSession, Diagnosis, Section
from classfit.models.diagnosis import ANSWER_KEYS, DIAG_STATUSES, MODES, PHASES
from classfit.schemas.diagnosis import DiagMode, DiagStatus, Phase
from tests.fixtures.assign import approved
from tests.fixtures.courses import admin_headers
from tests.fixtures.diagnosis import (
    ANSWERS_9,
    ANSWERS_ALL_1,
    ANSWERS_ALL_5,
    ANSWERS_MIXED,
    AREA_KEYS,
    COMPANY_BODY,
    DEPTS_20,
    DIAGNOSIS_KEYS,
    ITEM_KEYS,
    PREVIOUS_KEYS,
    RECO_SAMPLE,
    REPORT_KEYS,
    RESPONDENT,
    TODAY,
    TRACK_KEYS,
    UNDATED_BODY,
    pool_candidates,
    set_today,
)
from tests.fixtures.instructors import count, locs, problem_of

ADMIN = "/v1/admin"
LARGEST = 2**63 - 1  # BIGINT 로 표현되는 가장 큰 id — 없으면 404
OVERFLOW = 2**63  # BIGINT 밖 — DB 를 치기 전에 422


def _ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, (r.request.method, r.request.url, r.text)
    return r.json()


async def _company(client: httpx.AsyncClient, auth: dict[str, str], **over: Any) -> int:
    r = await client.post(
        f"{ADMIN}/companies", headers=auth, json={**COMPANY_BODY, **over}
    )
    return int(_ok(r, 201)["id"])


async def _round(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    company_id: int,
    answers: dict[str, int] | None = None,
    *,
    phase: str = "pre",
    finalize: bool = False,
) -> int:
    r = await client.post(
        f"{ADMIN}/companies/{company_id}/diagnoses", headers=auth, json={"phase": phase}
    )
    rid = int(_ok(r, 201)["id"])
    if answers is not None:
        await _patch(client, auth, rid, answers=answers)
    if finalize:
        _ok(await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth))
    return rid


async def _patch(
    client: httpx.AsyncClient, auth: dict[str, str], rid: int, **body: Any
) -> dict[str, Any]:
    r = await client.patch(f"{ADMIN}/diagnoses/{rid}", headers=auth, json=body)
    return dict(_ok(r))


async def _report(
    client: httpx.AsyncClient, auth: dict[str, str], rid: int
) -> dict[str, Any]:
    return dict(_ok(await client.get(f"{ADMIN}/diagnoses/{rid}/report", headers=auth)))


async def _submitted_round(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    company_id: int,
    answers: dict[str, int],
    *,
    phase: str = "post",
) -> tuple[int, str]:
    """링크 발급 → 공개 제출 → (검토 대기 회차 id, 토큰)."""
    r = await client.post(
        f"{ADMIN}/companies/{company_id}/links", headers=auth, json={"phase": phase}
    )
    token = _ok(r, 201)["token"]
    r = await client.post(
        f"/v1/ax/{token}", json={"answers": answers, "respondent": RESPONDENT}
    )
    _ok(r, 201)
    detail = _ok(await client.get(f"{ADMIN}/companies/{company_id}", headers=auth))
    (link,) = [x for x in detail["links"] if x["token"] == token]
    return int(link["diagnosis_id"]), token


async def _audits(
    session: AsyncSession, action: str, target_type: str = "diagnosis"
) -> list[tuple[str, Any]]:
    rows = await session.execute(
        select(AuditLog.target_id, AuditLog.detail)
        .where(AuditLog.action == action, AuditLog.target_type == target_type)
        .order_by(AuditLog.id)
    )
    return [(t, d) for t, d in rows.all()]


async def test_diagnosis_create_patch_finalize(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    admin_id, auth = await admin_headers(db_session)
    pool = await pool_candidates(db_session, app.state.settings)
    co = await _company(client, auth)  # 부서 영업(cs) · 생산(prod)

    r = await client.post(
        f"{ADMIN}/companies/{co}/diagnoses", headers=auth, json={"phase": "pre"}
    )
    made = _ok(r, 201)
    assert set(made) == DIAGNOSIS_KEYS
    assert (made["round_no"], made["status"], made["mode"], made["phase"]) == (
        1,
        "draft",
        "visit",
        "pre",
    )
    assert (made["diagnosed_on"], made["created_by"]) == (
        TODAY.isoformat(),
        f"admin:{admin_id}",
    )
    assert (made["respondent"], made["answers"], made["reco"]) == (None, {}, None)
    rid = made["id"]

    got = await _patch(client, auth, rid, answers=ANSWERS_9)
    assert got["answers"] == ANSWERS_9
    rep = await _report(client, auth, rid)
    assert (rep["answered"], rep["complete"], rep["level"], rep["total"]) == (
        9,
        False,
        None,
        220,
    )
    await _patch(client, auth, rid, answers=ANSWERS_9)  # 같은 값 — audit 없음
    assert [t for t, _ in await _audits(db_session, "diagnosis.update")] == [str(rid)]

    await _patch(client, auth, rid, answers=ANSWERS_MIXED)
    rep = await _report(client, auth, rid)
    assert (rep["answered"], rep["complete"], rep["level"], rep["total"]) == (
        17,
        True,
        3,
        450,
    )
    assert rep["reco_saved"] is False

    # reco PATCH 없이 확정 — 확정이 그 순간 초안을 남긴다(후보는 AX 과정만)
    final = _ok(await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth))
    assert set(final) == DIAGNOSIS_KEYS
    assert (final["status"], final["finalized_by_id"]) == ("final", admin_id)
    assert final["finalized_at"] is not None
    tracks = {t["key"]: t for t in final["reco"]["tracks"]}
    assert set(tracks) == {"cs", "prod"}
    assert all(set(t) == TRACK_KEYS for t in tracks.values())
    # 후보는 공개 AX 과정만 · 직무군마다 id 순 앞 3개(고유 과정은 같은 태그라도 들지 않는다)
    assert (tracks["cs"]["courses"], tracks["prod"]["courses"]) == (
        pool.cs,
        pool.prod[:3],
    )
    assert pool.own not in tracks["cs"]["courses"]
    assert not tracks["cs"]["candidates_missing"]
    assert not tracks["prod"]["candidates_missing"]
    assert (tracks["cs"]["depts"], tracks["prod"]["depts"]) == (["영업"], ["생산"])

    for r in (
        await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth),
        await client.patch(
            f"{ADMIN}/diagnoses/{rid}", headers=auth, json={"answers": ANSWERS_ALL_1}
        ),
        await client.patch(
            f"{ADMIN}/diagnoses/{rid}/reco", headers=auth, json=RECO_SAMPLE
        ),
        await client.delete(f"{ADMIN}/diagnoses/{rid}", headers=auth),
    ):
        problem_of(r, 409, "/problems/conflict")
    kept = _ok(await client.get(f"{ADMIN}/diagnoses/{rid}", headers=auth))
    assert (kept["answers"], kept["reco"]) == (ANSWERS_MIXED, final["reco"])

    r = await client.post(
        f"{ADMIN}/companies/{co}/diagnoses", headers=auth, json={"phase": "post"}
    )
    assert _ok(r, 201)["round_no"] == 2
    assert await _audits(db_session, "diagnosis.finalize") == [
        (str(rid), {"round_no": 1, "answered": 17, "total": 450, "level": 3})
    ]
    created = await _audits(db_session, "diagnosis.create")
    assert [d["round_no"] for _, d in created] == [1, 2]


async def test_diagnosis_finalize_requires_17(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)
    sixteen = {k: v for k, v in ANSWERS_ALL_5.items() if k != "3-3"}
    rid = await _round(client, auth, co, sixteen)

    got = problem_of(
        await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth),
        409,
        "/problems/conflict",
    )
    assert got["missing"] == ["3-3"]
    assert "1" in got["detail"]
    row = _ok(await client.get(f"{ADMIN}/diagnoses/{rid}", headers=auth))
    assert (row["status"], row["finalized_at"], row["reco"]) == ("draft", None, None)
    assert await _audits(db_session, "diagnosis.finalize") == []


async def test_diagnosis_report_scores_and_delta(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    _, x_auth = await approved(db_session, app.state.settings, email="x@example.com")
    co = await _company(client, auth)

    # r1 사전 final(전부 1 → 40 × 4 · 160 · L2 — DEC-003) · 증빙 둘·하나
    r1 = await _round(client, auth, co, ANSWERS_ALL_1)
    await _patch(client, auth, r1, evidence={"0-0": [True, True], "0-1": [True, False]})
    _ok(await client.post(f"{ADMIN}/diagnoses/{r1}:finalize", headers=auth))
    rep = await _report(client, auth, r1)
    assert set(rep) == REPORT_KEYS
    assert (rep["total"], rep["level"], rep["previous"]) == (160, 2, None)
    assert [a["pts"] for a in rep["areas"]] == [40, 40, 40, 40]
    assert [(a["n"], a["done"]) for a in rep["areas"]] == [
        (5, 5),
        (4, 4),
        (4, 4),
        (4, 4),
    ]
    assert all(set(a) == AREA_KEYS for a in rep["areas"])
    assert [i["key"] for i in rep["items"]] == list(ANSWER_KEYS)
    assert all(set(i) == ITEM_KEYS for i in rep["items"])
    assert [i["evidence_count"] for i in rep["items"][:3]] == [2, 1, 0]

    # r2 draft(17개를 답해도 draft 는 비교 대상이 아니다) · r3 링크 제출(review) · r4 사후 final
    await _round(client, auth, co, ANSWERS_ALL_5, phase="post")
    r3, _ = await _submitted_round(client, auth, co, ANSWERS_MIXED)
    r4 = await _round(client, auth, co, ANSWERS_ALL_5, phase="post", finalize=True)

    rep = await _report(client, auth, r4)
    prev = rep["previous"]
    assert set(prev) == PREVIOUS_KEYS
    assert (prev["round_no"], prev["status"], prev["total"], prev["level"]) == (
        3,
        "review",
        450,
        3,
    )
    assert prev["areas"] == [120, 100, 110, 120]
    assert (prev["delta_total"], prev["delta_areas"]) == (350, [80, 100, 90, 80])
    rep = await _report(client, auth, r3)
    assert (rep["status"], rep["mode"], rep["previous"]["round_no"]) == (
        "review",
        "link",
        1,
    )
    assert (rep["previous"]["delta_total"], rep["previous"]["delta_areas"]) == (
        290,
        [80, 60, 70, 80],
    )

    problem_of(
        await client.get(f"{ADMIN}/diagnoses/{r1}/pdf", headers=auth),
        501,
        "/problems/not-implemented",
    )
    for path in (f"{LARGEST}/report", f"{LARGEST}/pdf", f"{LARGEST}"):
        problem_of(await client.get(f"{ADMIN}/diagnoses/{path}", headers=auth), 404)
    got = problem_of(
        await client.get(f"{ADMIN}/diagnoses/{OVERFLOW}/report", headers=auth), 422
    )
    assert locs(got) == [["path", "diagnosis_id"]]
    problem_of(await client.get(f"{ADMIN}/diagnoses/{r1}/report", headers=x_auth), 403)


async def test_diagnosis_reco_patch_and_lock(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    pool = await pool_candidates(db_session, app.state.settings)
    co = await _company(
        client, auth, depts=["영업", "생산", "설계팀"]
    )  # cs · prod · eng
    rid = await _round(client, auth, co, ANSWERS_MIXED)

    rep = await _report(client, auth, rid)
    assert rep["reco_saved"] is False
    tracks = {t["key"]: t for t in rep["reco"]["tracks"]}
    assert set(tracks) == {"cs", "prod", "eng"}
    assert (tracks["eng"]["courses"], tracks["eng"]["candidates_missing"]) == ([], True)
    assert (tracks["cs"]["courses"], tracks["cs"]["candidates_missing"]) == (
        pool.cs,
        False,
    )
    assert (
        _ok(await client.get(f"{ADMIN}/diagnoses/{rid}", headers=auth))["reco"] is None
    )

    saved = _ok(
        await client.patch(
            f"{ADMIN}/diagnoses/{rid}/reco", headers=auth, json=RECO_SAMPLE
        )
    )
    assert saved["reco"] == RECO_SAMPLE
    rep = await _report(client, auth, rid)
    assert (rep["reco_saved"], rep["reco"]) == (True, RECO_SAMPLE)

    track = RECO_SAMPLE["tracks"][0]
    for bad in (
        {**RECO_SAMPLE, "tracks": [track] * 21},
        {**RECO_SAMPLE, "tracks": [{**track, "courses": ["과정"] * 21}]},
        {**RECO_SAMPLE, "common": {**RECO_SAMPLE["common"], "focus": "가" * 501}},
        {**RECO_SAMPLE, "extra": 1},
        {**RECO_SAMPLE, "tracks": [{**track, "extra": 1}]},
        {k: v for k, v in RECO_SAMPLE.items() if k != "poc"},
    ):
        problem_of(
            await client.patch(f"{ADMIN}/diagnoses/{rid}/reco", headers=auth, json=bad),
            422,
        )
    assert (
        _ok(await client.get(f"{ADMIN}/diagnoses/{rid}", headers=auth))["reco"]
        == RECO_SAMPLE
    )
    assert len(await _audits(db_session, "diagnosis.reco")) == 1

    final = _ok(await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth))
    assert final["reco"] == RECO_SAMPLE  # 저장한 것을 그대로 남긴다
    problem_of(
        await client.patch(
            f"{ADMIN}/diagnoses/{rid}/reco", headers=auth, json=RECO_SAMPLE
        ),
        409,
        "/problems/conflict",
    )


async def test_diagnosis_twenty_depts_roundtrip(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth, depts=DEPTS_20)
    rid = await _round(client, auth, co, ANSWERS_MIXED)

    tracks = (await _report(client, auth, rid))["reco"]["tracks"]
    assert len(tracks) == 8  # 부서 20 → 8직무군
    assert sorted(d for t in tracks for d in t["depts"]) == sorted(DEPTS_20)

    def reco(n: int) -> dict[str, Any]:
        return {
            **RECO_SAMPLE,
            "tracks": [
                {
                    "key": f"t{i}",
                    "name": f"트랙 {i}",
                    "depts": [],
                    "courses": [f"과정 {i}"],
                    "candidates_missing": False,
                }
                for i in range(n)
            ],
        }

    problem_of(
        await client.patch(
            f"{ADMIN}/diagnoses/{rid}/reco", headers=auth, json=reco(21)
        ),
        422,
    )
    _ok(
        await client.patch(f"{ADMIN}/diagnoses/{rid}/reco", headers=auth, json=reco(20))
    )
    _ok(await client.post(f"{ADMIN}/diagnoses/{rid}:finalize", headers=auth))
    r = await client.post(
        f"{ADMIN}/courses",
        headers=auth,
        json={**UNDATED_BODY, "start": "diagnosis", "diagnosis_id": rid},
    )
    course_id = _ok(r, 201)["course"]["id"]
    sections = await db_session.scalars(
        select(Section.id).where(Section.course_id == course_id)
    )
    section_ids = list(sections)
    assert len(section_ids) == 21  # 공통교육 + 트랙 20
    per_track = 1 + (1 if RECO_SAMPLE["capstone"] else 0)
    sessions = await count(
        db_session, CourseSession, CourseSession.section_id.in_(section_ids)
    )
    assert sessions == len(RECO_SAMPLE["common"]["items"]) + 20 * per_track


async def test_diagnosis_delete_rules(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)

    r1 = await _round(client, auth, co)
    r2 = await _round(client, auth, co, ANSWERS_ALL_5, finalize=True)
    assert (
        await client.delete(f"{ADMIN}/diagnoses/{r1}", headers=auth)
    ).status_code == 204
    problem_of(await client.get(f"{ADMIN}/diagnoses/{r1}", headers=auth), 404)
    problem_of(await client.delete(f"{ADMIN}/diagnoses/{r1}", headers=auth), 404)
    problem_of(
        await client.delete(f"{ADMIN}/diagnoses/{r2}", headers=auth),
        409,
        "/problems/conflict",
    )
    assert (
        _ok(await client.get(f"{ADMIN}/diagnoses/{r2}", headers=auth))["round_no"] == 2
    )

    # 링크 제출 회차를 지우면 응답을 받지 않은 것으로 — 링크는 revoked(제출 시각은 이력으로 남는다)
    r3, token = await _submitted_round(client, auth, co, ANSWERS_MIXED)
    assert (
        _ok(await client.get(f"{ADMIN}/diagnoses/{r3}", headers=auth))["round_no"] == 3
    )
    assert (
        await client.delete(f"{ADMIN}/diagnoses/{r3}", headers=auth)
    ).status_code == 204
    detail = _ok(await client.get(f"{ADMIN}/companies/{co}", headers=auth))
    (link,) = detail["links"]
    assert (link["state"], link["diagnosis_id"]) == ("revoked", None)
    assert link["submitted_at"] is not None and link["revoked_at"] is not None
    assert [r["round_no"] for r in detail["rounds"]] == [2]
    problem_of(await client.get(f"/v1/ax/{token}"), 410, "/problems/diag-link-revoked")
    r = await client.post(
        f"{ADMIN}/companies/{co}/links", headers=auth, json={"phase": "post"}
    )
    _ok(r, 201)
    assert await count(db_session, Diagnosis, Diagnosis.company_id == co) == 1

    deleted = await _audits(db_session, "diagnosis.delete")
    assert [(t, d["round_no"], d["status"]) for t, d in deleted] == [
        (str(r1), 1, "draft"),
        (str(r3), 3, "review"),
    ]
    revoked = await _audits(db_session, "diag_link.revoke", "diag_link")
    assert [d.get("reason") for _, d in revoked] == ["round_deleted"]
    assert revoked[0][0] == str(link["id"])


async def test_diagnosis_validation_422(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 스키마의 상태·구분 글자 = models 상수(schemas 는 service 를 모른다 — 다시 선언한 글자가 어긋나지 않게)
    assert get_args(Phase) == PHASES
    assert get_args(DiagMode) == MODES
    assert get_args(DiagStatus) == DIAG_STATUSES
    set_today(app, TODAY)
    _, auth = await admin_headers(db_session)
    co = await _company(client, auth)
    visit = await _round(client, auth, co)
    before = _ok(await client.get(f"{ADMIN}/diagnoses/{visit}", headers=auth))

    for body in (
        {"answers": {"0-5": 3}},
        {"answers": {"4-0": 3}},
        {"answers": {"0-0": 0}},
        {"answers": {"0-0": 6}},
        {"answers": None},
        {"evidence": {"0-0": [True, True, True]}},
        {"evidence": {"9-9": [True, False]}},
        {"matrix": {"3-0": 3}},
        {"matrix": {"0-0": 6}},
        {"field": {"work": "가" * 201}},
        {"field": {"tools": ["도구"] * 21}},
        {"field": {"tools": ["가" * 51]}},
        {"field": {"unknown": "x"}},
        {"phase": "mid"},
        {"diagnosed_on": "어제"},
        {"extra": 1},
        {},
    ):
        problem_of(
            await client.patch(f"{ADMIN}/diagnoses/{visit}", headers=auth, json=body),
            422,
        )
    assert _ok(await client.get(f"{ADMIN}/diagnoses/{visit}", headers=auth)) == before
    problem_of(
        await client.post(
            f"{ADMIN}/companies/{co}/diagnoses", headers=auth, json={"phase": "mid"}
        ),
        422,
    )

    # 링크 회차의 제출일은 잠긴다 — 다른 값만 422, 같은 값은 바뀐 칸이 아니다
    linked, _ = await _submitted_round(client, auth, co, ANSWERS_MIXED)
    row = _ok(await client.get(f"{ADMIN}/diagnoses/{linked}", headers=auth))
    assert row["diagnosed_on"] == TODAY.isoformat()
    got = problem_of(
        await client.patch(
            f"{ADMIN}/diagnoses/{linked}",
            headers=auth,
            json={"diagnosed_on": "2026-10-01", "answers": ANSWERS_ALL_5},
        ),
        422,
    )
    assert [(v["loc"], v["type"]) for v in got["violations"]] == [
        (["body", "diagnosed_on"], "frozen_field")
    ]
    assert _ok(await client.get(f"{ADMIN}/diagnoses/{linked}", headers=auth)) == row
    same = await _patch(
        client, auth, linked, diagnosed_on=TODAY.isoformat(), answers=ANSWERS_ALL_5
    )
    assert (same["diagnosed_on"], same["answers"]) == (TODAY.isoformat(), ANSWERS_ALL_5)
    moved = await _patch(client, auth, visit, diagnosed_on="2026-10-01")
    assert moved["diagnosed_on"] == date(2026, 10, 1).isoformat()
