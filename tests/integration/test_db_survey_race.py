"""T8 동시성 행동 시험 열(T8 결정 xix): 제출 둘 · 닫기와 제출 · 첫 응답과 문항 수정 · 배포 둘 · 다시 열기와 배포 · 옛 양식
삭제와 다른 양식 재배포 · 기본 지정과 삭제 · 결과 한 스냅샷 · 양식 삭제와 배포 · 기본 지정 둘. 라이브 PG, 커밋한다.
이름 접두는 test_survey_race_(E-11 의 test_concurrent_ 와 다르다 — E-11 몫 하나는 tests/integration/test_db_concurrency.py).

도우미는 T5 tests/integration/test_db_assign_race.py 의 :77-206(WAIT_SECONDS … _race)과 :271-286(_ok · _count · _seed)을
그대로 복사했다(그 파일은 고치지 않는다). 장벽 도우미 _pause_after·_race_paused 는 복사하지 않았다 — ①~⑦·⑨·⑩ 은 A 가
함수를 끝내고 커밋 전에 서는 _race 꼴이고, ⑧ 은 B 세션의 execute·scalars·scalar 를 감싸 B 의 첫 survey 문장 직후 A 를
커밋시킨다(_commit_on_first_survey — 잠금 대기가 없어 _race 의 during 을 못 쓴다).
committing 은 끝에 SEED_TABLES 밖의 ORM 표를 TRUNCATE 한 뒤 survey_template 을 마이그레이션 직후 상태로 되돌린다 — 표를
비우고(RESTART IDENTITY) 0009 의 시드 상수 DEFAULT_TEMPLATE 한 행을 다시 넣는다(행 하나 · 기본 · 이름·비고·문항이 시드 값).
survey_template 은 SEED_TABLES 라 첫 TRUNCATE 가 비우지 않는데, 이 파일의 시험은 양식을 만들고 기본 지정이 기본을 옮긴다.
시험은 시드 행 자체를 고치지 않고(기본 표시만 옮겨진다) 새 양식을 만들어 쓴다.
A·B 는 운영 경로(service.surveys)로 부른다. 기다렸는지와 무엇을 기다렸는지(survey · course · survey_template)를 함께
단언하고, 결과 단언(행 수·칸 값)을 따로 둔다. 순서는 _waits_on_lock 폴링과 PG 의 잠금 줄이 정한다(sleep 없음).
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest_asyncio
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from classfit.core.config import Settings
from classfit.core.errors import Conflict, NotFound
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import survey_template as crud_survey_template
from classfit.crud.learner import get_or_create_learner
from classfit.database.session import make_engine, make_session_factory
from classfit.models import Base, Survey, SurveyResponse, SurveyTemplate
from classfit.service.auth.sessions import Principal
from classfit.service.rules.survey import questions_hash
from classfit.service.surveys import close, respond, results, templates
from tests.fixtures.courses import open_test_course
from tests.fixtures.records import assigned
from tests.fixtures.surveys import ANSWERS_OK, TODAY_RUNNING, deploy_to

WAIT_SECONDS = 5.0
POLL_SECONDS = 0.02
GATHER_SECONDS = 15.0

Factory = async_sessionmaker[AsyncSession]
Work = Callable[[AsyncSession], Awaitable[Any]]
# 마이그레이션이 넣는 시드 표는 비우지 않는다(0005 document_type · 0009 survey_template)
SEED_TABLES = frozenset({"document_type", "survey_template"})
ADMIN = "admin:1"
TODAY = TODAY_RUNNING
SURVEY_SQL = re.compile(r"\bFROM survey\b")
MIGRATION_0009 = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0009_surveys.py"
)


def _seed_template() -> dict[str, Any]:
    """0009 의 시드 한 행(DEFAULT_TEMPLATE) — 그 글자의 유일한 자리는 마이그레이션 파일이다."""
    spec = importlib.util.spec_from_file_location("migration_0009", MIGRATION_0009)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.DEFAULT_TEMPLATE)


@pytest_asyncio.fixture
async def committing(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    """커밋하는 엔진. 끝에 ORM 표를 비운다(sorted_tables, CASCADE). 시드 표 SEED_TABLES 는 남기고, survey_template 은
    마이그레이션 직후 상태(시드 한 행)로 되돌린다."""
    engine = make_engine(migrated_db_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        try:
            async with engine.begin() as conn:
                quote = conn.dialect.identifier_preparer.format_table
                names = ", ".join(
                    quote(t)
                    for t in Base.metadata.sorted_tables
                    if t.name not in SEED_TABLES
                )
                await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
                await conn.execute(
                    text("TRUNCATE survey_template RESTART IDENTITY CASCADE")
                )
                await conn.execute(
                    insert(SurveyTemplate.__table__).values(**_seed_template())
                )
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def factory(committing: AsyncEngine) -> Factory:
    return make_session_factory(committing)


async def _waits_on_lock(
    engine: AsyncEngine, pid: int, task: asyncio.Task[Any]
) -> bool:
    """B(pid)가 잠금을 기다리는 것을 보면 True, 못 보고 B 가 끝났거나 5초가 지나면 False.

    pg_stat_activity 는 트랜잭션 안에서 처음 읽은 값을 붙들므로 AUTOCOMMIT 으로 매번 새로 읽는다.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        while loop.time() < deadline and not task.done():
            wait = await conn.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            )
            if wait == "Lock":
                return True
            await asyncio.sleep(POLL_SECONDS)
    return False


