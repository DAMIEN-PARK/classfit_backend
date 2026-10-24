"""AX 진단 표와 crud·service(T9a 결정 iii·iv·v·viii·xi·xvii): 표 제약 · owner_kind 판정 · 회차 번호 · service 전이 ·
회사 삭제 규칙 · 권장 구성 후보 · 비교 기준 · 잠금 호출 자리. 라이브 PG.

행은 crud·service 로 직접 만든다(HTTP 없음). 시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(회차 번호 round_no 는
규칙이라 단언한다). 표 제약 시험은 service 없이 crud·원시 INSERT 로 상태를 박는다(tests/fixtures/diagnosis.py 4단계 몫).
잠금 호출 자리 시험은 src 를 ast 로 읽는다(T7 tests/integration/test_db_record.py 의 _tree·_function·_calls·_first 를
복사했다). 잠금이 실제로 줄 세우는지는 tests/integration/test_db_diag_race.py 가 잰다.
"""

from __future__ import annotations

import ast
import datetime as dt
import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import catalog as crud_catalog
from classfit.crud import company as crud_company
from classfit.crud import course as crud_course
from classfit.crud import diag_link as crud_link
from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud import page as crud_page
from classfit.crud import scope as crud_scope
from classfit.crud.scope import OWNER_KINDS
from classfit.models import AuditLog, Company, Course, DiagLink, Diagnosis, PoolCourse
from classfit.service.auth.sessions import Principal
from classfit.service.diagnosis import companies, reports, rounds
from classfit.service.diagnosis.rounds import FrozenField
from classfit.service.rules.diagnosis import ANSWER_KEYS, score
from classfit.service.rules.reco import build_reco
from tests.fixtures.courses import open_test_course
from tests.fixtures.diagnosis import (
    ACTOR,
    ANSWERS_9,
    ANSWERS_ALL_1,
    ANSWERS_ALL_5,
    ANSWERS_MIXED,
    RECO_SAMPLE,
    RESPONDENT_EMAIL,
    TODAY,
    insert_link,
    insert_round,
    make_company,
    make_link,
    make_round,
    make_token,
    pool_candidates,
    submit_via_service,
)
from tests.fixtures.instructors import count

ADMIN = Principal("admin", 1)
SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"


async def _violates(
    db: AsyncSession, stmt: Any, sqlstate: str, constraint: str | None = None
) -> None:
    """SAVEPOINT 안에서 stmt 가 sqlstate(그리고 그 제약 이름)로 실패하는지."""
    tx = await db.begin_nested()
    with pytest.raises(IntegrityError) as caught:
        await db.execute(stmt)
    await tx.rollback()
    assert caught.value.orig.sqlstate == sqlstate, caught.value
    if constraint is not None:
        assert caught.value.orig.diag.constraint_name == constraint, caught.value


