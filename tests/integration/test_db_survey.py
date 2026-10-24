"""만족도 설문 표·crud·service(T8 결정 iii·iv·v·xi·xii·xvii·xix): 기본 양식 시드 · 표 제약 · 상태 SQL 판 · 잠금 SQL 글자 ·
알림 미리 보기 · 강의 삭제 · 결과 읽기 문장 수 · 잠금 호출 자리. 라이브 PG.

alembic check 는 CHECK·시드를 비교하지 않으므로 여기서 잰다. 행은 표에 직접 넣거나 crud·service 로 만든다(HTTP 없음). 강의는
단일 진입점 open_test_course, 등록은 crud(get_or_create_learner · insert_enrollment), 배포는 운영 경로 deploy_to 로 만든다.
행 id·시퀀스 번호는 단언하지 않는다. 잠금 호출 자리 시험은 src 를 ast 로 읽는다(T7 tests/integration/test_db_record.py 의
_Call·_function·_calls 를 복사했다). 잠금이 실제로 줄 세우는지는 tests/integration/test_db_survey_race.py 가 잰다.
"""

from __future__ import annotations

import ast
import datetime as dt
import importlib
import inspect
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import delete, event, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from classfit.core.config import Settings
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import flush as crud_flush
from classfit.crud import outbox as crud_outbox
from classfit.crud import survey as crud_survey
from classfit.crud import survey_response as crud_survey_response
from classfit.crud import survey_template as crud_survey_template
from classfit.crud.learner import get_or_create_learner
from classfit.database.session import make_session_factory
from classfit.models import (
    AuditLog,
    Course,
    Enrollment,
    MailOutbox,
    Survey,
    SurveyResponse,
    SurveyTemplate,
)
from classfit.service.auth.sessions import Principal
from classfit.service.courses import remove
from classfit.service.rules.survey import DatesRejected, status_at
from classfit.service.surveys import close, results
from scripts import outbox_preview
from tests.fixtures.courses import open_test_course
from tests.fixtures.instructors import count
from tests.fixtures.records import Assigned, assigned
from tests.fixtures.surveys import TODAY_RUNNING, deploy_to

DAY = dt.timedelta(days=1)
TODAY = TODAY_RUNNING
ADMIN = "admin:1"
SRC = Path(__file__).resolve().parents[2] / "src" / "classfit"
# survey·survey_response 표를 읽는 문장(표 이름이 낱말로 나온다). 결과 읽기는 둘을 한 문장으로 읽어야 한다 — 설문을 따로
# 읽든(current_for_course → survey_with_answers) 답을 따로 읽든(설문 SELECT → 응답 SELECT) 둘째 문장이 센다
SURVEY_SQL = re.compile(r"\bsurvey(?:_response)?\b")
CLOSED_AT = dt.datetime(2026, 11, 3, 9, tzinfo=dt.UTC)
QUESTION_KEYS = {
    "key",
    "type",
    "text",
    "area",
    "required",
    "star",
    "is_overall",
    "options",
    "custom",
}
ONE_SCALE = [
    {
        "key": "q1",
        "type": "scale",
        "text": "만족한다",
        "area": None,
        "required": True,
        "star": False,
        "is_overall": True,
        "options": None,
        "custom": False,
    }
]


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


def _survey_row(course_id: int, **over: Any) -> dict[str, Any]:
    return {
        "course_id": course_id,
        "template_name": "기본 양식",
        "questions": ONE_SCALE,
        "open_on": dt.date(2026, 11, 5),
        "close_on": dt.date(2026, 11, 19),
    } | over


async def _insert_survey(db: AsyncSession, course_id: int, **over: Any) -> int:
    stmt = insert(Survey.__table__).values(**_survey_row(course_id, **over))
    return (await db.execute(stmt.returning(Survey.id))).scalar_one()


async def _enrollment(db: AsyncSession, course_id: int, email: str) -> int:
    learner = await get_or_create_learner(db, email)
    row = await crud_enrollment.insert_enrollment(
        db, course_id=course_id, learner_id=learner.id, name="김가명", dept="영업"
    )
    return row.id