async def _blocked_on(engine: AsyncEngine, pid: int) -> set[str]:
    """B(pid)가 쥔 tuple 잠금의 표 이름 — 행 잠금·UPDATE·DELETE 가 기다리는 행의 표다."""
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        rows = await conn.scalars(
            text(
                "SELECT c.relname FROM pg_locks l JOIN pg_class c ON c.oid = l.relation"
                " WHERE l.pid = :pid AND l.locktype = 'tuple'"
            ),
            {"pid": pid},
        )
        return set(rows.all())


async def _commit_after[T](
    session: AsyncSession, work: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    result = await work(session)
    await session.commit()
    return result


async def _lock_timeout(session: AsyncSession) -> int:
    """lock_timeout 10초를 걸고 백엔드 pid 를 돌려준다(교착·잠금 누수 때 멈추지 않고 빨개지게)."""
    await session.execute(text("SET LOCAL lock_timeout = '10s'"))
    pid = await session.scalar(text("SELECT pg_backend_pid()"))
    assert pid is not None
    return int(pid)


@dataclass
class Raced:
    first: Any  # A 결과(예외면 예외 객체)
    second: Any  # B 결과(예외면 예외 객체)
    waited: bool  # B 가 잠금을 기다렸는지
    blocked: set[str]  # B 가 기다린 행의 표


async def _race(
    factory: Factory,
    engine: AsyncEngine,
    hold: Work,
    contend: Work,
    during: Callable[[], Awaitable[None]] | None = None,
) -> Raced:
    """A 는 hold 뒤 커밋 전에 멈추고, B 를 띄워 기다림·대기 관계를 잰 뒤(그동안 during) A 를 커밋한다."""
    async with factory() as a, factory() as b:
        await _lock_timeout(a)
        first = await hold(a)
        pid = await _lock_timeout(b)
        task = asyncio.create_task(_commit_after(b, contend))
        try:
            waited = await _waits_on_lock(engine, pid, task)
            blocked = await _blocked_on(engine, pid) if waited else set()
            if during is not None:
                await during()
            await a.commit()
            (second,) = await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True), GATHER_SECONDS
            )
        finally:
            if not task.done():
                await a.rollback()  # A 의 잠금을 풀어 B 가 끝나게 한다
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    return Raced(first, second, waited, blocked)