async def test_diagnosis_table_checks(db_session: AsyncSession) -> None:
    db = db_session
    companies = Company.__table__
    rounds = Diagnosis.__table__
    links = DiagLink.__table__
    base_company = {"name": "A사", "contact": "담당자 가"}
    for change, name in [
        ({"size": "10명 미만"}, "size"),
        ({"name": "   "}, "name"),
        ({"name": "\n\t"}, "name"),  # 공백류만(btrim 은 스페이스만 지운다)
        ({"contact": " \t"}, "contact"),
        ({"depts": [f"부서 {i}" for i in range(21)]}, "depts"),
    ]:
        await _violates(
            db,
            insert(companies).values(**(base_company | change)),
            "23514",
            f"ck_company_{name}",
        )
    twenty = await make_company(db, depts=[f"부서 {i}" for i in range(20)])
    assert len(twenty.depts) == 20  # 상한 20 은 된다
    company = await make_company(db)
    other = await make_company(db, name="B사")

    base_round = {
        "company_id": company.id,
        "round_no": 1,
        "phase": "pre",
        "mode": "visit",
        "status": "draft",
        "diagnosed_on": TODAY,
        "created_by": "admin:1",
    }
    finalized = dt.datetime(2026, 11, 3, 10, tzinfo=dt.UTC)
    for change, name in [
        ({"round_no": 0}, "round_no"),
        ({"phase": "mid"}, "phase"),
        ({"mode": "self"}, "mode"),
        ({"status": "submitted"}, "status"),
        ({"respondent": {"name": "응답자 가"}}, "respondent"),  # visit 인데 응답자
        ({"status": "final"}, "finalized_status"),  # final 인데 확정 시각 없음
        (
            {"finalized_at": finalized, "finalized_by_id": 1},
            "finalized_status",
        ),  # draft 인데 확정 시각·확정자
        (
            {"status": "final", "finalized_at": finalized},
            "finalized_pair",
        ),  # 확정자 없음
    ]:
        await _violates(
            db,
            insert(rounds).values(**(base_round | change)),
            "23514",
            f"ck_diagnosis_{name}",
        )
    first = await insert_round(db, company.id, round_no=1)
    await _violates(
        db,
        insert(rounds).values(**base_round),
        "23505",
        "uq_diagnosis_company_id_round_no",
    )
    # 다른 회사는 같은 번호를 쓴다
    other_round = await insert_round(db, other.id, round_no=1)
    linked = await insert_round(
        db, company.id, round_no=2, mode="link", respondent={"name": "응답자 가"}
    )

    base_link = {
        "company_id": company.id,
        "token": make_token("checks-base"),
        "phase": "pre",
        "issued_on": TODAY,
        "expires_on": TODAY + dt.timedelta(days=14),
        "status": "open",
    }
    now = dt.datetime(2026, 11, 3, 11, tzinfo=dt.UTC)
    for change, name in [
        ({"token": make_token("short")[:31]}, "token"),
        ({"token": make_token("long") + "a"}, "token"),
        ({"token": "가" * 32}, "token"),
        ({"token": "a" * 31 + "."}, "token"),
        ({"phase": "mid"}, "phase"),
        ({"expires_on": TODAY - dt.timedelta(days=1)}, "period"),
        ({"status": "expired"}, "status"),
        ({"status": "submitted"}, "submitted_at"),  # 제출 시각 없음
        ({"status": "revoked"}, "revoked_at"),  # 회수 시각 없음
        ({"submitted_at": now}, "submitted_history"),  # open 인데 제출 시각
        ({"diagnosis_id": linked.id}, "diagnosis_submitted"),  # open 인데 회차
    ]:
        await _violates(
            db,
            insert(links).values(**(base_link | change)),
            "23514",
            f"ck_diag_link_{name}",
        )
    await db.execute(insert(links).values(**base_link))
    # 같은 토큰 · 같은 회사의 open 둘(부분 유일)
    await _violates(
        db,
        insert(links).values(**(base_link | {"company_id": other.id})),
        "23505",
        "uq_diag_link_token",
    )
    await _violates(
        db,
        insert(links).values(**(base_link | {"token": make_token("checks-2")})),
        "23505",
        "uq_diag_link_company_open",
    )
    # revoked 둘은 된다 · revoked 인데 submitted_at 있음(이력)도 된다
    revoked = base_link | {"status": "revoked", "revoked_at": now}
    await db.execute(insert(links).values(**(revoked | {"token": make_token("r1")})))
    await db.execute(
        insert(links).values(
            **(revoked | {"token": make_token("r2"), "submitted_at": now})
        )
    )
    # 제출한 링크 둘이 한 회차를 가리킬 수 없다
    submitted = base_link | {
        "status": "submitted",
        "submitted_at": now,
        "diagnosis_id": linked.id,
    }
    await db.execute(insert(links).values(**(submitted | {"token": make_token("s1")})))
    await _violates(
        db,
        insert(links).values(**(submitted | {"token": make_token("s2")})),
        "23505",
        "uq_diag_link_diagnosis_id",
    )
    # 도우미의 상태 박기(open 으로 넣은 뒤 submitted) — 다른 회사
    stamped = await insert_link(
        db,
        other.id,
        token=make_token("other-submitted"),
        status="submitted",
        diagnosis_id=other_round.id,
    )
    assert (stamped.status, stamped.diagnosis_id) == ("submitted", other_round.id)
    assert stamped.submitted_at is not None and stamped.revoked_at is None
    # 링크가 가리키는 회차를 직접 지우면 23503(NO ACTION) — 삭제 경로는 crud.diagnosis.delete_diagnosis 가 먼저 푼다
    await _violates(
        db,
        delete(rounds).where(rounds.c.id == linked.id),
        "23503",
        "fk_diag_link_diagnosis_id_diagnosis",
    )

    # 강의 연결은 SET NULL, 회차·링크는 CASCADE(DB 수준)
    course, _ = await open_test_course(db)
    await db.execute(
        update(Course).where(Course.id == course.id).values(company_id=company.id)
    )
    assert await count(db, Diagnosis, Diagnosis.company_id == company.id) == 2
    assert await count(db, DiagLink, DiagLink.company_id == company.id) == 4
    await db.execute(delete(companies).where(companies.c.id == company.id))
    assert await count(db, Diagnosis, Diagnosis.company_id == company.id) == 0
    assert await count(db, DiagLink, DiagLink.company_id == company.id) == 0
    assert await count(db, Diagnosis, Diagnosis.id == first.id) == 0
    linked_to = await db.scalar(
        select(Course.company_id)
        .where(Course.id == course.id)
        .execution_options(populate_existing=True)
    )
    assert linked_to is None
    assert await count(db, Diagnosis, Diagnosis.company_id == other.id) == 1


