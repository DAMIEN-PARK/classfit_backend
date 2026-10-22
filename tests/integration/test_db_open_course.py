"""강의 개설·초대코드(Design 5절 13·부록 A T2a): 단일 진입점, 전 행 유일, 강의당 산 코드 1개, 재발급, 충돌 재시도. 라이브 PG.

단일 진입 시험은 src 에서 부르는 곳을 센다. def·class 정의 줄은 빼고 센다.
"""

import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict
from classfit.crud.invite_code import update_code
from classfit.models import InviteCode
from classfit.service.courses import codes
from classfit.service.courses.codes import reissue_invite_code
from tests.fixtures.courses import open_test_course

SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"
UNIQUE_VIOLATION = "23505"
_DEFINITION = re.compile(r"^\s*(async\s+def|def|class)\s")


def _callers(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    found = []
    for path in sorted(SRC.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if any(rx.search(line) for line in lines if not _DEFINITION.match(line)):
            found.append(path.relative_to(SRC).as_posix())
    return found


def test_courses_open_single_entry() -> None:
    assert _callers(r"\binsert_course\(") == ["service/courses/open.py"]
    assert _callers(r"\bCourse\(") == ["crud/course.py"]


def test_invite_code_generated_only_in_issue_invite_code() -> None:
    assert _callers(r"\b_new_invite_code\(") == ["service/courses/codes.py"]
    assert _callers(r"\bInviteCode\(") == ["service/courses/codes.py"]


async def _live_count(session: AsyncSession, course_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(InviteCode)
        .where(InviteCode.course_id == course_id, InviteCode.status != "replaced")
    )
    return await session.scalar(stmt) or 0


async def test_invite_code_unique_across_all_rows(db_session: AsyncSession) -> None:
    a, old = await open_test_course(db_session)
    old_code = old.code
    await reissue_invite_code(db_session, a.id)  # old 는 replaced
    b, _ = await open_test_course(db_session, title="B 강의")
    # replaced 행의 코드도 다시 못 쓴다(부분 색인 밖인 replaced 로 넣어도 code 유일에 걸린다)
    db_session.add(
        InviteCode(
            course_id=b.id,
            code=old_code,
            status="replaced",
            expires_on=date(2026, 12, 31),
        )
    )
    with pytest.raises(IntegrityError) as caught:
        await db_session.flush()
    assert caught.value.orig.sqlstate == UNIQUE_VIOLATION  # type: ignore[union-attr]


async def test_invite_code_one_live_per_course(db_session: AsyncSession) -> None:
    course, _ = await open_test_course(db_session)
    expires = date(2026, 12, 31)
    with pytest.raises(IntegrityError) as caught:
        async with db_session.begin_nested():
            # "1" 은 알파벳 밖이라 만든 코드와 겹치지 않는다. 걸리는 것은 부분 유일 색인이다
            db_session.add(
                InviteCode(
                    course_id=course.id,
                    code="Z1Z1Z1",
                    status="paused",
                    expires_on=expires,
                )
            )
            await db_session.flush()
    assert caught.value.orig.sqlstate == UNIQUE_VIOLATION  # type: ignore[union-attr]
    # 대조: replaced 행은 색인 밖이라 들어간다
    db_session.add(
        InviteCode(
            course_id=course.id, code="Y1Y1Y1", status="replaced", expires_on=expires
        )
    )
    await db_session.flush()
    assert await _live_count(db_session, course.id) == 1


async def test_invite_code_reissue_marks_old_replaced(db_session: AsyncSession) -> None:
    course, old = await open_test_course(db_session)
    await update_code(db_session, old, max_seats=30)
    old_id, old_code, old_expires = old.id, old.code, old.expires_on

    new = await reissue_invite_code(db_session, course.id)

    stmt = (
        select(
            InviteCode.id,
            InviteCode.code,
            InviteCode.status,
            InviteCode.expires_on,
            InviteCode.max_seats,
        )
        .where(InviteCode.course_id == course.id)
        .order_by(InviteCode.id)
    )
    rows = (await db_session.execute(stmt)).all()
    assert [(r.id, r.status) for r in rows] == [
        (old_id, "replaced"),
        (new.id, "active"),
    ]
    assert rows[1].code != old_code
    assert (rows[1].expires_on, rows[1].max_seats) == (
        old_expires,
        30,
    )  # 만료일·정원을 옮긴다
    assert await _live_count(db_session, course.id) == 1


async def test_invite_code_issue_when_live_exists_409_no_retry(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """산 코드가 있는 강의에 또 발급하면 부분 유일 색인에 걸린다. 새 코드로도 안 풀리니 다시 넣지 않고 409."""
    course, live = await open_test_course(db_session)
    real = codes._new_invite_code
    calls: list[str] = []

    def counted() -> str:
        calls.append(real())
        return calls[-1]

    monkeypatch.setattr("classfit.service.courses.codes._new_invite_code", counted)
    with pytest.raises(Conflict, match="산 초대코드가 이미 있습니다"):
        await codes.issue_invite_code(
            db_session, course_id=course.id, expires_on=live.expires_on
        )
    assert len(calls) == 1  # INSERT 1회, 재시도 없음
    assert await _live_count(db_session, course.id) == 1


async def test_invite_code_retry_on_collision(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, taken_row = await open_test_course(db_session)
    other, _ = await open_test_course(db_session, title="B 강의")
    taken = taken_row.code
    real = codes._new_invite_code
    calls: list[str] = []

    def collide_twice() -> str:
        code = taken if len(calls) < 2 else real()
        calls.append(code)
        return code

    monkeypatch.setattr(
        "classfit.service.courses.codes._new_invite_code", collide_twice
    )
    new = await reissue_invite_code(db_session, other.id)
    assert calls[:2] == [taken, taken] and len(calls) == 3
    assert new.code == calls[2] != taken and new.status == "active"

    def always_taken() -> str:
        calls.append(taken)
        return taken

    calls.clear()
    monkeypatch.setattr("classfit.service.courses.codes._new_invite_code", always_taken)
    with pytest.raises(Conflict):
        await reissue_invite_code(db_session, other.id)
    assert len(calls) == codes.MAX_TRIES == 5
