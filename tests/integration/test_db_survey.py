"""만족도 설문 표와 crud(T8 결정 iii·iv·v·xix): 기본 양식 시드 · 표 제약 · 상태 SQL 판 · 잠금 SQL 글자. 라이브 PG.

alembic check 는 CHECK·시드를 비교하지 않으므로 여기서 잰다. 행은 표에 직접 넣거나 crud 로 만든다(HTTP 없음). 강의는 단일
진입점 open_test_course, 등록은 crud(get_or_create_learner · insert_enrollment)로 만든다. 행 id·시퀀스 번호는 단언하지 않는다.
잠금이 실제로 줄 세우는지는 tests/integration/test_db_survey_race.py 가 잰다.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import course as crud_course
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import survey as crud_survey
from classfit.crud import survey_template as crud_survey_template
from classfit.crud.learner import get_or_create_learner
from classfit.models import Enrollment, Survey, SurveyResponse, SurveyTemplate
from classfit.service.rules.survey import status_at
from tests.fixtures.courses import open_test_course
from tests.fixtures.instructors import count

DAY = dt.timedelta(days=1)
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