async def test_diagnosis_owner_kind_judgment(db_session: AsyncSession) -> None:
    check = OWNER_KINDS["diagnosis_pdf"]
    assert await check(db_session, ADMIN, 1) is True
    assert (
        await check(db_session, ADMIN, 2**62) is True
    )  # 행을 만드는 경로가 없어 owner_id 를 보지 않는다
    for kind in ("instructor", "learner", "system"):
        assert await check(db_session, Principal(kind, 1, 1), 1) is False, kind
    # owner_kind 글자는 등록부 한 곳에만 — 행을 만드는 경로가 없다(PDF 501)
    quoted = '"diagnosis_pdf"'
    hits = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if quoted in path.read_text(encoding="utf-8")
    )
    assert hits == ["crud/scope.py"]


# ── 5단계: service 수준(운영 경로)


def _settings() -> Settings:
    return Settings(_env_file=None)


async def _audits(db: AsyncSession, action: str) -> list[AuditLog]:
    rows = await db.scalars(
        select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
    )
    return list(rows.all())


async def test_diagnosis_round_numbers(db_session: AsyncSession) -> None:
    db = db_session
    company = await make_company(db)
    r1 = await make_round(db, company.id, phase="pre")
    r2 = await make_round(db, company.id, phase="post")
    r3 = await make_round(db, company.id, phase="pre")
    assert [r.round_no for r in (r1, r2, r3)] == [1, 2, 3]
    await rounds.delete_round(db, diagnosis_id=r2.id, actor=ACTOR)
    r4 = await make_round(db, company.id)
    assert r4.round_no == 4  # 중간 번호는 당기지 않는다(최대 + 1)
    await rounds.delete_round(db, diagnosis_id=r4.id, actor=ACTOR)
    again = await make_round(db, company.id, phase="post")
    assert again.round_no == 4  # 마지막 번호를 지우면 다음 회차가 그 번호를 다시 받는다
    link = await make_link(db, company.id)
    submitted = await submit_via_service(db, link.token)
    assert (submitted.round_no, submitted.mode, submitted.status) == (
        5,
        "link",
        "review",
    )
    other = await make_company(db, name="B사")
    assert (await make_round(db, other.id)).round_no == 1  # 회사마다 따로
    numbers = [r.round_no for r in await crud_diagnosis.list_rounds(db, company.id)]
    assert numbers == [1, 3, 4, 5]