async def test_survey_default_template_seed(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(SurveyTemplate))).all()
    assert len(rows) == 1
    (seed,) = rows
    assert (seed.name, seed.note, seed.is_default) == (
        "기본 양식",
        "현행 만족도 조사지 구조",
        True,
    )
    questions = seed.questions
    assert len(questions) == 24
    assert all(set(q) == QUESTION_KEYS for q in questions)
    keys = [q["key"] for q in questions]
    assert len(set(keys)) == 24
    assert keys == [
        "info",
        "dept",
        "job",
        "exp",
        "part",
        *(f"b{i:02d}" for i in range(1, 13)),
        "c1",
        "c2",
        "c3",
        "overall",
        "next_type",
        "next_when",
        "next_how",
    ]
    by_key = {q["key"]: q for q in questions}
    assert Counter(q["type"] for q in questions) == {
        "info": 1,
        "single": 6,
        "scale": 13,
        "text": 3,
        "multi": 1,
    }
    # 영역 없음은 안내 1 · 응답자 정보 4 · 주관식 3. 종합은 종합 척도 1 + 후속 수요 3
    assert Counter(q["area"] for q in questions) == {
        None: 8,
        "교육 내용": 3,
        "강사·운영": 3,
        "직무 활용": 3,
        "정보보안": 1,
        "향후 활용": 2,
        "종합": 4,
    }
    assert [q["key"] for q in questions if q["star"]] == [
        "b01",
        "b04",
        "b07",
        "b10",
        "b11",
        "overall",
    ]
    assert [q["key"] for q in questions if q["is_overall"]] == ["overall"]
    assert by_key["overall"]["type"] == "scale"
    # 응답자 정보: 부서 16 · 직무 12 + 직접 입력 · 사용 경험 4지 · 참여 형태 2지
    assert (len(by_key["dept"]["options"]), by_key["dept"]["custom"]) == (16, True)
    assert (len(by_key["job"]["options"]), by_key["job"]["custom"]) == (12, True)
    assert "직접 입력" not in by_key["dept"]["options"] + by_key["job"]["options"]
    assert [len(by_key[k]["options"]) for k in ("exp", "part")] == [4, 2]
    assert [
        len(by_key[k]["options"]) for k in ("next_type", "next_when", "next_how")
    ] == [
        4,
        4,
        3,
    ]
    assert by_key["next_type"]["type"] == "multi"
    # 필수: 응답자 정보 넷 · 척도 13 / 선택: 안내 · 주관식 셋 · 후속 수요 셋
    assert sorted(k for k, q in by_key.items() if q["required"]) == sorted(
        ["dept", "job", "exp", "part", *(f"b{i:02d}" for i in range(1, 13)), "overall"]
    )
    assert all(
        q["options"] is None for q in questions if q["type"] not in ("single", "multi")
    )
    assert all(not q["custom"] for q in questions if q["key"] not in ("dept", "job"))