def _ok(raced: Raced) -> None:
    """A·B 둘 다 예외 없음(40P01 교착 · 55P03 lock_timeout · 23503 · 500 없음)."""
    for value in (raced.first, raced.second):
        assert not isinstance(value, BaseException), repr(value)


async def _count(factory: Factory, model: type, *where: Any) -> int:
    async with factory() as s:
        return (
            await s.scalar(select(func.count()).select_from(model).where(*where)) or 0
        )


async def _seed[T](factory: Factory, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async with factory() as s, s.begin():
        return await work(s)


@dataclass(frozen=True)
class _Deployed:
    course_id: int
    survey_id: int
    version: str  # 문항 판 해시
    learners: list[Principal]
    instructor_id: int | None


async def _learners(s: AsyncSession, course_id: int, n: int) -> list[Principal]:
    """그 강의 등록 n 개(crud 로 직접) — 수강생 주체 n 개."""
    out = []
    for i in range(n):
        learner = await get_or_create_learner(s, f"race-{course_id}-{i}@example.com")
        await crud_enrollment.insert_enrollment(
            s, course_id=course_id, learner_id=learner.id, name=f"가명{i}", dept=None
        )
        out.append(Principal("learner", learner.id, course_id))
    return out


async def _deployed(
    s: AsyncSession, *, learners: int = 1, instructor: bool = False
) -> _Deployed:
    """강의(instructor 면 배정 강사가 있는 강의) · 등록 learners 개 · 기본 양식 배포(오늘 열림)."""
    iid = None
    if instructor:
        x = await assigned(s, Settings(_env_file=None), email="race-x@example.com")
        course_id, iid = x.course_id, x.instructor_id
    else:
        course, _ = await open_test_course(s)
        course_id = course.id
    people = await _learners(s, course_id, learners)
    (row,) = await deploy_to(s, [course_id])
    return _Deployed(course_id, row.id, questions_hash(row.questions), people, iid)


def _submit(seeded: _Deployed, who: Principal) -> Work:
    async def run(s: AsyncSession) -> Survey:
        return await respond.submit(
            s,
            who,
            course_id=seeded.course_id,
            survey_id=seeded.survey_id,
            questions_hash=seeded.version,
            answers=ANSWERS_OK,
            today=TODAY,
        )

    return run


def _deploy(course_ids: list[int], template_id: int | None = None) -> Work:
    async def run(s: AsyncSession) -> list[Survey]:
        return await deploy_to(s, course_ids, template_id=template_id)

    return run


async def _new_template(s: AsyncSession, name: str) -> int:
    seed = await crud_survey_template.default_template(s)
    assert seed is not None
    view = await templates.create_template(
        s, name=name, note=None, questions=seed.questions, actor=ADMIN
    )
    return view.id


async def _defaults(factory: Factory) -> list[int]:
    async with factory() as s:
        stmt = select(SurveyTemplate.id).where(SurveyTemplate.is_default.is_(True))
        return list((await s.scalars(stmt)).all())


async def _survey(factory: Factory, survey_id: int) -> Survey:
    async with factory() as s:
        row = await s.get(Survey, survey_id)
        assert row is not None
        return row


async def test_survey_race_double_submit_one_row(
    factory: Factory, committing: AsyncEngine
) -> None:
    """① 같은 등록의 제출 둘 → B 는 설문 행에서 기다렸다 A 의 응답을 보고 Conflict(23505·500 아님) · 응답 1행."""
    seeded = await _seed(factory, _deployed)
    work = _submit(seeded, seeded.learners[0])
    raced = await _race(factory, committing, work, work)
    assert (raced.waited, raced.blocked) == (True, {"survey"})
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert (
        await _count(
            factory, SurveyResponse, SurveyResponse.survey_id == seeded.survey_id
        )
        == 1
    )


async def test_survey_race_close_then_submit_409(
    factory: Factory, committing: AsyncEngine
) -> None:
    """② 관리자 닫기(A)가 커밋 전인 사이 제출(B) → B 는 설문 행에서 기다렸다 닫힘을 보고 Conflict · 응답 0."""
    seeded = await _seed(factory, _deployed)

    async def shut(s: AsyncSession) -> Survey:
        return await close.close_survey(
            s, survey_id=seeded.survey_id, today=TODAY, actor=ADMIN
        )

    raced = await _race(factory, committing, shut, _submit(seeded, seeded.learners[0]))
    assert (raced.waited, raced.blocked) == (True, {"survey"})
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert (
        await _count(
            factory, SurveyResponse, SurveyResponse.survey_id == seeded.survey_id
        )
        == 0
    )
    assert (await _survey(factory, seeded.survey_id)).closed_at is not None


async def test_survey_race_first_response_locks_questions(
    factory: Factory, committing: AsyncEngine
) -> None:
    """③ 첫 제출(A)이 커밋 전인 사이 문항 수정(B) → B 는 설문 행에서 기다렸다 응답 1건을 세고 Conflict · 문항 그대로."""
    seeded = await _seed(factory, _deployed)
    before = (await _survey(factory, seeded.survey_id)).questions
    changed = [q | {"text": "바꾼 문구"} if q["key"] == "b01" else q for q in before]

    async def edit(s: AsyncSession) -> Survey:
        return await close.patch_survey(
            s,
            survey_id=seeded.survey_id,
            changes={"questions": changed},
            today=TODAY,
            actor=ADMIN,
        )

    raced = await _race(factory, committing, _submit(seeded, seeded.learners[0]), edit)
    assert (raced.waited, raced.blocked) == (True, {"survey"})
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert (await _survey(factory, seeded.survey_id)).questions == before


async def test_survey_race_deploy_twice_waits_on_course(
    factory: Factory, committing: AsyncEngine
) -> None:
    """④ 같은 강의 배포 둘 → B 는 강의 행에서 기다렸다(부분 유일 색인이 아니라) A 의 열린 설문을 보고 Conflict · 설문 1행."""

    async def seed(s: AsyncSession) -> int:
        course, _ = await open_test_course(s)
        return course.id

    course_id = await _seed(factory, seed)
    work = _deploy([course_id])
    raced = await _race(factory, committing, work, work)
    assert (raced.waited, raced.blocked) == (True, {"course"})
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert await _count(factory, Survey, Survey.course_id == course_id) == 1


async def test_survey_race_reopen_then_deploy_409(
    factory: Factory, committing: AsyncEngine
) -> None:
    """⑤ 닫힌 현재 설문 S 를 다시 여는(A) 사이 같은 강의 배포(B) → B 는 강의 행에서 기다렸다 S 가 열림임을 보고 Conflict.

    S 는 밀려나지 않는다(current ∧ open — v1 의 좀비가 없다) · 설문 1행.
    """

    async def seed(s: AsyncSession) -> _Deployed:
        seeded = await _deployed(s)
        await close.close_survey(
            s, survey_id=seeded.survey_id, today=TODAY, actor=ADMIN
        )
        return seeded

    seeded = await _seed(factory, seed)

    async def reopen(s: AsyncSession) -> Survey:
        return await close.reopen_survey(
            s, survey_id=seeded.survey_id, today=TODAY, actor=ADMIN
        )

    raced = await _race(factory, committing, reopen, _deploy([seeded.course_id]))
    assert (raced.waited, raced.blocked) == (True, {"course"})
    assert isinstance(raced.second, Conflict), repr(raced.second)
    row = await _survey(factory, seeded.survey_id)
    assert (row.current, row.closed_at, row.reopened_at is not None) == (
        True,
        None,
        True,
    )
    assert await _count(factory, Survey, Survey.course_id == seeded.course_id) == 1


async def test_survey_race_template_delete_waits_on_course(
    factory: Factory, committing: AsyncEngine
) -> None:
    """⑥ 양식 T1 의 닫힌 설문이 있는 강의 둘에 기본 양식으로 다시 배포(A — 밀어내기 둘)하는 사이 T1 삭제(B) →
    B 는 T1 을 바로 잡고 강의 행에서 기다렸다 성공(40P01·lock_timeout 없음). 옛 설문 둘은 template_id NULL ∧ current false."""

    async def seed(s: AsyncSession) -> tuple[list[int], int, int]:
        t1 = await _new_template(s, "옛 양식")
        ids = []
        for title in ("강의 A", "강의 B"):
            course, _ = await open_test_course(s, title=title)
            ids.append(course.id)
        old = await deploy_to(s, ids, template_id=t1)
        for row in old:
            await close.close_survey(s, survey_id=row.id, today=TODAY, actor=ADMIN)
        default = await crud_survey_template.default_template(s)
        assert default is not None
        return ids, t1, default.id

    course_ids, t1, t2 = await _seed(factory, seed)

    async def remove(s: AsyncSession) -> None:
        await templates.delete_template(s, template_id=t1, actor=ADMIN)

    raced = await _race(factory, committing, _deploy(course_ids, t2), remove)
    assert (raced.waited, raced.blocked) == (True, {"course"})
    _ok(raced)
    async with factory() as s:
        rows = (
            await s.execute(
                select(Survey.course_id, Survey.template_id, Survey.current)
                .where(Survey.course_id.in_(course_ids))
                .order_by(Survey.course_id, Survey.id)
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        (course_ids[0], None, False),
        (course_ids[0], t2, True),
        (course_ids[1], None, False),
        (course_ids[1], t2, True),
    ]
    assert await _count(factory, SurveyTemplate, SurveyTemplate.id == t1) == 0


async def test_survey_race_set_default_then_delete_409(
    factory: Factory, committing: AsyncEngine
) -> None:
    """⑦ 기본 지정 T2(A — 옛 기본·T2 FOR UPDATE)가 커밋 전인 사이 T2 삭제(B) → B 는 양식 행에서 기다렸다 기본임을 보고 Conflict."""
    t2 = await _seed(factory, lambda s: _new_template(s, "새 기본"))

    async def make_default(s: AsyncSession) -> Any:
        return await templates.set_default_template(s, template_id=t2, actor=ADMIN)

    async def remove(s: AsyncSession) -> None:
        await templates.delete_template(s, template_id=t2, actor=ADMIN)

    raced = await _race(factory, committing, make_default, remove)
    assert (raced.waited, raced.blocked) == (True, {"survey_template"})
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert await _defaults(factory) == [t2]


def _commit_on_first_survey(b: AsyncSession, a: AsyncSession) -> list[bool]:
    """b 의 execute·scalars·scalar 를 감싸 b 가 survey 를 읽는 첫 문장 직후 a 를 커밋한다. 돌려준 목록에 커밋 여부가 남는다.

    scalars 는 안에서 execute 를 다시 부르므로(인스턴스 속성 감싸개를 탄다) 한 번만 커밋한다. scalar 는 execute 를 거치지
    않으므로 따로 감싼다.
    """
    fired: list[bool] = []
    for name in ("execute", "scalars", "scalar"):
        orig = getattr(b, name)

        async def wrapped(*args: Any, _orig: Any = orig, **kwargs: Any) -> Any:
            result = await _orig(*args, **kwargs)
            if not fired and args and SURVEY_SQL.search(str(args[0])):
                fired.append(True)
                await a.commit()
            return result

        setattr(b, name, wrapped)
    return fired


async def test_survey_race_results_single_snapshot(
    factory: Factory, committing: AsyncEngine
) -> None:
    """⑧ 닫힌 설문 S(응답 n)를 A 가 다시 열고 응답 하나를 넣은 채 서 있는 사이, B 의 결과 읽기가 첫 survey 문장을 보낸
    직후 A 가 커밋한다 → 관리자·강사 결과 둘 다 상태·응답 수·집계가 전부 전(closed, n)이다(한 문장 — 두 문장이면 섞인다)."""

    async def seed(s: AsyncSession) -> _Deployed:
        seeded = await _deployed(s, learners=4, instructor=True)
        for who in seeded.learners[:2]:
            await _submit(seeded, who)(s)
        await close.close_survey(
            s, survey_id=seeded.survey_id, today=TODAY, actor=ADMIN
        )
        return seeded

    seeded = await _seed(factory, seed)
    assert seeded.instructor_id is not None
    teacher = Principal("instructor", seeded.instructor_id)
    for case, (n, newcomer) in enumerate(
        ((2, seeded.learners[2]), (3, seeded.learners[3]))
    ):
        if case == 1:  # 앞 사례가 다시 열었다 — 다시 닫는다(응답 3)
            await _seed(
                factory,
                lambda s: close.close_survey(
                    s, survey_id=seeded.survey_id, today=TODAY, actor=ADMIN
                ),
            )
        async with factory() as a, factory() as b:
            await _lock_timeout(a)
            await _lock_timeout(b)
            await close.reopen_survey(
                a, survey_id=seeded.survey_id, today=TODAY, actor=ADMIN
            )
            await _submit(seeded, newcomer)(a)
            fired = _commit_on_first_survey(b, a)
            if case == 0:
                got: Any = await results.admin_results(
                    b, survey_id=seeded.survey_id, today=TODAY
                )
                overall = got.aggregate.overall
            else:
                got = await results.instructor_results(
                    b, teacher, course_id=seeded.course_id, today=TODAY, min_responses=1
                )
                assert (got.visible, got.reason) == (True, None)
                overall = got.aggregate.overall
            seen = (got.head.status, got.head.current, got.responses, got.total)
            await b.rollback()
        assert fired == [True], case
        assert seen == ("closed", True, n, 4), case
        assert (got.head.responses, overall.n) == (n, n), case
        assert (
            await _count(
                factory, SurveyResponse, SurveyResponse.survey_id == seeded.survey_id
            )
            == n + 1
        )


async def test_survey_race_template_delete_then_deploy_404(
    factory: Factory, committing: AsyncEngine
) -> None:
    """⑨ 양식 T 삭제(A — T FOR UPDATE)가 커밋 전인 사이 T 로 배포(B) → B 는 양식 행(KEY SHARE)에서 기다렸다 NotFound(23503 아님)."""

    async def seed(s: AsyncSession) -> tuple[int, int]:
        template_id = await _new_template(s, "지울 양식")
        course, _ = await open_test_course(s)
        return template_id, course.id

    template_id, course_id = await _seed(factory, seed)

    async def remove(s: AsyncSession) -> None:
        await templates.delete_template(s, template_id=template_id, actor=ADMIN)

    raced = await _race(factory, committing, remove, _deploy([course_id], template_id))
    assert (raced.waited, raced.blocked) == (True, {"survey_template"})
    assert isinstance(raced.second, NotFound), repr(raced.second)
    assert await _count(factory, Survey, Survey.course_id == course_id) == 0


async def test_survey_race_set_default_twice_409(
    factory: Factory, committing: AsyncEngine
) -> None:
    """⑩ 기본 지정 T2(A)가 커밋 전인 사이 기본 지정 T3(B — 잠그기 전 읽은 옛 기본은 시드) → B 는 옛 기본 행에서 기다렸다
    잠근 뒤 지금 기본(T2)이 옛 기본과 달라 Conflict(23505·500 아님) · 기본은 T2 하나."""

    async def seed(s: AsyncSession) -> tuple[int, int]:
        return await _new_template(s, "둘째"), await _new_template(s, "셋째")

    t2, t3 = await _seed(factory, seed)

    def make_default(template_id: int) -> Work:
        async def run(s: AsyncSession) -> Any:
            return await templates.set_default_template(
                s, template_id=template_id, actor=ADMIN
            )

        return run

    raced = await _race(factory, committing, make_default(t2), make_default(t3))
    assert (raced.waited, raced.blocked) == (True, {"survey_template"})
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert await _defaults(factory) == [t2]