async def test_diagnosis_service_transitions(db_session: AsyncSession) -> None:
    db = db_session
    company = await make_company(db)
    # D1 — draft · visit
    row = await rounds.create_round(
        db, company_id=company.id, phase="pre", diagnosed_on=TODAY, actor=ACTOR
    )
    assert (row.status, row.mode, row.round_no, row.created_by) == (
        "draft",
        "visit",
        1,
        ACTOR,
    )
    (created,) = await _audits(db, "diagnosis.create")
    assert created.detail == {
        "company_id": company.id,
        "round_no": 1,
        "phase": "pre",
        "mode": "visit",
    }
    # D2 · D3 — 바뀐 칸만 쓰고, 같은 값이면 audit 없음
    rid = row.id
    row = await rounds.patch_round(
        db, diagnosis_id=rid, fields={"answers": ANSWERS_9}, actor=ACTOR
    )
    assert row.answers == ANSWERS_9
    await rounds.patch_round(
        db,
        diagnosis_id=rid,
        fields={"answers": ANSWERS_9, "phase": "pre"},
        actor=ACTOR,
    )
    (updated,) = await _audits(db, "diagnosis.update")
    assert updated.detail == {"fields": ["answers"]}
    # 방문 회차는 진단일을 바꿀 수 있다
    await rounds.patch_round(
        db,
        diagnosis_id=rid,
        fields={"diagnosed_on": TODAY - dt.timedelta(days=1)},
        actor=ACTOR,
    )
    # D6 — 16개로 확정 409(미응답 1)
    sixteen = {k: 3 for k in ANSWER_KEYS[:16]}
    await rounds.patch_round(
        db, diagnosis_id=rid, fields={"answers": sixteen}, actor=ACTOR
    )
    with pytest.raises(Conflict) as caught:
        await rounds.finalize_round(db, diagnosis_id=rid, admin_id=1, actor=ACTOR)
    assert caught.value.extra == {"missing": [ANSWER_KEYS[16]]}
    # D8 — 확정 전 권장 구성 저장, 같은 값이면 audit 없음
    await rounds.save_reco(db, diagnosis_id=rid, reco=RECO_SAMPLE, actor=ACTOR)
    await rounds.save_reco(db, diagnosis_id=rid, reco=RECO_SAMPLE, actor=ACTOR)
    assert len(await _audits(db, "diagnosis.reco")) == 1
    # D5 — 17개 확정: 저장한 reco 를 스냅샷
    await rounds.patch_round(
        db, diagnosis_id=rid, fields={"answers": ANSWERS_MIXED}, actor=ACTOR
    )
    row = await rounds.finalize_round(db, diagnosis_id=rid, admin_id=1, actor=ACTOR)
    assert row.status == "final" and row.finalized_at is not None
    assert row.finalized_by_id == 1 and row.reco == RECO_SAMPLE
    (finalized,) = await _audits(db, "diagnosis.finalize")
    assert finalized.detail == {"round_no": 1, "answered": 17, "total": 450, "level": 3}
    # D4 · D7 — final 은 고치기·권장 구성·재확정·지우기 409, audit 그대로
    before = await count(db, AuditLog)
    for attempt in (
        rounds.patch_round(
            db, diagnosis_id=rid, fields={"answers": ANSWERS_ALL_5}, actor=ACTOR
        ),
        rounds.save_reco(db, diagnosis_id=rid, reco={}, actor=ACTOR),
        rounds.finalize_round(db, diagnosis_id=rid, admin_id=1, actor=ACTOR),
        rounds.delete_round(db, diagnosis_id=rid, actor=ACTOR),
    ):
        with pytest.raises(Conflict):
            await attempt
    assert await count(db, AuditLog) == before
    # reco 를 저장하지 않고 확정하면 그 순간 초안(후보 포함)을 스냅샷한다
    plain = await make_round(db, company.id, answers=ANSWERS_ALL_1)
    plain = await rounds.finalize_round(
        db, diagnosis_id=plain.id, admin_id=1, actor=ACTOR
    )
    expected = build_reco(
        score=score(ANSWERS_ALL_1),
        answers=ANSWERS_ALL_1,
        field={},
        matrix={},
        depts=company.depts,
        candidates=await reports.candidate_titles(db),
    )
    assert plain.reco == expected
    # review(링크 제출) — 답은 고치고, 제출일은 다른 값이면 FrozenField · 같은 값이면 바뀐 칸 아님
    link = await make_link(db, company.id, phase="post")
    review = await submit_via_service(db, link.token)
    assert review.respondent is not None
    assert review.respondent["email"] == RESPONDENT_EMAIL
    review = await rounds.patch_round(
        db, diagnosis_id=review.id, fields={"answers": ANSWERS_ALL_5}, actor=ACTOR
    )
    with pytest.raises(FrozenField) as frozen:
        await rounds.patch_round(
            db,
            diagnosis_id=review.id,
            fields={"diagnosed_on": TODAY - dt.timedelta(days=3)},
            actor=ACTOR,
        )
    assert frozen.value.field == "diagnosed_on"
    await rounds.patch_round(
        db, diagnosis_id=review.id, fields={"diagnosed_on": TODAY}, actor=ACTOR
    )
    # D9 — 링크 회차 삭제: 링크 revoked · 회차 연결 풀림 · 제출 시각은 이력
    await rounds.delete_round(db, diagnosis_id=review.id, actor=ACTOR)
    found = await crud_link.get_by_token(db, link.token, fresh=True)
    assert found is not None
    gone = found[0]
    assert (gone.status, gone.diagnosis_id) == ("revoked", None)
    assert gone.submitted_at is not None and gone.revoked_at is not None
    assert await crud_diagnosis.get_diagnosis(db, review.id) is None
    deleted = await _audits(db, "diagnosis.delete")
    assert [a.detail for a in deleted] == [
        {"company_id": company.id, "round_no": 3, "status": "review"}
    ]
    revoked = await _audits(db, "diag_link.revoke")
    assert [a.detail for a in revoked] == [
        {"token_prefix": link.token[:8], "reason": "round_deleted"}
    ]
    with pytest.raises(NotFound):
        await rounds.patch_round(
            db, diagnosis_id=review.id, fields={"phase": "pre"}, actor=ACTOR
        )