async def test_survey_table_checks(db_session: AsyncSession) -> None:
    db = db_session
    course, _ = await open_test_course(db)
    templates = SurveyTemplate.__table__
    good_template = {"name": "새 양식", "questions": ONE_SCALE}
    for change, name in (
        (
            {"name": " \t\n"},
            "ck_survey_template_name",
        ),  # 공백류뿐(btrim 은 스페이스만 지운다)
        ({"name": "가" * 101}, "ck_survey_template_name_length"),
        ({"questions": {"q": 1}}, "ck_survey_template_questions"),
    ):
        await _violates(
            db, insert(templates).values(**(good_template | change)), "23514", name
        )
    await db.execute(
        insert(templates).values(name="가" * 100, questions=[])
    )  # 100자 · 빈 배열은 표가 받는다
    await _violates(
        db,
        insert(Survey.__table__).values(
            **_survey_row(course.id, close_on=dt.date(2026, 11, 4))
        ),
        "23514",
        "ck_survey_period",
    )
    await _violates(
        db,
        insert(Survey.__table__).values(**_survey_row(course.id, current=False)),
        "23514",
        "ck_survey_current_closed",
    )

    # 기본 양식은 많아야 하나(시드가 이미 기본)
    await _violates(
        db,
        insert(templates).values(good_template | {"is_default": True}),
        "23505",
        "uq_survey_template_default",
    )
    # 강의당 현재 설문 하나 — 밀려난(닫힌) 행은 같은 강의에 몇이든
    template = await crud_survey_template.insert_template(
        db, name="지울 양식", note=None, is_default=False, questions=ONE_SCALE
    )
    old = await _insert_survey(
        db, course.id, current=False, closed_at=CLOSED_AT, template_id=template.id
    )
    current = await _insert_survey(db, course.id, template_id=template.id)
    await _violates(
        db,
        insert(Survey.__table__).values(**_survey_row(course.id)),
        "23505",
        "uq_survey_course_id_current",
    )
    # 응답: 답은 객체 · (설문, 등록) 하나
    enrollment_id = await _enrollment(db, course.id, "check-a@example.com")
    responses = SurveyResponse.__table__
    await _violates(
        db,
        insert(responses).values(
            survey_id=current, enrollment_id=enrollment_id, answers=[1]
        ),
        "23514",
        "ck_survey_response_answers",
    )
    await db.execute(
        insert(responses).values(
            survey_id=current, enrollment_id=enrollment_id, answers={"q1": 5}
        )
    )
    await _violates(
        db,
        insert(responses).values(
            survey_id=current, enrollment_id=enrollment_id, answers={}
        ),
        "23505",
        "uq_survey_response_survey_id_enrollment_id",
    )
    # 응답이 있는 등록은 지울 수 없다(NO ACTION)
    await _violates(
        db,
        delete(Enrollment).where(Enrollment.id == enrollment_id),
        "23503",
        "fk_survey_response_enrollment_id_enrollment",
    )
    # 양식을 지우면 배포 설문의 template_id 는 NULL, 이름·문항 스냅샷은 남는다
    assert await crud_survey_template.delete_template(db, template.id) is True
    left = (
        await db.execute(
            select(Survey.template_id, Survey.template_name, Survey.questions)
            .where(Survey.id.in_([old, current]))
            .order_by(Survey.id)
        )
    ).all()
    assert [tuple(r) for r in left] == [(None, "기본 양식", ONE_SCALE)] * 2
    # 설문을 지우면 응답이 CASCADE
    await db.execute(delete(Survey).where(Survey.id == current))
    assert await count(db, SurveyResponse, SurveyResponse.survey_id == current) == 0
    # 강의를 지우면 설문이 CASCADE(수강생 없는 강의 — 있는 강의는 service 가 409 로 먼저 막는다)
    empty, _ = await open_test_course(db, title="빈 강의")
    gone = await _insert_survey(db, empty.id)
    assert await crud_course.delete_course(db, empty.id) is True
    assert await count(db, Survey, Survey.id == gone) == 0


async def test_survey_status_sql_matches_python(db_session: AsyncSession) -> None:
    """기간 셋 × closed_at(없음·있음) = 설문 여섯을 오늘 다섯마다 두 판으로 잰다(30 조합)."""
    db = db_session
    periods = [
        (dt.date(2026, 11, 5), dt.date(2026, 11, 19)),
        (dt.date(2026, 11, 10), dt.date(2026, 11, 10)),  # 하루
        (dt.date(2026, 10, 1), dt.date(2026, 10, 10)),  # 지난
    ]
    ids: list[int] = []
    for i, (open_on, close_on) in enumerate(periods):
        course, _ = await open_test_course(db, title=f"상태 {i}")
        # 현재 설문(날짜로만 판정) + 관리자가 닫은 옛 설문
        ids.append(
            await _insert_survey(db, course.id, open_on=open_on, close_on=close_on)
        )
        ids.append(
            await _insert_survey(
                db,
                course.id,
                open_on=open_on,
                close_on=close_on,
                closed_at=CLOSED_AT,
                current=False,
            )
        )
    todays = [
        dt.date(2026, 11, 4),  # 첫 기간 열림 전날
        dt.date(2026, 11, 5),  # 열림일 당일
        dt.date(2026, 11, 10),  # 하루 기간 당일
        dt.date(2026, 11, 19),  # 닫힘일 당일
        dt.date(2026, 11, 20),  # 닫힘 다음 날
    ]
    seen: set[str] = set()
    mismatched = []
    for today in todays:
        stmt = (
            select(
                Survey.id,
                Survey.open_on,
                Survey.close_on,
                Survey.closed_at,
                crud_survey.survey_status_sql(today),
            )
            .where(Survey.id.in_(ids))
            .order_by(Survey.id)
        )
        rows = (await db.execute(stmt)).all()
        assert len(rows) == 6
        for sid, open_on, close_on, closed_at, sql_status in rows:
            py_status = status_at(
                open_on=open_on, close_on=close_on, closed_at=closed_at, today=today
            )
            seen.add(sql_status)
            if py_status != sql_status:
                mismatched.append(
                    (sid, open_on, close_on, closed_at, today, py_status, sql_status)
                )
    assert mismatched == []
    assert seen == {"scheduled", "open", "closed"}


