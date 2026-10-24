"""AX 진단 표와 crud·service(T9a 결정 iii·iv·v·viii·xi·xvii): 표 제약 · owner_kind 판정 · 회차 번호 · service 전이 ·
회사 삭제 규칙 · 권장 구성 후보 · 비교 기준 · 잠금 호출 자리. 라이브 PG.

행은 crud·service 로 직접 만든다(HTTP 없음). 시험 안에서 행 id·시퀀스 번호를 단언하지 않는다(회차 번호 round_no 는
규칙이라 단언한다). 표 제약 시험은 service 없이 crud·원시 INSERT 로 상태를 박는다(tests/fixtures/diagnosis.py 4단계 몫).
잠금 호출 자리 시험은 src 를 ast 로 읽는다(T7 tests/integration/test_db_record.py 의 _tree·_function·_calls·_first 를
복사했다). 잠금이 실제로 줄 세우는지는 tests/integration/test_db_diag_race.py 가 잰다.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.scope import OWNER_KINDS
from classfit.models import Company, Course, DiagLink, Diagnosis
from classfit.service.auth.sessions import Principal
from tests.fixtures.courses import open_test_course
from tests.fixtures.diagnosis import (
    TODAY,
    insert_link,
    insert_round,
    make_company,
    make_token,
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
    other_round = await insert_round(db, other.id, round_no=1)  # 다른 회사는 같은 번호를 쓴다
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