async def test_company_service_delete_rules(db_session: AsyncSession) -> None:
    db = db_session
    company = await make_company(db)
    course, _ = await open_test_course(db, company_id=company.id)
    assert course.company_id == company.id
    await make_round(db, company.id)
    await make_link(db, company.id)
    with pytest.raises(Conflict) as caught:
        await companies.delete_company(db, company_id=company.id, actor=ACTOR)
    assert caught.value.extra == {"active_courses": 1}
    assert await crud_company.get_company(db, company.id) is not None
    # 보관하면 지워진다 — 보관 강의의 연결은 풀리고 회차·링크는 같이 지워진다
    await crud_course.update_course(db, course, archived_at=dt.datetime.now(dt.UTC))
    await companies.delete_company(db, company_id=company.id, actor=ACTOR)
    assert await crud_company.get_company(db, company.id) is None
    linked = await db.scalar(
        select(Course.company_id)
        .where(Course.id == course.id)
        .execution_options(populate_existing=True)
    )
    assert linked is None
    assert await count(db, Diagnosis, Diagnosis.company_id == company.id) == 0
    assert await count(db, DiagLink, DiagLink.company_id == company.id) == 0
    (deleted,) = await _audits(db, "company.delete")
    assert deleted.detail == {"rounds": 1, "links": 1, "unlinked_courses": 1}
    with pytest.raises(NotFound):
        await companies.delete_company(db, company_id=company.id, actor=ACTOR)
    with pytest.raises(NotFound):
        await open_test_course(db, company_id=company.id)  # 없는 회사 연결 404


async def test_diagnosis_report_candidates_ax_only(db_session: AsyncSession) -> None:
    db = db_session
    pool = await pool_candidates(db, _settings())
    candidates = await reports.candidate_titles(db)
    assert set(candidates) == {"eng", "cs", "buy", "prod", "qa", "vis", "film", "mgt"}
    assert candidates["cs"] == pool.cs  # AX 2개뿐 — 같은 태그의 고유 과정은 빠진다
    assert pool.own not in candidates["cs"]
    assert candidates["prod"] == pool.prod[:3]  # 앞 3개 한도
    assert candidates["film"] == pool.prod[:3]  # prod·film 은 같은 태그(알려진 한계)
    assert candidates["eng"] == []
    company = await make_company(db)  # 부서 영업·생산 → cs · prod
    draft = await make_round(db, company.id, answers=ANSWERS_MIXED)
    report = await reports.report_of(db, diagnosis_id=draft.id)
    assert report.reco_saved is False
    tracks = {t["key"]: t for t in report.reco["tracks"]}
    assert set(tracks) == {"cs", "prod"}
    assert tracks["cs"]["courses"] == pool.cs
    assert tracks["prod"]["courses"] == pool.prod[:3]
    assert not tracks["cs"]["candidates_missing"]
    # 고유 과정을 비공개로 돌려도 결과가 같다(애초에 후보가 아니다)
    own = await db.scalar(select(PoolCourse).where(PoolCourse.title == pool.own))
    assert own is not None and own.source == "own"
    own.pub = False
    await db.flush()
    assert await reports.candidate_titles(db) == candidates


async def test_diagnosis_report_delta_is_live(db_session: AsyncSession) -> None:
    db = db_session
    company = await make_company(db)
    r1 = await make_round(db, company.id, answers=ANSWERS_ALL_1, status="final")
    # draft — 비교 대상이 아니다
    r2 = await make_round(db, company.id, answers=ANSWERS_ALL_5)
    link = await make_link(db, company.id)
    r3 = await submit_via_service(db, link.token, answers=ANSWERS_MIXED)
    r4 = await make_round(
        db, company.id, answers=ANSWERS_ALL_5, status="final", phase="post"
    )
    assert [r.round_no for r in (r1, r2, r3, r4)] == [1, 2, 3, 4]
    report = await reports.report_of(db, diagnosis_id=r4.id)
    assert report.previous is not None
    assert (report.previous.round_no, report.previous.status) == (3, "review")
    assert (report.previous.total, report.previous.delta_total) == (450, 350)
    assert report.previous.delta_areas == [80, 100, 90, 80]
    early = await reports.report_of(db, diagnosis_id=r3.id)
    # r2 draft 건너뜀
    assert early.previous is not None and early.previous.round_no == 1
    # 비교 대상(review)을 고치면 다음 읽기의 증감이 바뀐다 — 스냅샷이 없다
    await rounds.patch_round(
        db, diagnosis_id=r3.id, fields={"answers": ANSWERS_ALL_5}, actor=ACTOR
    )
    report = await reports.report_of(db, diagnosis_id=r4.id)
    assert report.previous is not None
    assert (report.previous.total, report.previous.delta_total) == (800, 0)
    # 지우면 그 앞 완료 회차(r1 final)로 — r1 은 final 이라 더 지울 수 없다(D4)
    await rounds.delete_round(db, diagnosis_id=r3.id, actor=ACTOR)
    report = await reports.report_of(db, diagnosis_id=r4.id)
    assert report.previous is not None
    assert (report.previous.round_no, report.previous.delta_total) == (1, 640)
    first = await reports.report_of(db, diagnosis_id=r1.id)
    assert first.previous is None
    with pytest.raises(NotFound):
        await reports.report_of(db, diagnosis_id=r3.id)