class _Recorder:
    """세션 대신 받아 crud 가 보낸 문장을 모은다(DB 를 치지 않는다)."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def scalar(self, stmt: Any) -> None:
        self.statements.append(stmt)

    async def scalars(self, stmt: Any) -> _Recorder:
        self.statements.append(stmt)
        return self

    def all(self) -> list[Any]:
        return []


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


async def test_survey_lock_sql_flags() -> None:
    """양식 잠금 셋과 설문 잠금 둘의 컴파일 SQL: 배포만 FOR KEY SHARE, 나머지는 FOR UPDATE(NO KEY 없음, codex 1차 #6)."""
    rec: Any = _Recorder()
    await crud_survey_template.lock_template_shared(rec, 1)
    await crud_survey_template.lock_template(rec, 1)
    await crud_survey_template.lock_templates(rec, [2, 1])
    await crud_survey.lock_survey(rec, 1)
    sqls = [_sql(s) for s in rec.statements]
    shared, single, many, survey = sqls
    assert shared.endswith("FOR KEY SHARE"), shared
    for sql in (single, many, survey):
        assert sql.endswith("FOR UPDATE"), sql
    joined = "\n".join(sqls)
    assert joined.count("FOR KEY SHARE") == 1
    assert joined.count("FOR UPDATE") == 3
    assert "NO KEY" not in joined and "FOR SHARE" not in joined
    assert "ORDER BY survey_template.id" in many

    rec = _Recorder()
    await crud_survey.lock_in_id_order(rec, course_id=1)
    await crud_survey.lock_in_id_order(rec, template_id=1)
    for stmt in rec.statements:
        sql = _sql(stmt)
        assert "ORDER BY survey.id" in sql and sql.endswith("FOR UPDATE"), sql
    with pytest.raises(ValueError, match="하나만"):
        await crud_survey.lock_in_id_order(rec, course_id=1, template_id=1)
    with pytest.raises(ValueError, match="하나만"):
        await crud_survey.lock_in_id_order(rec)


async def _course_with_people(db: AsyncSession, *, learners: int, tag: str) -> Assigned:
    """배정 강사 X 가 있는 강의(tests/fixtures/records.assigned)와 등록 learners 개(이메일 <tag>-<i>@example.com)."""
    x = await assigned(db, Settings(_env_file=None), email=f"{tag}-x@example.com")
    for i in range(learners):
        await _enrollment(db, x.course_id, f"{tag}-{i}@example.com")
    return x


async def test_survey_outbox_preview_kinds(
    db_connection: AsyncConnection,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """배포 → survey_opened 수강생 2 + 강사 1 · 닫기 → survey_closed 강사 1. 미리 보기는 params 만으로 본문을 만들고(설문·강의를
    지워도 같다) 롤백한다. params 칸이 빠지면 3."""
    db = db_session
    x = await _course_with_people(db, learners=2, tag="notice")
    (row,) = await deploy_to(db, [x.course_id])
    opened = (
        await db.execute(
            select(MailOutbox.to, MailOutbox.params)
            .where(MailOutbox.kind == "survey_opened")
            .order_by(MailOutbox.id)
        )
    ).all()
    params = {
        "survey_id": row.id,
        "course_title": "시험 강의",
        "open_on": "2026-11-03",
        "close_on": "2026-11-17",  # 2일 강의(11-02~03) 종료 + 14
    }
    assert [tuple(r) for r in opened] == [
        ("notice-0@example.com", params),
        ("notice-1@example.com", params),
        ("notice-x@example.com", params),
    ]
    factory = make_session_factory(
        db_connection, join_transaction_mode="create_savepoint"
    )

    async def bodies(kind: str) -> list[tuple[str, str]]:
        assert await outbox_preview.run([], factory) == 0
        out = json.loads(capsys.readouterr().out)
        return [(m["to"], m["body"]) for m in out["messages"] if m["kind"] == kind]

    first = await bodies("survey_opened")
    assert [to for to, _ in first] == [to for to, _ in opened]
    for _, body in first:
        assert "「시험 강의」" in body and "11월 3일에 열립니다" in body, body
        assert "11월 17일까지" in body, body
    sent = select(MailOutbox.sent_at).where(MailOutbox.kind.like("survey_%"))
    assert set((await db.scalars(sent)).all()) == {None}  # 미리 보기는 롤백

    await close.close_survey(db, survey_id=row.id, today=TODAY, actor=ADMIN)
    closed = await bodies("survey_closed")
    assert [to for to, _ in closed] == ["notice-x@example.com"]
    assert "「시험 강의」" in closed[0][1] and "11월 3일에 닫혔습니다" in closed[0][1]

    # 설문·등록·강의 행을 지워도 본문은 같다(params 스냅샷)
    await db.execute(delete(Survey).where(Survey.course_id == x.course_id))
    await db.execute(delete(Enrollment).where(Enrollment.course_id == x.course_id))
    await remove.remove_course(db, x.course_id)
    assert await count(db, Course, Course.id == x.course_id) == 0
    assert await bodies("survey_opened") == first
    assert await bodies("survey_closed") == closed

    broken = {k: v for k, v in params.items() if k != "course_title"}
    await crud_outbox.enqueue(
        db, kind="survey_opened", params=broken, to="a@example.com"
    )
    assert await outbox_preview.run([], factory) == 3
    assert "전제 거절" in capsys.readouterr().err


async def test_survey_course_delete_cascades(db_session: AsyncSession) -> None:
    """수강생 없는 강의의 설문(밀려난 행 포함)은 강의 삭제(remove_course — 설문 행 id 순 잠금 뒤)가 같이 지운다. audit 은 남는다."""
    db = db_session
    course, _ = await open_test_course(db)
    (old,) = await deploy_to(db, [course.id])
    await close.close_survey(db, survey_id=old.id, today=TODAY, actor=ADMIN)
    await deploy_to(db, [course.id])  # 닫힌 설문을 밀어내고 새 현재 설문
    assert await count(db, Survey, Survey.course_id == course.id) == 2
    await remove.remove_course(db, course.id)
    assert await count(db, Survey, Survey.course_id == course.id) == 0
    deployed = (
        AuditLog.action == "survey.deploy",
        AuditLog.target_type == "course",
        AuditLog.target_id == str(course.id),
    )
    assert await count(db, AuditLog, *deployed) == 2


async def test_survey_patch_close_on_not_before_today(db_session: AsyncSession) -> None:
    """PATCH 의 닫힘일은 오늘 이상이다(리뷰 반영) — 열린 설문의 닫힘일을 지난날로 당겨 날짜로 닫으면 closed_at·알림·audit 이
    빈 채 닫히므로 막는다(닫으려면 :close). 예약 설문도 같다. 거절되면 칸·audit 이 그대로고, 오늘 당일은 받는다."""
    db = db_session
    course, _ = await open_test_course(db)
    later, _ = await open_test_course(db, title="예약 강의")
    (opened,) = await deploy_to(db, [course.id])  # 11-03 ~ 11-19
    (scheduled,) = await deploy_to(
        db, [later.id], open={"mode": "date", "date": dt.date(2026, 11, 25)}
    )
    today = dt.date(2026, 11, 10)
    updates = (AuditLog.action == "survey.update",)
    for row, status in ((opened, "open"), (scheduled, "scheduled")):
        before = (row.open_on, row.close_on)
        assert (
            status_at(
                open_on=row.open_on, close_on=row.close_on, closed_at=None, today=today
            )
            == status
        )
        with pytest.raises(DatesRejected) as caught:
            await close.patch_survey(
                db,
                survey_id=row.id,
                changes={"close_on": today - DAY},
                today=today,
                actor=ADMIN,
            )
        assert (caught.value.reason, caught.value.course_id) == (
            "close_before_today",
            None,
        ), status
        fresh = await crud_survey.get_survey(db, row.id, fresh=True)
        assert fresh is not None
        assert ((fresh.open_on, fresh.close_on), fresh.closed_at) == (before, None)
    assert await count(db, AuditLog, *updates) == 0
    # 오늘 당일은 받는다 — 오늘까지 열려 있다
    patched = await close.patch_survey(
        db, survey_id=opened.id, changes={"close_on": today}, today=today, actor=ADMIN
    )
    assert patched.close_on == today
    assert (
        status_at(open_on=patched.open_on, close_on=today, closed_at=None, today=today)
        == "open"
    )
    assert await count(db, AuditLog, *updates) == 1


async def test_survey_instructor_results_single_statement(
    db_connection: AsyncConnection, db_session: AsyncSession
) -> None:
    """관리자 결과(admin_results)·강사 결과(instructor_results) 각각에서 survey·survey_response 를 읽는 문장은 하나다(설문 행 ·
    강의 행 · 답 배열을 한 SELECT 로 — 상태와 답이 한 스냅샷). 응답 0건이면 답은 NULL 이 아니라 빈 배열이고 종합은 null 이다."""
    db = db_session
    x = await _course_with_people(db, learners=1, tag="stmt")
    (row,) = await deploy_to(db, [x.course_id])
    await close.close_survey(db, survey_id=row.id, today=TODAY, actor=ADMIN)
    found = await crud_survey_response.survey_with_answers(db, row.id)
    assert found is not None and found[2] == []
    teacher = Principal("instructor", x.instructor_id)

    statements: list[str] = []

    def collect(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        statements.append(statement)

    target = db_connection.sync_connection
    assert target is not None
    event.listen(target, "before_cursor_execute", collect)
    try:
        statements.clear()
        admin = await results.admin_results(db, survey_id=row.id, today=TODAY)
        admin_sql = list(statements)
        statements.clear()
        mine = await results.instructor_results(
            db, teacher, course_id=x.course_id, today=TODAY, min_responses=1
        )
        mine_sql = list(statements)
    finally:
        event.remove(target, "before_cursor_execute", collect)

    def survey_reads(sql: list[str]) -> list[str]:
        skip = ("SAVEPOINT", "RELEASE", "ROLLBACK")
        return [
            s
            for s in sql
            if SURVEY_SQL.search(s) and not s.lstrip().upper().startswith(skip)
        ]

    assert len(survey_reads(admin_sql)) == 1, admin_sql
    assert len(survey_reads(mine_sql)) == 1, mine_sql
    assert (admin.responses, admin.total, admin.percent) == (0, 1, 0)
    assert admin.aggregate.overall is None and admin.head.status == "closed"
    assert (mine.responses, mine.visible, mine.reason) == (0, False, "below_minimum")


@dataclass(frozen=True)
class _Call:
    owner: str | None  # 받는 이름(crud_survey.lock_survey 면 crud_survey)
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


# 쓰기 진입점 열(T8 결정 xix · codex 1차 #5). 네 파일의 공개 async def 가운데 쓰기 crud 를 부르는 것은 이 열뿐이어야 한다
WRITERS = {
    "service/surveys/templates.py": (
        "create_template",
        "update_template",
        "delete_template",
        "set_default_template",
        "duplicate_template",
    ),
    "service/surveys/deploy.py": ("deploy",),
    "service/surveys/close.py": ("patch_survey", "close_survey", "reopen_survey"),
    "service/surveys/respond.py": ("submit",),
}
WRITE_PREFIXES = ("insert_", "apply_", "delete_", "set_")
WRITE_NAMES = {"supersede", "insert_audit", "enqueue"}
CRUD_MODULES: tuple[ModuleType, ...] = (
    crud_audit,
    crud_course,
    crud_enrollment,
    crud_flush,
    crud_outbox,
    crud_survey,
    crud_survey_response,
    crud_survey_template,
)


def _is_write(call: _Call) -> bool:
    return (call.owner or "").startswith("crud_") and (
        call.name.startswith(WRITE_PREFIXES) or call.name in WRITE_NAMES
    )


def _crud_names() -> set[str]:
    return {
        name
        for module in CRUD_MODULES
        for name, value in vars(module).items()
        if inspect.isfunction(value) and value.__module__ == module.__name__
    }


def _locked_by(relpath: str, function: str) -> set[str]:
    """그 crud 파일에서 with_for_update( 를 부르는 함수 이름."""
    return {
        node.name
        for node in _tree(relpath).body
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        and any(c.name == function for c in _calls(node))
    }


def test_survey_lock_call_sites() -> None:
    crud_names = _crud_names()
    # ① 쓰기 진입점 열 == 공개 async def 가운데 쓰기 crud 를 부르는 것 · ② crud 는 모듈 별칭 속성으로
    for relpath, functions in WRITERS.items():
        tree = _tree(relpath)
        writers = {
            node.name
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and not node.name.startswith("_")
            and any(_is_write(c) for c in _calls(node))
        }
        assert writers == set(functions), (relpath, writers)
        bare = [
            c.name
            for c in _calls(tree)
            if c.name in crud_names
            and not (c.owner or "").startswith("crud_")
            and c.owner not in ("self", "session")
        ]
        assert bare == [], f"{relpath}: crud 를 별칭 밖에서 부른다 — {bare}"
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module == "classfit.crud":
                assert all(a.asname == f"crud_{a.name}" for a in node.names), relpath
            elif module.startswith("classfit.crud."):
                loaded = importlib.import_module(module)
                # 형(Subject 등)만 들인다 — 함수는 별칭 속성으로
                for alias in node.names:
                    assert not inspect.isfunction(getattr(loaded, alias.name)), (
                        relpath,
                        alias.name,
                    )

    # ③ 배포: 양식 KEY SHARE → 강의 id 정렬 → lock_course → lock_survey → 잠근 뒤 get_survey(fresh=True) → insert_survey
    where = "deploy.py::deploy"
    calls = _calls(_function("service/surveys/deploy.py", "deploy"))
    order = [
        _first(calls, name, where)
        for name in ("lock_template_shared", "sorted", "lock_course", "lock_survey")
    ]
    fresh = [
        c.at
        for c in calls
        if c.name == "get_survey" and c.keywords.get("fresh") == "True"
    ]
    assert fresh, f"{where}: 잠근 뒤 get_survey(fresh=True) 가 없다"
    insert = _first(calls, "insert_survey", where)
    assert order == sorted(order) and order[-1] < fresh[0] < insert, where
    assert min(c.at for c in calls if _is_write(c)) > order[-1], where

    # ④ 양식 삭제: lock_template → lock_course(None 이면 건너뜀) → lock_in_id_order → delete_template
    where = "templates.py::delete_template"
    body = _function("service/surveys/templates.py", "delete_template")
    calls = _calls(body)
    steps = [
        _first(calls, name, where)
        for name in ("lock_template", "lock_course", "lock_in_id_order")
    ]
    crud_delete = [
        c.at
        for c in calls
        if c.name == "delete_template" and c.owner == "crud_survey_template"
    ]
    assert steps == sorted(steps) and crud_delete and steps[-1] < crud_delete[0], where
    skips = [
        node
        for node in ast.walk(body)
        if isinstance(node, ast.If)
        and any(c.name == "lock_course" for c in _calls(node.test))
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.ops[0], ast.Is)
        and [type(s) for s in node.body] == [ast.Continue]
    ]
    assert len(skips) == 1, f"{where}: lock_course 의 None 갈래가 continue 가 아니다"

    # ⑤ 양식 수정: 첫 호출이 lock_template
    calls = _calls(_function("service/surveys/templates.py", "update_template"))
    assert calls[0].name == "lock_template", calls[0]

    # ⑥ 기본 지정: 옛 기본 읽기 → lock_templates → 잠근 뒤 기본 재확인 → 옛 false · flush → 새 true · flush
    calls = _calls(_function("service/surveys/templates.py", "set_default_template"))
    watched = {
        "lock_templates",
        "default_template",
        "apply_template",
        "flush_or_conflict",
    }
    assert [c.name for c in calls if c.name in watched] == [
        "default_template",
        "lock_templates",
        "default_template",
        "apply_template",
        "flush_or_conflict",
        "apply_template",
        "flush_or_conflict",
    ]

    # ⑦ 닫기·다시 열기·고치기: lock_course → lock_survey 가 첫 쓰기 앞, 잠근 뒤 get_survey(fresh=True)(고치기는 count_responses)
    for fn in ("close_survey", "reopen_survey", "patch_survey"):
        where = f"close.py::{fn}"
        calls = _calls(_function("service/surveys/close.py", fn))
        course = _first(calls, "lock_course", where)
        survey = _first(calls, "lock_survey", where)
        writes = [
            c.at
            for c in calls
            if _is_write(c) or c.name in ("_audit", "_notify_closed")
        ]
        assert writes and course < survey < min(writes), where
        assert any(
            c.name == "get_survey"
            and c.at > survey
            and c.keywords.get("fresh") == "True"
            for c in calls
        ), f"{where}: 잠근 뒤 get_survey(fresh=True) 가 없다"
        if fn == "patch_survey":
            assert survey < _first(calls, "count_responses", where) < min(writes), where

    # ⑧ 제출: lock_survey → 잠근 뒤 get_survey(fresh=True) · find_response(fresh=True) → insert_response, 강의는 잡지 않는다
    where = "respond.py::submit"
    calls = _calls(_function("service/surveys/respond.py", "submit"))
    survey = _first(calls, "lock_survey", where)
    insert = _first(calls, "insert_response", where)
    assert not any(c.name == "lock_course" for c in calls), where
    for reread in ("get_survey", "find_response"):
        assert any(
            c.name == reread
            and survey < c.at < insert
            and c.keywords.get("fresh") == "True"
            for c in calls
        ), f"{where}: 잠근 뒤 {reread}(fresh=True) 가 없다"

    # ⑨ 결과: 잠그지 않고 한 문장(관리자 survey_with_answers · 강사 current_with_answers), 둘째 survey 읽기 없음
    tree = _tree("service/surveys/results.py")
    assert not any(c.name.startswith("lock_") for c in _calls(tree))
    text = (SRC / "service/surveys/results.py").read_text(encoding="utf-8")
    assert "course_header(" not in text and "session.get(" not in text
    admin = [
        c.name for c in _calls(_function("service/surveys/results.py", "admin_results"))
    ]
    assert admin.count("survey_with_answers") == 1
    mine = [
        c.name
        for c in _calls(_function("service/surveys/results.py", "instructor_results"))
    ]
    assert mine.count("current_with_answers") == 1
    assert "current_for_course" not in mine and "survey_with_answers" not in mine

    # ⑩ 강의 삭제(T2b remove_course): lock_course → lock_in_id_order(course_id=) → delete_course
    where = "remove.py::remove_course"
    calls = _calls(_function("service/courses/remove.py", "remove_course"))
    steps = [
        _first(calls, name, where)
        for name in ("lock_course", "lock_in_id_order", "delete_course")
    ]
    assert steps == sorted(steps), where
    (by_course,) = [c for c in calls if c.name == "lock_in_id_order"]
    assert by_course.keywords == {"course_id": "course_id"}, where

    # ⑪ 잠금 자리: crud/survey.py 둘 · crud/survey_template.py 셋, 배포 잠금은 FOR KEY SHARE 꼴
    assert _locked_by("crud/survey.py", "with_for_update") == {
        "lock_survey",
        "lock_in_id_order",
    }
    assert _locked_by("crud/survey_template.py", "with_for_update") == {
        "lock_template_shared",
        "lock_template",
        "lock_templates",
    }
    shared = [
        c
        for c in _calls(_function("crud/survey_template.py", "lock_template_shared"))
        if c.name == "with_for_update"
    ]
    assert [c.keywords for c in shared] == [{"read": "True", "key_share": "True"}]
