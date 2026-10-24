"""T9a 동시성 행동 시험 아홉(T9a 결정 xi·xvi + codex 구현 리뷰 1차 ③④): 링크 발급 · 같은 토큰 제출 · 확정과 수정 · 회수와
제출 · 개설 ③ 과 회사 삭제(두 방향) · 회사 삭제와 보관 강의 쓰기 · 회사 삭제와 설문 양식 삭제(보관 강의 둘 — 강의 잠금 순서) ·
회사 삭제와 회사 PATCH. 라이브 PG, 커밋한다. 이름 접두는 test_diag_race_(E-11 의 test_concurrent_ 와 다르다).

틀은 T5 tests/integration/test_db_assign_race.py(T8 병합 판)의 도우미를 그대로 복사했다(그 파일은 고치지 않는다):
커밋하는 NullPool 엔진 committing(끝에 SEED_TABLES 밖의 ORM 표를 TRUNCATE — 0005 document_type · 0009 survey_template 시드는
남긴다) · factory · pg_stat_activity 로 "B 가 기다렸다" 를 재는 _waits_on_lock · B 가 기다린 행의 표 _blocked_on ·
_commit_after · _lock_timeout · _race(A 가 함수를 끝내고 커밋 전에 선다) · _ok · _count · _seed, 그리고 장벽 도우미
_pause_after · _race_paused(A 를 crud 호출 하나 뒤에 세운다 — 양식 삭제가 강의 1 만 잡은 순간, codex 1차 ③).
일곱 다 무엇을 기다렸는지(blocked)와 결과(행 수·칸 값·예외 종류·audit 수)를 따로 단언한다. 오늘은 today= 로 준다.
순서는 시간이 아니라 Event 와 _waits_on_lock 폴링이 정한다(sleep 없음). A·B 둘 다 lock_timeout 10초.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

import classfit.crud.course
from classfit.core.errors import Conflict, Gone, NotFound
from classfit.crud import course as crud_course
from classfit.database.session import make_engine, make_session_factory
from classfit.models import (
    AuditLog,
    Base,
    Company,
    Course,
    DiagLink,
    Diagnosis,
    InviteCode,
    Survey,
    SurveyTemplate,
)
from classfit.schemas.course import CourseOpenIn, CoursePatchIn
from classfit.service.courses import days
from classfit.service.courses.open import open_course
from classfit.service.diagnosis import companies, links, public, rounds
from classfit.service.surveys import templates
from tests.fixtures.courses import open_test_course
from tests.fixtures.diagnosis import (
    ACTOR,
    ANSWERS_ALL_5,
    ANSWERS_MIXED,
    FIELD_SAMPLE,
    MATRIX_SAMPLE,
    RECO_SAMPLE,
    RESPONDENT,
    TODAY,
    UNDATED_BODY,
    insert_link,
    insert_round,
    make_company,
    make_token,
)

WAIT_SECONDS = 5.0
POLL_SECONDS = 0.02
GATHER_SECONDS = 15.0

Factory = async_sessionmaker[AsyncSession]
Work = Callable[[AsyncSession], Awaitable[Any]]
# 마이그레이션이 넣는 시드 표는 비우지 않는다(0005 document_type · 0009 survey_template, T8 병합 판과 같다)
SEED_TABLES = frozenset({"document_type", "survey_template"})


@dataclass(frozen=True)
class _Admin:
    type: str = "admin"
    id: int = 1
    course_id: int | None = None


@pytest_asyncio.fixture
async def committing(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    """커밋하는 엔진. 끝에 ORM 표를 비운다(sorted_tables, CASCADE). 시드 표 SEED_TABLES 는 남긴다."""
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


def _pause_after(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, name: str
) -> tuple[asyncio.Event, asyncio.Event]:
    """(held, release). module.name 의 첫 호출만 진짜 함수를 끝낸 뒤 held 를 켜고 release 를 기다린다."""
    real = getattr(module, name)
    held, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        result = await real(*args, **kwargs)
        if calls == 1:
            held.set()
            await release.wait()
        return result

    monkeypatch.setattr(module, name, wrapper)
    return held, release


async def _race_paused(
    factory: Factory,
    engine: AsyncEngine,
    held: asyncio.Event,
    release: asyncio.Event,
    hold: Work,
    contend: Work,
) -> Raced:
    """A 를 장벽까지 보내고 B 를 띄워 기다림·대기 관계를 잰 뒤 장벽을 푼다. 둘 다 끝나면 결과를 모은다."""
    async with factory() as a, factory() as b:
        await _lock_timeout(a)
        a_task = asyncio.create_task(_commit_after(a, hold))
        b_task: asyncio.Task[Any] | None = None
        try:
            barrier = asyncio.create_task(held.wait())
            await asyncio.wait(
                {a_task, barrier},
                timeout=WAIT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            barrier.cancel()
            if not held.is_set():
                detail = a_task.exception() if a_task.done() else "5초 초과"
                raise AssertionError(f"장벽에 닿지 않음: {detail!r}")
            pid = await _lock_timeout(b)
            b_task = asyncio.create_task(_commit_after(b, contend))
            waited = await _waits_on_lock(engine, pid, b_task)
            blocked = await _blocked_on(engine, pid) if waited else set()
            release.set()
            first, second = await asyncio.wait_for(
                asyncio.gather(a_task, b_task, return_exceptions=True), GATHER_SECONDS
            )
        finally:
            release.set()
            pending = [t for t in (a_task, b_task) if t is not None and not t.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
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


async def _audits(factory: Factory, action: str) -> list[dict[str, Any]]:
    async with factory() as s:
        rows = await s.scalars(
            select(AuditLog.detail)
            .where(AuditLog.action == action)
            .order_by(AuditLog.id)
        )
        return list(rows.all())


def _diagnosis_body(diagnosis_id: int) -> CourseOpenIn:
    return CourseOpenIn.model_validate(
        {"start": "diagnosis", "diagnosis_id": diagnosis_id, **UNDATED_BODY}
    )


def _issue(company_id: int) -> Work:
    async def work(s: AsyncSession) -> DiagLink:
        return await links.issue_link(
            s,
            company_id=company_id,
            phase="pre",
            recipient=None,
            expires_on=None,
            today=TODAY,
            actor=ACTOR,
        )

    return work


def _submit(token: str) -> Work:
    async def work(s: AsyncSession) -> DiagLink:
        return await public.submit(
            s,
            token=token,
            answers=ANSWERS_MIXED,
            field=FIELD_SAMPLE,
            matrix=MATRIX_SAMPLE,
            respondent=RESPONDENT,
            today=TODAY,
        )

    return work


def _delete_company(company_id: int) -> Work:
    async def work(s: AsyncSession) -> None:
        await companies.delete_company(s, company_id=company_id, actor=ACTOR)

    return work


def _open_from(diagnosis_id: int) -> Work:
    async def work(s: AsyncSession) -> Course:
        course, _ = await open_course(
            s, _diagnosis_body(diagnosis_id), actor=ACTOR, invite_expiry_days=30
        )
        return course

    return work


async def _company_with_link(
    factory: Factory, tag: str, **link: Any
) -> tuple[int, str]:
    async def seed(s: AsyncSession) -> tuple[int, str]:
        company = await make_company(s)
        row = await insert_link(s, company.id, token=make_token(tag), **link)
        return company.id, row.token

    return await _seed(factory, seed)


async def _company_with_final(factory: Factory) -> tuple[int, int]:
    async def seed(s: AsyncSession) -> tuple[int, int]:
        company = await make_company(s)
        row = await insert_round(
            s,
            company.id,
            round_no=1,
            answers=ANSWERS_MIXED,
            status="final",
            reco=RECO_SAMPLE,
        )
        return company.id, row.id

    return await _seed(factory, seed)


async def test_diag_race_issue_two_links_one_open(
    factory: Factory, committing: AsyncEngine
) -> None:
    """만료 지난 open 링크 E 가 있는 회사에 발급 둘 — 하나는 E 를 회수하고 발급, 다른 하나는 잠근 뒤 만료 전 open 을 보고 409."""
    company_id, old = await _company_with_link(
        factory,
        "race-expired",
        issued_on=TODAY - dt.timedelta(days=15),
        expires_on=TODAY - dt.timedelta(days=1),
    )
    raced = await _race(factory, committing, _issue(company_id), _issue(company_id))
    assert (raced.waited, raced.blocked) == (True, {"company"})
    assert isinstance(raced.first, DiagLink), repr(raced.first)
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert raced.second.__cause__ is None  # 23505(부분 유일)가 아니라 잠근 뒤의 판정
    opened = DiagLink.company_id == company_id, DiagLink.status == "open"
    assert await _count(factory, DiagLink, *opened) == 1
    assert await _count(factory, DiagLink, DiagLink.token == raced.first.token) == 1
    revoked = DiagLink.token == old, DiagLink.status == "revoked"
    assert await _count(factory, DiagLink, *revoked) == 1
    assert len(await _audits(factory, "diag_link.issue")) == 1
    assert await _audits(factory, "diag_link.revoke") == [
        {"token_prefix": old[:8], "reason": "expired"}
    ]


async def test_diag_race_submit_same_token_once(
    factory: Factory, committing: AsyncEngine
) -> None:
    """같은 토큰의 제출 둘 — 하나만 회차를 만들고, 다른 하나는 잠근 뒤 링크를 다시 읽어 410(submitted)."""
    company_id, token = await _company_with_link(factory, "race-submit")
    raced = await _race(factory, committing, _submit(token), _submit(token))
    assert (raced.waited, raced.blocked) == (True, {"company"})
    assert isinstance(raced.first, DiagLink), repr(raced.first)
    assert isinstance(raced.second, Gone), repr(raced.second)
    assert raced.second.extra == {"reason": "submitted"}
    review = Diagnosis.company_id == company_id
    assert await _count(factory, Diagnosis, review) == 1
    assert (
        await _count(
            factory,
            Diagnosis,
            review,
            Diagnosis.status == "review",
            Diagnosis.mode == "link",
        )
        == 1
    )
    done = DiagLink.token == token, DiagLink.status == "submitted"
    assert await _count(factory, DiagLink, *done) == 1
    assert len(await _audits(factory, "diag_link.submit")) == 1


async def test_diag_race_finalize_vs_patch_409(
    factory: Factory, committing: AsyncEngine
) -> None:
    """확정 중인 회차를 고치려는 PATCH 는 회사 잠금을 기다린 뒤 final 을 보고 409 — 확정본의 답이 그대로다."""

    async def seed(s: AsyncSession) -> int:
        company = await make_company(s)
        row = await insert_round(s, company.id, round_no=1, answers=ANSWERS_MIXED)
        return row.id

    round_id = await _seed(factory, seed)

    async def finalize(s: AsyncSession) -> Diagnosis:
        return await rounds.finalize_round(
            s, diagnosis_id=round_id, admin_id=1, actor=ACTOR
        )

    async def patch(s: AsyncSession) -> Diagnosis:
        return await rounds.patch_round(
            s, diagnosis_id=round_id, fields={"answers": ANSWERS_ALL_5}, actor=ACTOR
        )

    raced = await _race(factory, committing, finalize, patch)
    assert (raced.waited, raced.blocked) == (True, {"company"})
    assert isinstance(raced.first, Diagnosis), repr(raced.first)
    assert isinstance(raced.second, Conflict), repr(raced.second)
    async with factory() as s:
        row = await s.get(Diagnosis, round_id)
        assert row is not None
        assert (row.status, row.answers) == ("final", ANSWERS_MIXED)
    assert await _audits(factory, "diagnosis.update") == []
    assert len(await _audits(factory, "diagnosis.finalize")) == 1


async def test_diag_race_revoke_then_submit_410(
    factory: Factory, committing: AsyncEngine
) -> None:
    """회수 중인 링크로 제출하면 회사 잠금을 기다린 뒤 revoked 를 보고 410 — 회차가 생기지 않는다."""
    company_id, token = await _company_with_link(factory, "race-revoke")

    async def revoke(s: AsyncSession) -> tuple[DiagLink, bool]:
        return await links.revoke_link(s, token=token, actor=ACTOR)

    raced = await _race(factory, committing, revoke, _submit(token))
    assert (raced.waited, raced.blocked) == (True, {"company"})
    assert not isinstance(raced.first, BaseException), repr(raced.first)
    assert isinstance(raced.second, Gone), repr(raced.second)
    assert raced.second.extra == {"reason": "revoked"}
    assert await _count(factory, Diagnosis, Diagnosis.company_id == company_id) == 0
    gone = DiagLink.token == token, DiagLink.status == "revoked"
    assert await _count(factory, DiagLink, *gone) == 1
    assert await _audits(factory, "diag_link.submit") == []


async def test_diag_race_open_course_then_company_delete_409(
    factory: Factory, committing: AsyncEngine
) -> None:
    """개설 ③ 이 회사를 KEY SHARE 로 쥔 채 서 있으면 회사 삭제(FOR UPDATE)가 기다린 뒤 활성 연결 강의를 보고 409."""
    company_id, round_id = await _company_with_final(factory)
    raced = await _race(
        factory, committing, _open_from(round_id), _delete_company(company_id)
    )
    assert (raced.waited, raced.blocked) == (True, {"company"})
    assert isinstance(raced.first, Course), repr(raced.first)
    assert isinstance(raced.second, Conflict), repr(raced.second)
    assert raced.second.extra == {"active_courses": 1}
    assert await _count(factory, Company, Company.id == company_id) == 1
    assert await _count(factory, Diagnosis, Diagnosis.id == round_id) == 1
    linked = Course.id == raced.first.id, Course.company_id == company_id
    assert await _count(factory, Course, *linked) == 1
    assert await _audits(factory, "company.delete") == []


async def test_diag_race_company_delete_then_open_course_404(
    factory: Factory, committing: AsyncEngine
) -> None:
    """회사 삭제가 서 있으면 개설 ③ 의 hold_company 가 기다린 뒤 행이 없음을 보고 404 — 23503·500 이 아니다."""
    company_id, round_id = await _company_with_final(factory)
    raced = await _race(
        factory, committing, _delete_company(company_id), _open_from(round_id)
    )
    assert (raced.waited, raced.blocked) == (True, {"company"})
    assert raced.first is None
    assert isinstance(raced.second, NotFound), repr(raced.second)
    assert await _count(factory, Company, Company.id == company_id) == 0
    assert await _count(factory, Diagnosis, Diagnosis.id == round_id) == 0
    assert await _count(factory, Course) == 0
    assert await _count(factory, InviteCode) == 0
    assert await _audits(factory, "course.open") == []


async def test_diag_race_company_delete_waits_for_archived_course_write(
    factory: Factory, committing: AsyncEngine
) -> None:
    """보관 강의 K 를 고치는 쓰기(lock_course)가 서 있으면 회사 삭제는 회사를 잡고 활성 0 을 본 뒤 K 의 연결 풀기에서
    K 행을 기다리고, A 커밋 뒤 성공한다(company → course 한 방향 — 교착 없음, 결정 xi ⓐ)."""

    async def seed(s: AsyncSession) -> tuple[int, int]:
        company = await make_company(s)
        course, _ = await open_test_course(s, company_id=company.id)
        await crud_course.update_course(s, course, archived_at=dt.datetime.now(dt.UTC))
        return company.id, course.id

    company_id, course_id = await _seed(factory, seed)

    async def patch(s: AsyncSession) -> list[str]:
        course = await crud_course.get_course(s, course_id)
        assert course is not None
        return await days.patch_course(s, course, CoursePatchIn(intro="새 소개"))

    raced = await _race(factory, committing, patch, _delete_company(company_id))
    assert (raced.waited, raced.blocked) == (True, {"course"})
    _ok(raced)
    assert raced.first == ["intro"]
    assert await _count(factory, Company, Company.id == company_id) == 0
    async with factory() as s:
        row = await s.get(Course, course_id)
        assert row is not None
        assert (row.company_id, row.intro) == (None, "새 소개")
    assert await _audits(factory, "company.delete") == [
        {"rounds": 0, "links": 0, "unlinked_courses": 1}
    ]


async def test_diag_race_company_delete_two_courses_vs_template_delete(
    factory: Factory, committing: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """같은 회사에 연결된 보관 강의 K1 < K2 둘이 같은 설문 양식을 썼다. 양식 삭제(T8 — 양식 → 강의 id 오름차순 lock_course)가
    K1 만 잡은 순간 회사 삭제가 오면, 회사 삭제도 연결 강의를 id 오름차순으로 잡아야 K1 에서 기다리고(K2 를 쥐지 않는다)
    둘 다 끝난다. 일괄 UPDATE 가 물리 순서(K2 먼저)로 잠그면 K2 를 쥔 채 K1 을 기다려 40P01 이다(codex 1차 ③)."""

    async def seed(s: AsyncSession) -> tuple[int, int, int, int]:
        company = await make_company(s)
        k1, _ = await open_test_course(s, company_id=company.id, title="강의 1")
        k2, _ = await open_test_course(s, company_id=company.id, title="강의 2")
        assert k1.id < k2.id
        template = SurveyTemplate(name="양식 가", is_default=False, questions=[])
        s.add(template)
        await s.flush()
        for course in (k1, k2):
            s.add(
                Survey(
                    course_id=course.id,
                    template_id=template.id,
                    template_name=template.name,
                    questions=[],
                    open_on=TODAY,
                    close_on=TODAY,
                )
            )
        now = dt.datetime.now(dt.UTC)
        for course in (k1, k2):
            await crud_course.update_course(s, course, archived_at=now)
        # K1 의 색인 칸을 두 번 바꿔(HOT 아님) 산 튜플을 힙·색인 모두 K2 뒤로 보낸다 — 실행 계획 순서 = K2 먼저
        for value in (None, company.id):
            await s.execute(
                update(Course).where(Course.id == k1.id).values(company_id=value)
            )
        return company.id, template.id, k1.id, k2.id

    company_id, template_id, k1_id, k2_id = await _seed(factory, seed)
    held, release = _pause_after(monkeypatch, classfit.crud.course, "lock_course")

    async def delete_template(s: AsyncSession) -> None:
        await templates.delete_template(s, template_id=template_id, actor=ACTOR)

    raced = await _race_paused(
        factory,
        committing,
        held,
        release,
        delete_template,
        _delete_company(company_id),
    )
    assert (raced.waited, raced.blocked) == (True, {"course"})
    _ok(raced)  # 40P01 교착 · 55P03 없음
    assert await _count(factory, Company, Company.id == company_id) == 0
    assert await _count(factory, SurveyTemplate, SurveyTemplate.id == template_id) == 0
    unlinked = Course.id.in_([k1_id, k2_id]), Course.company_id.is_(None)
    assert await _count(factory, Course, *unlinked) == 2
    assert await _audits(factory, "company.delete") == [
        {"rounds": 0, "links": 0, "unlinked_courses": 2}
    ]


async def test_diag_race_company_delete_then_patch_404(
    factory: Factory, committing: AsyncEngine
) -> None:
    """회사 삭제가 회사 행을 쥔 채 서 있으면 회사 PATCH 는 lock_company 에서 기다린 뒤 행이 없음을 보고 404 —
    잠그지 않고 읽은 행을 flush 하면 UPDATE 0행 StaleDataError 500 이다(codex 1차 ④)."""

    async def seed(s: AsyncSession) -> int:
        return (await make_company(s)).id

    company_id = await _seed(factory, seed)

    async def patch(s: AsyncSession) -> Company:
        return await companies.patch_company(
            s, company_id=company_id, fields={"memo": "바뀐 메모"}, actor=ACTOR
        )

    raced = await _race(factory, committing, _delete_company(company_id), patch)
    assert (raced.waited, raced.blocked) == (True, {"company"})
    assert raced.first is None
    assert isinstance(raced.second, NotFound), repr(raced.second)
    assert await _count(factory, Company, Company.id == company_id) == 0
    assert await _audits(factory, "company.update") == []
