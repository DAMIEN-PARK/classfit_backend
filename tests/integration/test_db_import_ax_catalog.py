"""관리 명령 import_ax_catalog(T4 결정 ii·iii·iv): 시안 모양 거절 · 부분 신규 · 미리 보기 · 두 번 같음 · 변경은 보고만 ·
관리자 플래그 유지 · 인자 틀림 2 · 심화만. 라이브 PG, 시험 연결에 묶은 session_factory 를 넘긴다(test_db_admin_commands 꼴).

입력 표본은 tests/fixtures/ax_catalog_sample.json(과정 4 · 심화 2, 가명). 바꾼 입력은 tmp_path 에 쓴다.
행 비교는 ORM 이 아니라 표를 직접 읽는다(identity map 의 옛 값을 보지 않게).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from classfit.crud.pool import get_pool_course_any, set_flags
from classfit.database.session import make_session_factory
from classfit.models import AdvancedCourse, AuditLog, PoolCourse
from scripts import import_ax_catalog

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "ax_catalog_sample.json"
COURSE_IDS = ["ax-common-1", "ax-common-2", "ax-test-1", "ax-test-2"]
ADVANCED_IDS = ["adv-1", "adv-2"]


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


def _sample() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return data


def _write(tmp_path: Path, data: Any, name: str = "catalog.json") -> str:
    path = tmp_path / name
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return str(path)


async def _run(
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
    *argv: str,
) -> tuple[int, Any, str]:
    """(종료 코드, stdout JSON 또는 None, stderr)."""
    code = await import_ax_catalog.run(list(argv), factory)
    captured = capsys.readouterr()
    out = json.loads(captured.out) if captured.out.strip() else None
    return code, out, captured.err


async def _count(session: AsyncSession, model: type, *where: object) -> int:
    stmt = select(func.count()).select_from(model).where(*where)
    return await session.scalar(stmt) or 0


async def _snapshot(session: AsyncSession, model: type) -> list[dict[str, Any]]:
    """표의 전 칸(updated_at 포함), id 순."""
    table = model.__table__  # type: ignore[attr-defined]
    rows = await session.execute(select(table).order_by(table.c.id))
    return [dict(r._mapping) for r in rows]


def _imports() -> Any:
    return AuditLog.action == "pool_course.import"


async def test_import_ax_catalog_mockup_shape_rejected_2(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    # 시안 강사.html:516 AX_CATALOG 모양: id 없이 dept·deptName
    mockup = {
        "courses": [
            {
                "dept": "office",
                "deptName": "사무행정부서",
                "title": "시안제목-누설금지",
                "goal": "시안목표-누설금지",
                "difficulty": "중",
                "output": "시안산출물",
            }
        ]
    }
    code, out, err = await _run(factory, capsys, _write(tmp_path, mockup), "--apply")

    assert (code, out) == (2, None)
    assert "courses.0.id: Field required" in err
    assert "courses.0.dept: Extra inputs are not permitted" in err
    assert "courses.0.deptName: Extra inputs are not permitted" in err
    for value in ("시안제목-누설금지", "시안목표-누설금지", "사무행정부서", "office"):
        assert value not in err
    assert await _count(db_session, PoolCourse) == 0


async def test_import_ax_catalog_partial_new_inserts_only_missing(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert (await _run(factory, capsys, str(SAMPLE), "--apply"))[0] == 0
    before = await _snapshot(db_session, PoolCourse)

    data = _sample()
    extra = copy.deepcopy(data["courses"][:2])
    extra[0]["id"], extra[1]["id"] = "ax-new-1", "ax-new-2"
    data["courses"] += extra
    code, out, _ = await _run(factory, capsys, _write(tmp_path, data), "--apply")

    assert code == 0
    assert out["courses"] == {
        "inserted": ["ax-new-1", "ax-new-2"],
        "unchanged": COURSE_IDS,
        "differs": [],
    }
    after = await _snapshot(db_session, PoolCourse)
    assert [
        r for r in after if r["id"] in COURSE_IDS
    ] == before  # 기존 4행 전 칸 그대로
    assert len(after) == 6
    assert await _count(db_session, AuditLog, _imports()) == 2


async def test_import_ax_catalog_preview_writes_nothing(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = await _run(factory, capsys, str(SAMPLE))

    assert code == 0
    assert out["applied"] is False
    assert out["courses"]["inserted"] == COURSE_IDS
    assert out["advanced"]["inserted"] == ADVANCED_IDS
    assert "미리 보기" in err
    assert await _count(db_session, PoolCourse) == 0
    assert await _count(db_session, AdvancedCourse) == 0
    assert await _count(db_session, AuditLog) == 0


async def test_import_ax_catalog_apply_then_again_same(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, first, _ = await _run(factory, capsys, str(SAMPLE), "--apply")
    assert code == 0 and first["applied"] is True
    assert first["courses"]["inserted"] == COURSE_IDS
    assert first["advanced"]["inserted"] == ADVANCED_IDS
    audit = (await db_session.scalars(select(AuditLog).where(_imports()))).one()
    assert (audit.actor, audit.target_type, audit.target_id) == (
        "system",
        "pool_course",
        None,
    )
    assert audit.detail == {
        "inserted": 4,
        "unchanged": 0,
        "differs": 0,
        "advanced_inserted": 2,
        "advanced_unchanged": 0,
        "advanced_differs": 0,
    }
    courses = await _snapshot(db_session, PoolCourse)
    advanced = await _snapshot(db_session, AdvancedCourse)
    for row in courses:
        assert (row["source"], row["owner_instructor_id"]) == ("ax", None)
        assert (row["reviewed"], row["pub"], row["active"]) == (True, True, True)
        assert row["reviewed_at"] is not None
    assert all((r["pub"], r["active"]) == (True, True) for r in advanced)

    code, second, _ = await _run(factory, capsys, str(SAMPLE), "--apply")

    assert code == 0
    assert second["courses"] == {"inserted": [], "unchanged": COURSE_IDS, "differs": []}
    assert second["advanced"] == {
        "inserted": [],
        "unchanged": ADVANCED_IDS,
        "differs": [],
    }
    assert await _count(db_session, AuditLog, _imports()) == 1
    assert await _snapshot(db_session, PoolCourse) == courses
    assert await _snapshot(db_session, AdvancedCourse) == advanced


async def test_import_ax_catalog_differs_reported_not_updated(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert (await _run(factory, capsys, str(SAMPLE), "--apply"))[0] == 0
    before = await _snapshot(db_session, PoolCourse)
    data = _sample()
    data["courses"][0]["title"] = "시험 과정 가 (고친 판)"

    code, out, _ = await _run(factory, capsys, _write(tmp_path, data), "--apply")

    assert code == 0
    assert out["courses"] == {
        "inserted": [],
        "unchanged": COURSE_IDS[1:],
        "differs": ["ax-common-1"],
    }
    assert await _snapshot(db_session, PoolCourse) == before
    assert await _count(db_session, AuditLog, _imports()) == 1


async def test_import_ax_catalog_keeps_admin_flags(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (await _run(factory, capsys, str(SAMPLE), "--apply"))[0] == 0
    row = await get_pool_course_any(db_session, "ax-common-1")
    assert row is not None
    await set_flags(db_session, row, pub=False, active=False)

    assert (await _run(factory, capsys, str(SAMPLE), "--apply"))[0] == 0

    flags = await db_session.execute(
        select(PoolCourse.__table__.c.pub, PoolCourse.__table__.c.active).where(
            PoolCourse.__table__.c.id == "ax-common-1"
        )
    )
    assert flags.one() == (False, False)


async def test_import_ax_catalog_bad_input_2(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    secret = "비밀제목-되찍지않음"

    def course(**over: Any) -> dict[str, Any]:
        base = copy.deepcopy(_sample()["courses"][0])
        base["title"] = secret
        return {"courses": [{**base, **over}]}

    long_id = "ax-" + "a" * 78  # 81자, 모양은 맞다(API 의 글자 id 상한 80)
    long_goal = "목" * 2001  # API 의 긴 글 상한 2000
    duplicate = course()
    duplicate["courses"].append(dict(duplicate["courses"][0]))
    cases: dict[str, tuple[str, list[str]]] = {
        "없는 경로": (str(tmp_path / "missing.json"), []),
        "JSON 아님": (_write(tmp_path, f"{{courses: [{secret}", "a.json"), [secret]),
        "id 모양": (_write(tmp_path, course(id="AX-1"), "b.json"), ["AX-1"]),
        "예약 접두": (
            _write(tmp_path, course(id="ax-custom-1"), "c.json"),
            ["ax-custom-1"],
        ),
        "직무군 밖": (
            _write(tmp_path, course(job_groups=["없는직무군"]), "d.json"),
            ["없는직무군"],
        ),
        "파일 안 중복 id": (_write(tmp_path, duplicate, "e.json"), []),
        "둘 다 빈 목록": (
            _write(tmp_path, {"courses": [], "advanced": []}, "f.json"),
            [],
        ),
        "id 81자": (_write(tmp_path, course(id=long_id), "g.json"), [long_id]),
        "goal 2001자": (
            _write(tmp_path, course(goal=long_goal), "h.json"),
            [long_goal],
        ),
    }
    for label, (path, hidden) in cases.items():
        code, out, err = await _run(factory, capsys, path, "--apply")
        assert (code, out) == (2, None), label
        assert err.startswith("인자 틀림"), (label, err)
        for value in (secret, *hidden):
            assert value not in err, (label, err)
    assert await _count(db_session, PoolCourse) == 0
    assert await _count(db_session, AdvancedCourse) == 0
    assert await _count(db_session, AuditLog) == 0


async def test_import_ax_catalog_advanced_only_file(
    factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, {"advanced": _sample()["advanced"]})

    code, out, _ = await _run(factory, capsys, path, "--apply")
    assert code == 0
    assert out["courses"] == {"inserted": [], "unchanged": [], "differs": []}
    assert out["advanced"]["inserted"] == ADVANCED_IDS
    assert await _count(db_session, AdvancedCourse) == 2
    assert await _count(db_session, PoolCourse) == 0

    code, out, _ = await _run(factory, capsys, path, "--apply")
    assert code == 0
    assert out["advanced"] == {"inserted": [], "unchanged": ADVANCED_IDS, "differs": []}
    assert await _count(db_session, AuditLog, _imports()) == 1
