"""강의 상태: Python 판(rules.status.course_status_at)과 SQL 판(crud.course.course_status_sql)이 같다. 라이브 PG.

기간 위치 5 × (수동 아님 + 수동 3값) = 강의 20개를 open_course 로 만들고, 오늘 3개(기준 시작일·종료일·종료 다음 날)마다
행마다 두 판을 대조한다. 경계(종료일 당일 running, 다음 날 ended)가 갈리면 여기서 빨개진다.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.course import course_status_sql, update_course
from classfit.models import Course
from classfit.service.rules.status import course_status_at
from tests.fixtures.courses import open_test_course

START, END = date(2026, 11, 2), date(2026, 11, 6)
DAY = timedelta(days=1)
PERIODS = [
    (START, END),  # 기준 기간
    (START, START),  # 시작일 하루
    (END, END),  # 종료일 하루
    (END + DAY, END + 5 * DAY),  # 앞으로
    (START - 10 * DAY, START - DAY),  # 지난
]
MANUAL = [None, "prep", "running", "ended"]
TODAYS = [START, END, END + DAY]


async def test_course_status_python_matches_sql(db_session: AsyncSession) -> None:
    ids: list[int] = []
    for start_on, end_on in PERIODS:
        for manual in MANUAL:
            course, _ = await open_test_course(
                db_session, day_count=0, start_on=start_on, end_on=end_on
            )
            if manual is not None:
                await update_course(
                    db_session, course, status=manual, status_manual=True
                )
            ids.append(course.id)
    assert len(ids) == len(PERIODS) * len(MANUAL) == 20

    seen: set[str] = set()
    for today in TODAYS:
        stmt = (
            select(
                Course.id,
                Course.start_on,
                Course.end_on,
                Course.status,
                Course.status_manual,
                course_status_sql(today),
            )
            .where(Course.id.in_(ids))
            .order_by(Course.id)
        )
        rows = (await db_session.execute(stmt)).all()
        assert len(rows) == 20
        mismatched = []
        for cid, start_on, end_on, status, manual, sql_status in rows:
            py_status = course_status_at(
                start_on=start_on,
                end_on=end_on,
                status=status,
                status_manual=manual,
                today=today,
            )
            seen.add(sql_status)
            if py_status != sql_status:
                mismatched.append(
                    (
                        cid,
                        start_on,
                        end_on,
                        status,
                        manual,
                        today,
                        py_status,
                        sql_status,
                    )
                )
        assert mismatched == []
    assert seen == {"prep", "running", "ended"}  # 대조가 비어 있지 않다
