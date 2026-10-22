"""과정 풀 표(0006, Design 부록 A T4): 공개 카탈로그 · source·소유자·난이도·직무군 CHECK · 역량 유일 · 차시 유일·CASCADE ·
파일 행 file_id 유일 · 역량 삭제가 파일 행과 stored_file 행을 같은 트랜잭션에서 지움. 라이브 PG.

alembic check 는 CHECK 를 비교하지 않으므로 여기서 잰다. 행은 crud 로 직접 만든다(HTTP 픽스처 없음, worker-b 픽스처 미사용).
강사는 T3 make_instructor(단일 진입점 signup)로 만든다.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.core.errors import Conflict
from classfit.crud import pool_file
from classfit.crud.advanced import insert_advanced
from classfit.crud.capability import delete_capability, get_or_create_capability
from classfit.crud.catalog import published_catalog
from classfit.crud.curriculum import insert_curriculum, replace_slots
from classfit.crud.pool import insert_pool_course
from classfit.crud.stored_file import insert_stored_file
from classfit.models import (
    Capability,
    CapabilityFile,
    Curriculum,
    CurriculumSlot,
    StoredFile,
)
from tests.fixtures.instructors import make_instructor

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
NOW = dt.datetime(2026, 10, 22, 9, 0, tzinfo=dt.UTC)

# 결정 vii 의 출력 칸(정확히)
COURSE_KEYS = {
    "id",
    "source",
    "title",
    "job_groups",
    "difficulty",
    "minutes",
    "goal",
    "output",
    "material",
    "theory",
    "practice",
    "schedule",
}
CURRICULUM_KEYS = {
    "id",
    "title",
    "job_groups",
    "difficulty",
    "days",
    "start_time",
    "end_time",
    "slot_min",
    "break_min",
    "goal",
    "output",
    "slots",
}
SLOT_KEYS = {"day", "slot", "title", "description"}
ADVANCED_KEYS = {"id", "title", "audience", "tool", "hours", "goal", "features"}
PERSONAL_KEYS = {"instructor_id", "owner", "owner_instructor_id", "name", "email"}


async def _instructor(session: AsyncSession, email: str) -> int:
    return await make_instructor(session, Settings(_env_file=None), email=email)


def _course(pool_id: str, owner: int | None = None, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": pool_id,
        "source": "own" if owner is not None else "ax",
        "owner_instructor_id": owner,
        "title": "시험 과정 가",
        "job_groups": ["공통(전 직원)"],
        "difficulty": "중",
        "minutes": 60,
        "goal": "목표 가",
        "theory": ["이론 하나"],
        "practice": ["실습 하나"],
        "schedule": [["00:00", "이론", "개요"]],
    }
    return {**base, **over}


def _curriculum(curriculum_id: str, instructor_id: int, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": curriculum_id,
        "instructor_id": instructor_id,
        "title": "시험 커리큘럼 가",
        "job_groups": ["사무·행정"],
        "difficulty": "하",
        "days": 2,
        "start_time": dt.time(13, 0),
        "end_time": dt.time(17, 0),
        "slot_min": 50,
        "break_min": 10,
    }
    return {**base, **over}


def _advanced(advanced_id: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": advanced_id,
        "title": "시험 심화 가",
        "audience": "실무자",
        "tool": "도구 가",
        "hours": 18,
        "features": ["특징 하나"],
    }
    return {**base, **over}


async def _check_violation(session: AsyncSession, **fields: Any) -> str:
    """insert_pool_course 의 CHECK 위반 sqlstate. flush_or_conflict 가 SAVEPOINT 를 써서 바깥 트랜잭션은 산다."""
    with pytest.raises(IntegrityError) as caught:
        await insert_pool_course(session, **fields)
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


async def _violation(session: AsyncSession, *rows: object) -> str:
    """rows 를 SAVEPOINT 안에서 넣고 위반 sqlstate 를 돌려준다. 바깥 시험 트랜잭션은 산다."""
    with pytest.raises(IntegrityError) as caught:
        async with session.begin_nested():
            session.add_all(rows)
            await session.flush()
    return caught.value.orig.sqlstate  # type: ignore[union-attr]


def _conflict_sqlstate(exc: Conflict) -> str | None:
    return getattr(getattr(exc.__cause__, "orig", None), "sqlstate", None)


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    stmt = select(func.count()).select_from(model).where(*where)
    return await session.scalar(stmt) or 0


def _keys(value: Any) -> set[str]:
    """dict·list 를 재귀로 돌며 만난 키 전부."""
    if isinstance(value, dict):
        found = set(value)
        for v in value.values():
            found |= _keys(v)
        return found
    if isinstance(value, list):
        found = set()
        for v in value:
            found |= _keys(v)
        return found
    return set()


async def _pdf_row(
    session: AsyncSession, owner_kind: str, owner_id: Any, digit: str
) -> tuple[Any, StoredFile]:
    row = await pool_file.insert_file_row(
        session, owner_kind, owner_id, kind="pdf", title="강의안"
    )
    stored = await insert_stored_file(
        session,
        sha256=digit * 64,
        owner_kind=owner_kind,
        owner_id=row.id,
        content_type="application/pdf",
        size=5,
    )
    await pool_file.set_file_id(session, row, stored.id)
    return row, stored


async def test_no_personal_keys_catalog(db_session: AsyncSession) -> None:
    email = "pool-owner@example.com"
    iid = await _instructor(db_session, email)
    own = f"own-{iid}"
    reviewed = {"reviewed": True, "reviewed_at": NOW}
    rows = [
        _course("ax-cat-1", pub=True, **reviewed),  # 공개 ∧ 활성
        _course("ax-cat-2", pub=False, **reviewed),  # 비공개
        _course("ax-cat-3", pub=True, active=False, **reviewed),  # 비활성
        _course(f"{own}-1", iid, pub=True, **reviewed),  # 고유 과정 검토·공개
        _course(f"{own}-2", iid),  # 고유 과정 미검토(pub false)
        _course(
            f"{own}-3", iid, pub=True, reviewed=False, reviewed_at=NOW
        ),  # 검토 뒤 수정
    ]
    for fields in rows:
        await insert_pool_course(db_session, **fields)
    await insert_curriculum(db_session, **_curriculum(f"cur-{iid}-1", iid, pub=True))
    await insert_curriculum(db_session, **_curriculum(f"cur-{iid}-2", iid))
    await replace_slots(
        db_session,
        f"cur-{iid}-1",
        [
            {"day": 2, "slot": 1, "title": "차시 나"},
            {"day": 1, "slot": 2, "title": "차시 가", "description": "설명"},
        ],
    )
    await insert_advanced(db_session, **_advanced("adv-cat-1", pub=True))
    await insert_advanced(db_session, **_advanced("adv-cat-2", pub=True, active=False))

    catalog = await published_catalog(db_session)

    assert [c.id for c in catalog.courses] == ["ax-cat-1", f"{own}-1", f"{own}-3"]
    assert [c.id for c in catalog.curricula] == [f"cur-{iid}-1"]
    assert [(s.day, s.slot) for s in catalog.curricula[0].slots] == [(1, 2), (2, 1)]
    assert [a.id for a in catalog.advanced] == ["adv-cat-1"]
    assert {c.source for c in catalog.courses} == {"ax", "own"}

    body = dataclasses.asdict(catalog)
    assert set(body) == {"courses", "curricula", "advanced"}
    assert all(set(c) == COURSE_KEYS for c in body["courses"])
    assert all(set(c) == CURRICULUM_KEYS for c in body["curricula"])
    assert all(set(s) == SLOT_KEYS for c in body["curricula"] for s in c["slots"])
    assert all(set(a) == ADVANCED_KEYS for a in body["advanced"])
    every = _keys(body)
    assert every == {"courses", "curricula", "advanced"} | COURSE_KEYS | (
        CURRICULUM_KEYS | SLOT_KEYS | ADVANCED_KEYS
    )
    assert every & PERSONAL_KEYS == set()
    text = json.dumps(body, ensure_ascii=False, default=str)
    assert email not in text and "강사" not in text  # make_instructor 의 이름·이메일


async def test_pool_course_check_source_owner_and_difficulty(
    db_session: AsyncSession,
) -> None:
    iid = await _instructor(db_session, "pool-check@example.com")

    own_without_owner = _course("own-x-1", source="own", owner_instructor_id=None)
    ax_with_owner = _course("ax-x-1", source="ax", owner_instructor_id=iid)
    bad_difficulty = _course("ax-x-2", difficulty="최상")
    for fields in (own_without_owner, ax_with_owner, bad_difficulty):
        assert await _check_violation(db_session, **fields) == CHECK_VIOLATION

    ax = await insert_pool_course(db_session, **_course("ax-x-3"))
    own = await insert_pool_course(db_session, **_course(f"own-{iid}-1", iid))
    assert (ax.source, ax.owner_instructor_id) == ("ax", None)
    assert (own.source, own.owner_instructor_id) == ("own", iid)
    # 서버 기본값: 활성 · 비공개 · 미검토
    assert (ax.active, ax.pub, ax.reviewed, ax.reviewed_at) == (
        True,
        False,
        False,
        None,
    )


async def test_pool_course_job_groups_nonempty_check(db_session: AsyncSession) -> None:
    no_jobs = _course("ax-j-1", job_groups=[])
    assert await _check_violation(db_session, **no_jobs) == CHECK_VIOLATION
    ok = await insert_pool_course(
        db_session, **_course("ax-j-2", job_groups=["사무·행정", "기획·전략"])
    )
    assert ok.job_groups == ["사무·행정", "기획·전략"]


async def test_pool_capability_unique(db_session: AsyncSession) -> None:
    iid = await _instructor(db_session, "pool-cap@example.com")
    await insert_pool_course(db_session, **_course("ax-c-1"))

    first, created = await get_or_create_capability(db_session, iid, "ax-c-1")
    again, created_again = await get_or_create_capability(db_session, iid, "ax-c-1")
    assert (created, created_again) == (True, False)
    assert first.id == again.id

    dup = Capability(instructor_id=iid, pool_course_id="ax-c-1")
    assert await _violation(db_session, dup) == UNIQUE_VIOLATION
    assert await _count(db_session, Capability) == 1


async def test_pool_curriculum_slot_unique_and_cascade(
    db_session: AsyncSession,
) -> None:
    iid = await _instructor(db_session, "pool-cur@example.com")
    cid = f"cur-{iid}-1"
    await insert_curriculum(db_session, **_curriculum(cid, iid))

    with pytest.raises(Conflict) as caught:
        await replace_slots(
            db_session,
            cid,
            [
                {"day": 1, "slot": 1, "title": "차시 가"},
                {"day": 1, "slot": 1, "title": "차시 나"},
            ],
        )
    assert _conflict_sqlstate(caught.value) == UNIQUE_VIOLATION

    assert (
        await replace_slots(
            db_session,
            cid,
            [
                {"day": 1, "slot": 1, "title": "차시 가"},
                {"day": 2, "slot": 3, "title": "차시 나"},
            ],
        )
        == 2
    )
    assert await _count(db_session, CurriculumSlot) == 2
    # 다시 바꾸면 통째 교체다
    assert (
        await replace_slots(db_session, cid, [{"day": 2, "slot": 1, "title": "다"}])
        == 1
    )
    assert await _count(db_session, CurriculumSlot) == 1

    await db_session.execute(delete(Curriculum).where(Curriculum.id == cid))
    assert await _count(db_session, CurriculumSlot) == 0


async def test_pool_file_rows_file_id_unique(db_session: AsyncSession) -> None:
    iid = await _instructor(db_session, "pool-file@example.com")
    own = await insert_pool_course(db_session, **_course(f"own-{iid}-1", iid))
    cap, _ = await get_or_create_capability(db_session, iid, own.id)
    cur = await insert_curriculum(db_session, **_curriculum(f"cur-{iid}-1", iid))

    owners = {
        "pool_course_file": own.id,
        "capability_file": cap.id,
        "curriculum_file": cur.id,
    }
    for digit, (kind, owner_id) in zip("abc", owners.items(), strict=True):
        first, stored = await _pdf_row(db_session, kind, owner_id, digit)
        second = await pool_file.insert_file_row(
            db_session, kind, owner_id, kind="pdf", title="둘째"
        )
        assert (first.sort, second.sort) == (0, 1)
        model = pool_file.file_model(kind)
        with pytest.raises(IntegrityError) as caught:
            async with db_session.begin_nested():
                await db_session.execute(
                    model.__table__.update()
                    .where(model.id == second.id)
                    .values(file_id=stored.id)
                )
        assert caught.value.orig.sqlstate == UNIQUE_VIOLATION, kind  # type: ignore[union-attr]
        # link 는 url 이 있어야 하고 file_id 가 없어야 한다(대상 CHECK)
        bad_link = model(**{model.owner_fk: owner_id}, kind="link", title="링크")
        assert await _violation(db_session, bad_link) == CHECK_VIOLATION, kind


async def test_pool_capability_delete_removes_file_rows_same_tx(
    db_session: AsyncSession,
) -> None:
    iid = await _instructor(db_session, "pool-del@example.com")
    await insert_pool_course(db_session, **_course("ax-d-1"))
    cap, _ = await get_or_create_capability(db_session, iid, "ax-d-1")
    await _pdf_row(db_session, "capability_file", cap.id, "d")
    await pool_file.insert_file_row(
        db_session,
        "capability_file",
        cap.id,
        kind="link",
        title="참고",
        url="https://example.com/a",
    )
    cap_id = cap.id
    kind_files = StoredFile.owner_kind == "capability_file"
    assert await _count(db_session, CapabilityFile) == 2
    assert await _count(db_session, StoredFile, kind_files) == 1

    nested = await db_session.begin_nested()
    assert await delete_capability(db_session, cap) == 2
    assert await _count(db_session, CapabilityFile) == 0
    assert await _count(db_session, StoredFile, kind_files) == 0
    assert await _count(db_session, Capability) == 0
    await nested.rollback()

    # 같은 트랜잭션이라 되돌리면 셋 다 남는다
    assert (
        await _count(db_session, CapabilityFile, CapabilityFile.capability_id == cap_id)
        == 2
    )
    assert await _count(db_session, StoredFile, kind_files) == 1
    assert await _count(db_session, Capability) == 1
