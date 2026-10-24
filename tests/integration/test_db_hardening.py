"""0012(T11 결정 xii): survey.template_id 색인 · 이름·제목 CHECK 여섯의 공백류 꼴 · 모델과 마이그레이션의 식 글자 ·
데이터 있는 0011 → 0012 의 행 가드와 왕복. 라이브 PG.

alembic check 는 CHECK 글자를 비교하지 않으므로(env.py 가 CHECK 비교를 켜지 않는다) 식은 여기서 잰다. NBSP 같은 비ASCII
공백이 [:space:] 인지는 DB ctype 에 따르므로 ASCII 공백류(스페이스·탭·LF·CR·VT·FF)만 단언한다.
마이그레이션 시험은 세션 시험 DB 에서 alembic CLI 를 자식 프로세스로 돌린다(conftest 꼴). db_session·db_connection 을 쓰지
않고 자기 연결로 행을 커밋하며, CLI 를 부르기 전마다 그 연결을 닫는다(NullPool). 끝에는 무조건 커밋한 행을 지우고 → 연결을
닫고 → upgrade head 가 성공해 0012 (head) 인지 본다 — 어기는 행이 남은 채 upgrade head 를 부르면 같은 가드가 복구를 막는다.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import CheckConstraint, func, insert, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from classfit.database.session import make_engine
from classfit.models import Base, Learner
from tests.fixtures.courses import open_test_course

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "alembic" / "versions"
CHECK_VIOLATION = "23514"
# ASCII 공백류만 있는 값 — 옛 식(btrim 은 스페이스만 지운다)은 스페이스뿐인 값 말고는 다 받았다
BLANKS = (" ", "\t", "\n", "\r", "\x0b", "\x0c", " \t\n\r\x0b\x0c ")
MAX_LENGTH = {"name": 50, "title": 200}  # 옛 식과 같은 n
INSERT_INSTRUCTOR = (
    "INSERT INTO instructor (email, password_hash, name, phone, terms_version,"
    " terms_agreed_at) VALUES (:email, 'unused', :name, '010-0000-0000', 'v1', now())"
    " RETURNING id"
)


def _migration(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{name}", VERSIONS / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(table: str, column: str) -> CheckConstraint:
    found = [
        c
        for c in Base.metadata.tables[table].constraints
        if isinstance(c, CheckConstraint) and c.name == f"ck_{table}_{column}"
    ]
    assert len(found) == 1, (table, column)
    return found[0]


async def _violates(db: AsyncSession, stmt: Any, constraint: str) -> None:
    """SAVEPOINT 안에서 stmt 가 CHECK 위반(그 제약 이름)으로 실패하는지."""
    tx = await db.begin_nested()
    with pytest.raises(IntegrityError) as caught:
        await db.execute(stmt)
    await tx.rollback()
    assert caught.value.orig.sqlstate == CHECK_VIOLATION, caught.value
    assert caught.value.orig.diag.constraint_name == constraint, caught.value


async def _accepts(db: AsyncSession, stmt: Any) -> None:
    """SAVEPOINT 안에서 stmt 가 들어가는지 — 되돌려 유일 칸이 다음 넣기와 겹치지 않게 한다."""
    tx = await db.begin_nested()
    await db.execute(stmt)
    await tx.rollback()


async def test_survey_template_id_index(db_session: AsyncSession) -> None:
    rows = await db_session.scalars(
        text(
            "SELECT indexdef FROM pg_indexes"
            " WHERE tablename = 'survey' AND indexname = 'ix_survey_template_id'"
        )
    )
    (indexdef,) = rows.all()
    assert indexdef.endswith("(template_id)"), indexdef


async def _bases(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """표마다 검사 칸을 뺀 정상 행. 부모 행(강의·수강생·강사·커리큘럼)은 시험 트랜잭션 안에 만든다."""
    course, _ = await open_test_course(db)
    learner = Learner(email="hardening-learner@example.com")
    db.add(learner)
    await db.flush()
    instructor_id = await db.scalar(
        text(INSERT_INSTRUCTOR),
        {"email": "hardening-parent@example.com", "name": "강사"},
    )
    curriculum: dict[str, Any] = {
        "instructor_id": instructor_id,
        "job_groups": ["공통(전 직원)"],
        "difficulty": "중",
        "days": 1,
        "start_time": dt.time(13),
        "end_time": dt.time(17),
        "slot_min": 50,
        "break_min": 10,
    }
    parent = Base.metadata.tables["curriculum"]
    await db.execute(
        insert(parent).values(id="cur-hardening-1", title="부모", **curriculum)
    )
    return {
        "enrollment": {"course_id": course.id, "learner_id": learner.id},
        "instructor": {
            "email": "hardening-check@example.com",
            "password_hash": "unused",
            "phone": "010-0000-0000",
            "terms_version": "v1",
            "terms_agreed_at": func.now(),
        },
        "pool_course": {
            "id": "ax-hardening",
            "source": "ax",
            "job_groups": ["공통(전 직원)"],
            "difficulty": "중",
            "minutes": 60,
        },
        "curriculum": {"id": "cur-hardening-2", **curriculum},
        "curriculum_slot": {"curriculum_id": "cur-hardening-1", "day": 1, "slot": 1},
        "advanced_course": {
            "id": "adv-hardening",
            "audience": "전 직원",
            "tool": "도구",
            "hours": 1,
        },
    }


async def test_blank_check_whitespace_only_rejected(db_session: AsyncSession) -> None:
    db = db_session
    bases = await _bases(db)
    checks = _migration("0012_hardening.py").CHECKS
    assert [table for table, *_ in checks] == list(bases)
    for table, column, *_ in checks:
        n = MAX_LENGTH[column]
        constraint = f"ck_{table}_{column}"
        row = insert(Base.metadata.tables[table]).values(**bases[table])
        for blank in BLANKS:
            await _violates(db, row.values({column: blank}), constraint)
        # 길이는 앞뒤 스페이스를 뺀 글자 수 — n 은 들어가고 n+1 은 위반
        await _accepts(db, row.values({column: "가" * n}))
        await _accepts(db, row.values({column: " " + "가" * n + " "}))
        await _violates(db, row.values({column: "가" * (n + 1)}), constraint)


def test_blank_check_model_matches_migration() -> None:
    m0012 = _migration("0012_hardening.py")
    assert len(m0012.CHECKS) == 6
    assert len({(table, column) for table, column, *_ in m0012.CHECKS}) == 6
    for table, column, new, old in m0012.CHECKS:
        assert str(_check(table, column).sqltext) == new, (table, column)
        assert new != old
    # downgrade 가 되돌리는 식 = 처음 만든 식(0004·0005 의 name · 0006 TITLE_CHECK)
    assert m0012.OLD_TITLE_CHECK == _migration("0006_course_pool.py").TITLE_CHECK
    for name in ("0004_enter_portal.py", "0005_instructor_onboarding.py"):
        assert f'"{m0012.OLD_NAME_CHECK}"' in (VERSIONS / name).read_text("utf-8")


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLASSFIT_DATABASE_URL": url, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        check=False,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _current(url: str) -> str:
    done = _alembic(url, "current")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


async def _commit(url: str, sql: str, **params: Any) -> list[Any]:
    """자기 연결 하나로 sql 을 커밋하고 연결을 닫는다(NullPool + dispose). 돌려받은 첫 칸 목록."""
    engine = make_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params)
            return list(result.scalars()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def test_migration_0012_guard_and_roundtrip(migrated_db_url: str) -> None:
    url = migrated_db_url
    ids: list[int] = []
    try:
        done = _alembic(url, "downgrade", "0011")
        assert done.returncode == 0, done.stderr
        # 옛 식(btrim 은 스페이스만 지운다)은 탭만 있는 이름을 받는다
        ids += await _commit(
            url, INSERT_INSTRUCTOR, email="hardening-bad@example.com", name="\t"
        )
        ids += await _commit(
            url, INSERT_INSTRUCTOR, email="hardening-good@example.com", name="정상 강사"
        )
        bad, good = ids

        # ⓐ 행 가드: 멈추고 그 수를 알린다 — 한 트랜잭션이라 0011 그대로
        done = _alembic(url, "upgrade", "0012")
        assert done.returncode != 0
        assert "0012 중단 - instructor.name 이 공백류만 있는 행 1 개" in done.stderr
        assert _current(url) == "0011"

        # ⓑ 그 행을 지우면 올라가고, 내렸다 다시 올려도 정상 행은 남는다
        await _commit(url, "DELETE FROM instructor WHERE id = :id", id=bad)
        for step in (("upgrade", "0012"), ("downgrade", "0011"), ("upgrade", "head")):
            done = _alembic(url, *step)
            assert done.returncode == 0, (step, done.stderr)
        sql = "SELECT name FROM instructor WHERE id = :id"
        assert await _commit(url, sql, id=good) == ["정상 강사"]
    finally:
        # 순서가 정해져 있다: 커밋한 행 지우기 → 연결 닫기(_commit 이 닫는다) → upgrade head 성공 단언
        if ids:
            await _commit(url, "DELETE FROM instructor WHERE id = ANY(:ids)", ids=ids)
        done = _alembic(url, "upgrade", "head")
        assert done.returncode == 0, done.stderr
        assert _current(url) == "0012 (head)"