async def test_company_list_survives_rows_deleted_between_queries(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """목록(쪽 → 회차 요약)·상세(회사 → 회차·링크·강의 → 요약)는 여러 문장이다. 그 사이 회사가 지워져도(READ COMMITTED 의
    다음 문장이 다른 연결의 커밋을 보는 꼴을 같은 세션의 DELETE 로 흉내 낸다) KeyError 500 이 아니다 — 요약은 비고
    목록 줄·상세 머리는 첫 문장에서 읽은 값 그대로다(T7·T8 두 문장 회귀 시험 꼴)."""
    db = db_session
    keep = await make_company(db)
    gone = await make_company(db, name="B사")
    await make_round(db, keep.id, answers=ANSWERS_MIXED, status="final")
    await make_round(db, gone.id, answers=ANSWERS_ALL_1, status="final")
    real_summaries = crud_company.round_summaries
    real_rounds = crud_diagnosis.list_rounds
    deleted: list[int] = []

    async def delete_company_first(company_id: int) -> None:
        await db.execute(delete(Company).where(Company.id == company_id))
        deleted.append(company_id)

    async def delete_then_summaries(session: AsyncSession, company_ids: Any) -> Any:
        if not deleted:  # 첫 문장(keyset_page) 뒤 · 요약 문장 앞
            await delete_company_first(gone.id)
        return await real_summaries(session, company_ids)

    monkeypatch.setattr(crud_company, "round_summaries", delete_then_summaries)
    items, _, has_more = await companies.company_list(
        db, ADMIN, q=None, cursor=None, limit=10
    )
    assert deleted == [gone.id] and has_more is False
    by_id = {view.company.id: view for view in items}
    assert set(by_id) == {keep.id, gone.id}
    assert by_id[gone.id].last_round is None
    assert by_id[gone.id].latest_final_round is None
    kept = by_id[keep.id].latest_final_round
    assert kept is not None and (kept.round_no, kept.level) == (1, 3)

    monkeypatch.setattr(crud_company, "round_summaries", real_summaries)
    other = await make_company(db, name="C사")
    await make_round(db, other.id, answers=ANSWERS_MIXED)
    await make_link(db, other.id)

    async def delete_then_rounds(session: AsyncSession, company_id: int) -> Any:
        await delete_company_first(company_id)  # 회사 머리 문장 뒤 · 회차 문장 앞
        return await real_rounds(session, company_id)

    monkeypatch.setattr(crud_diagnosis, "list_rounds", delete_then_rounds)
    detail = await companies.company_detail(db, company_id=other.id, today=TODAY)
    assert detail.company.id == other.id
    assert (detail.rounds, detail.links, detail.courses) == ([], [], [])
    assert detail.last_round is None and detail.latest_final_round is None


# ── 잠금 호출 자리(결정 xvii). T7 tests/integration/test_db_record.py 의 정적 도우미를 복사했다

# 회사 행 잠금 아래의 쓰기 열(결정 xi 아홉 + 회사 PATCH — codex 구현 리뷰 1차 ④). 각 파일의 공개 async def 중 쓰기를
# 부르는 것은 이 열 + 잠그지 않는 하나(회사 만들기)뿐이다
DIAG_WRITERS = {
    "service/diagnosis/links.py": ("issue_link", "revoke_link"),
    "service/diagnosis/public.py": ("submit",),
    "service/diagnosis/rounds.py": (
        "create_round",
        "patch_round",
        "save_reco",
        "finalize_round",
        "delete_round",
    ),
    "service/diagnosis/companies.py": ("patch_company", "delete_company"),
}
UNLOCKED_WRITERS = {"create_company"}  # 새 행 하나
DIAG_FILES = (
    "service/diagnosis/companies.py",
    "service/diagnosis/links.py",
    "service/diagnosis/public.py",
    "service/diagnosis/reports.py",
    "service/diagnosis/rounds.py",
)
DIAG_WRITE_CALLS = {
    "insert_company",
    "update_company",
    "delete_company",
    "insert_link",
    "update_link",
    "insert_diagnosis",
    "update_diagnosis",
    "finalize_row",
    "delete_diagnosis",
    "insert_audit",
}
# 잠근 뒤 대상을 다시 읽는 호출(②). fresh 표시는 fresh=True 를 함께 본다. None 은 잠금 자체가 새로 읽는 것(populate_existing)
DIAG_REREAD: dict[str, tuple[str, bool] | None] = {
    "issue_link": ("open_links", False),
    "revoke_link": ("get_by_token", True),
    "submit": ("get_by_token", True),
    "create_round": ("next_round_no", False),
    "patch_round": ("get_diagnosis", True),
    "save_reco": ("get_diagnosis", True),
    "finalize_round": ("get_diagnosis", True),
    "delete_round": ("get_diagnosis", True),
    "patch_company": None,
    "delete_company": ("active_course_count", False),
}
DIAG_CRUD: tuple[ModuleType, ...] = (
    crud_audit,
    crud_catalog,
    crud_company,
    crud_course,
    crud_diagnosis,
    crud_link,
    crud_page,
    crud_scope,
)


@dataclass(frozen=True)
class _Call:
    owner: str | None  # 받는 이름(crud_company.lock_company 면 crud_company)
    name: str
    at: tuple[int, int]  # (줄, 칸)
    keywords: dict[str, str] = field(
        default_factory=dict
    )  # 키워드 이름 → 값 글자(ast.unparse)


def _tree(relpath: str) -> ast.Module:
    return ast.parse((SRC / relpath).read_text(encoding="utf-8"))


def _function(relpath: str, function: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    (body,) = [
        node
        for node in ast.walk(_tree(relpath))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name == function
    ]
    return body


def _calls(node: ast.AST) -> list[_Call]:
    """node 안의 호출을 소스 순서(줄, 칸)로. ast.walk 는 소스 순서를 보장하지 않는다."""
    found: list[_Call] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        keywords = {k.arg: ast.unparse(k.value) for k in sub.keywords if k.arg}
        func = sub.func
        if isinstance(func, ast.Attribute):
            owner = func.value.id if isinstance(func.value, ast.Name) else None
            found.append(
                _Call(owner, func.attr, (sub.lineno, sub.col_offset), keywords)
            )
        elif isinstance(func, ast.Name):
            found.append(_Call(None, func.id, (sub.lineno, sub.col_offset), keywords))
    return sorted(found, key=lambda c: c.at)


def _first(calls: list[_Call], name: str, where: str) -> tuple[int, int]:
    hits = [c.at for c in calls if c.name == name]
    assert hits, f"{where}: {name}( 호출이 없다"
    return hits[0]


def _crud_names() -> set[str]:
    return {
        name
        for module in DIAG_CRUD
        for name, value in vars(module).items()
        if inspect.isfunction(value) and value.__module__ == module.__name__
    }


def test_diagnosis_lock_call_sites() -> None:
    crud_names = _crud_names()
    # ① 잠금이 첫 쓰기 앞 · ② 잠근 뒤 대상 다시 읽기 · 잠근 뒤 session.get 없음 · crud 는 별칭 속성
    for relpath, functions in DIAG_WRITERS.items():
        for fn in functions:
            where = f"{relpath}::{fn}"
            calls = _calls(_function(relpath, fn))
            lock = _first(calls, "lock_company", where)
            writes = [c.at for c in calls if c.name in DIAG_WRITE_CALLS]
            assert writes and lock < min(writes), f"{where}: 쓰기가 잠금 앞이다"
            expected = DIAG_REREAD[fn]
            if expected is not None:
                reread, fresh = expected
                assert any(
                    c.name == reread
                    and lock < c.at < min(writes)
                    and (not fresh or c.keywords.get("fresh") == "True")
                    for c in calls
                ), f"{where}: 잠근 뒤 {reread}{'(fresh=True)' if fresh else ''} 가 없다"
            else:  # 잠근 행으로 비교한다 — 잠그기 전 getter 가 없다
                assert not any(c.name == "get_company" for c in calls), where
            assert not any(c.owner == "session" and c.name == "get" for c in calls)
            bare = [
                c.name
                for c in calls
                if c.name in crud_names and not (c.owner or "").startswith("crud_")
            ]
            assert bare == [], f"{where}: crud 를 별칭 밖에서 부른다 — {bare}"
    # ④ crud 는 `from classfit.crud import x as crud_…` 로만 들인다(함수를 직접 들이지 않는다 — diag_link 는 crud_link)
    for relpath in (*DIAG_FILES, "service/courses/start_diagnosis.py"):
        for node in ast.walk(_tree(relpath)):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module == "classfit.crud":
                assert all((a.asname or "").startswith("crud_") for a in node.names), (
                    relpath
                )
            elif module.startswith("classfit.crud."):
                loaded = importlib.import_module(module)
                for alias in node.names:
                    assert not inspect.isfunction(getattr(loaded, alias.name)), (
                        relpath,
                        alias.name,
                    )
    # ⑤ 쓰기를 부르는 공개 async def 는 아홉 + 잠그지 않는 둘뿐(규약 밖 새 쓰기 함수를 막는다)
    writers = {
        node.name
        for relpath in DIAG_FILES
        for node in _tree(relpath).body
        if isinstance(node, ast.AsyncFunctionDef)
        and not node.name.startswith("_")
        and any(c.name in DIAG_WRITE_CALLS for c in _calls(node))
    }
    locked = {fn for functions in DIAG_WRITERS.values() for fn in functions}
    assert writers == locked | UNLOCKED_WRITERS, writers
    # 회사 삭제: 회사 → 활성 수 → 연결 강의 id 오름차순 잠금 → 연결 풀기·삭제(codex 1차 ③)
    calls = _calls(_function("service/diagnosis/companies.py", "delete_company"))
    where = "companies.delete_company"
    assert (
        _first(calls, "lock_company", where)
        < _first(calls, "active_course_count", where)
        < _first(calls, "lock_linked_courses", where)
        < _first(calls, "delete_company", where)
    )
    # ③ 개설: 회사 확인은 starts.load 한 곳(hold_company → 시작점 갈래) · ③ 은 hold_company → fresh 다시 읽기 ·
    #    세션 넣기에 강사·풀·커리큘럼 참조 없음
    load = _calls(_function("service/courses/starts.py", "load"))
    hold = _first(load, "hold_company", "starts.load")
    assert hold < _first(load, "load_diagnosis", "starts.load")
    assert hold < _first(load, "load_clone", "starts.load")
    assert hold < _first(load, "load_curriculum", "starts.load")
    assert not any(
        c.name == "hold_company" for c in _calls(_tree("service/courses/open.py"))
    )
    source = _calls(_function("service/courses/start_diagnosis.py", "load_diagnosis"))
    hold = _first(source, "hold_company", "load_diagnosis")
    assert any(
        c.name == "get_diagnosis" and c.at > hold and c.keywords.get("fresh") == "True"
        for c in source
    ), "load_diagnosis: hold_company 뒤 get_diagnosis(fresh=True) 가 없다"
    inserts = [
        c
        for c in _calls(
            _function("service/courses/start_diagnosis.py", "apply_diagnosis")
        )
        if c.name == "insert_session"
    ]
    assert inserts
    for c in inserts:
        assert not {"instructor_id", "pool_course_id", "curriculum_id"} & set(
            c.keywords
        )
    # ⑥ crud/company.py 의 행 잠금은 lock_company(FOR UPDATE)·hold_company(FOR KEY SHARE)·lock_linked_courses(강의 id
    #    오름차순 FOR UPDATE) 세 자리뿐
    tree = _tree("crud/company.py")
    owners = [
        node.name
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        for c in _calls(node)
        if c.name == "with_for_update"
    ]
    assert sorted(owners) == ["hold_company", "lock_company", "lock_linked_courses"]
    linked_src = ast.unparse(_function("crud/company.py", "lock_linked_courses"))
    assert "order_by(Course.id)" in linked_src
    hold_src = ast.unparse(_function("crud/company.py", "hold_company"))
    assert "key_share=True" in hold_src and "read=True" in hold_src
    # ⑦ owner_kind 글자는 등록부 한 곳에만
    quoted = '"diagnosis_pdf"'
    assert sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if quoted in path.read_text(encoding="utf-8")
    ) == ["crud/scope.py"]
    # ⑧ 권장 구성 규칙은 DB 를 모르고 후보를 인자로 받는다 · 후보 읽기는 reports.candidate_titles 한 곳 ·
    #    무거운 published_catalog 는 진단 쪽 어디에도 없다
    reco_imports = [
        node.module or ""
        for node in ast.walk(_tree("service/rules/reco.py"))
        if isinstance(node, ast.ImportFrom)
    ]
    assert not [
        m for m in reco_imports if m.startswith(("classfit.crud", "classfit.models"))
    ]
    build = _function("service/rules/reco.py", "build_reco")
    assert "candidates" in [a.arg for a in build.args.kwonlyargs]
    readers = [
        (relpath, node.name)
        for relpath in (*DIAG_FILES, "service/courses/start_diagnosis.py")
        for node in ast.walk(_tree(relpath))
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        for c in _calls(node)
        if c.name == "published_ax_courses"
    ]
    assert readers == [("service/diagnosis/reports.py", "candidate_titles")]
    for relpath in (*DIAG_FILES, "service/courses/start_diagnosis.py"):
        text = (SRC / relpath).read_text(encoding="utf-8")
        assert "published_catalog(" not in text, relpath
