"""교육 문의(0011, Design 부록 A T9b): 표 CHECK · 유일 · NULL · 접수 service(재제출 창 · 하루 상한 · 영수증 겹침) · outbox
렌더러 · 단일 진입. 라이브 PG.

alembic check 는 CHECK 를 비교하지 않으므로 CHECK 는 여기서 잰다. 행 id·영수증 글자 값은 단언하지 않는다(모양·동치만).
시험은 바깥 트랜잭션 하나라 now() 가 고정이다 — 창 안·밖은 age_inquiry 로 행의 접수 시각을 밀어 만든다.
단일 진입 시험은 src 와 scripts 에서 부르는 곳을 센다(정의 줄 제외, T2b test_enrollment_created_only_in_enter 꼴).
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from classfit.core.errors import Conflict, TooManyRequests
from classfit.database.session import make_session_factory
from classfit.models import Inquiry, MailOutbox
from classfit.service.inquiries import receive
from classfit.service.inquiries.receive import Receipt
from classfit.service.rules import inquiry as rules_inquiry
from scripts import outbox_preview
from tests.fixtures.inquiry import (
    INQUIRY_BODY,
    NORMALIZED_EMAIL,
    NOTIFY_TO,
    RECEIPT_RE,
    age_inquiry,
    fields,
    outbox_rows,
    submitted_values,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "classfit"
_DEFINITION = re.compile(r"^\s*(async\s+def|def|class)\s")
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"
DAILY_MAX = 20


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


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


async def _count(db: AsyncSession, *where: Any) -> int:
    return await db.scalar(select(func.count()).select_from(Inquiry).where(*where)) or 0


def _row(receipt_no: str, **over: Any) -> dict[str, Any]:
    return {
        "receipt_no": receipt_no,
        "company_name": "A사",
        "contact_name": "홍길동",
        "email": "contact.a@example.com",
        "phone": "010-0000-0000",
        "message": "교육 문의 본문입니다.",
        "privacy_agreed_at": func.now(),
        **over,
    }


async def test_inquiry_table_checks(db_session: AsyncSession) -> None:
    db = db_session
    table = Inquiry.__table__

    # 규모 4구간 밖 · 공백류뿐인 회사명·담당자·내용(스페이스·탭·줄바꿈)
    for name, change in (
        ("company_size", {"company_size": "10_49"}),
        ("company_name", {"company_name": " \t "}),
        ("contact_name", {"contact_name": "\n"}),
        ("message", {"message": " \n\t "}),
    ):
        await _violates(
            db,
            insert(table).values(**_row("CHECK00001", **change)),
            CHECK_VIOLATION,
            f"ck_inquiry_{name}",
        )
    # 연락처는 필수(NOT NULL) — 내용은 선택이다
    await _violates(
        db,
        insert(table).values(**_row("NULLPHONE1", phone=None)),
        NOT_NULL_VIOLATION,
    )
    assert await _count(db) == 0

    # 대조: 맞는 행 · 규모 코드 넷 · 내용 NULL 은 들어간다
    await db.execute(insert(table).values(**_row("RECEIPTAA2")))
    for n, size in enumerate(("under_30", "30_99", "100_299", "300_plus")):
        await db.execute(
            insert(table).values(
                **_row(f"SIZE0000{n}2", company_size=size, message=None)
            )
        )
    assert await _count(db, Inquiry.message.is_(None)) == 4
    # 같은 영수증 둘은 23505 — 같은 이메일 + 같은 내용 두 행은 들어간다(중복 판정은 service 몫, 결정 v)
    await _violates(
        db,
        insert(table).values(**_row("RECEIPTAA2", email="b@example.com")),
        UNIQUE_VIOLATION,
        "uq_inquiry_receipt_no",
    )
    await db.execute(insert(table).values(**_row("RECEIPTBB3")))
    same = (
        func.lower(Inquiry.email) == "contact.a@example.com",
        Inquiry.message == "교육 문의 본문입니다.",
    )
    assert await _count(db, *same) == 2
    assert await _count(db) == 6
    # 동의 시각·접수 시각은 트랜잭션 now() 다
    stamps = (
        await db.execute(
            select(Inquiry.privacy_agreed_at, Inquiry.created_at, func.now()).limit(1)
        )
    ).one()
    assert stamps[0] == stamps[1] == stamps[2]


# ── 접수 service(결정 iv·v·vi·xxiv)


async def _receive(
    db: AsyncSession,
    *,
    honeypot: bool = False,
    daily_max: int = DAILY_MAX,
    **over: Any,
) -> Receipt:
    return await receive.receive_inquiry(
        db,
        fields=fields(**over),
        honeypot=honeypot,
        notify_to=NOTIFY_TO,
        daily_max=daily_max,
    )


async def _outbox(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(MailOutbox)) or 0


async def _id_of(db: AsyncSession, receipt_no: str) -> int:
    found = await db.scalar(select(Inquiry.id).where(Inquiry.receipt_no == receipt_no))
    assert found is not None, receipt_no
    return found


async def test_inquiry_receive_dedupe_window(db_session: AsyncSession) -> None:
    db = db_session
    first = await _receive(db)
    assert first.created and re.fullmatch(RECEIPT_RE, first.receipt_no)
    assert (await _count(db), await _outbox(db)) == (1, 2)

    # 1분 안 · 같은 이메일(대문자도 같다) + 같은 내용 → 같은 영수증, 아무것도 쓰지 않는다
    again = await _receive(db, email=NORMALIZED_EMAIL.upper())
    assert (again.receipt_no, again.created) == (first.receipt_no, False)
    assert again.received_at == first.received_at
    assert (await _count(db), await _outbox(db)) == (1, 2)
    # 회사명·담당자가 달라도 이메일 + 내용이 같으면 재제출이다
    other_name = await _receive(db, company_name="B사", contact_name="김철수")
    assert other_name.receipt_no == first.receipt_no

    first_id = await _id_of(db, first.receipt_no)
    await age_inquiry(db, first_id, seconds=30)  # 창 안(30초 전)
    inside = await _receive(db)
    assert (inside.receipt_no, inside.created) == (first.receipt_no, False)
    assert (
        inside.received_at < first.received_at
    )  # 그 행의 접수 시각(밀린 값)을 다시 읽었다
    assert await _count(db) == 1

    await age_inquiry(db, first_id, seconds=90)  # 창 밖(120초 전)
    outside = await _receive(db)
    assert outside.created and outside.receipt_no != first.receipt_no
    assert (await _count(db), await _outbox(db)) == (2, 4)

    # 내용이 한 글자라도 다르면 새 문의다
    changed = await _receive(db, message=INQUIRY_BODY["message"] + ".")
    assert changed.created and changed.receipt_no != outside.receipt_no
    assert await _count(db) == 3

    # 내용 없는 둘은 같은 내용이다(IS NOT DISTINCT FROM — NULL 끼리 같다)
    empty = await _receive(db, message=None)
    empty_again = await _receive(db, message=None)
    assert empty.created and not empty_again.created
    assert empty_again.receipt_no == empty.receipt_no
    assert (await _count(db), await _outbox(db)) == (4, 8)

    # honeypot: 영수증 모양 · 시각 타입은 같고 쓰기 0
    bot = await _receive(db, honeypot=True, message="봇 본문")
    assert not bot.created and re.fullmatch(RECEIPT_RE, bot.receipt_no)
    assert isinstance(bot.received_at, datetime) and bot.received_at.tzinfo is not None
    assert bot.received_at == first.received_at  # 같은 트랜잭션 now()
    assert (await _count(db), await _outbox(db)) == (4, 8)
    assert await _count(db, Inquiry.receipt_no == bot.receipt_no) == 0


async def test_inquiry_receive_daily_limit_429(db_session: AsyncSession) -> None:
    db = db_session
    one = await _receive(db, daily_max=2, message="첫째 문의")
    two = await _receive(db, daily_max=2, message="둘째 문의")
    assert one.created and two.created
    with pytest.raises(TooManyRequests) as caught:
        await _receive(db, daily_max=2, message="셋째 문의")
    assert caught.value.kind == "too-many-requests"
    assert (await _count(db), await _outbox(db)) == (2, 4)

    # 1분 안 재제출은 상한보다 먼저 본다 — 같은 영수증
    again = await _receive(db, daily_max=2, message="첫째 문의")
    assert (again.receipt_no, again.created) == (one.receipt_no, False)
    # 다른 이메일은 따로 센다
    other = await _receive(db, daily_max=2, email="b@example.com", message="셋째 문의")
    assert other.created

    # honeypot 은 행이 없어 상한에 세지 않는다
    for _ in range(3):
        await _receive(db, daily_max=2, honeypot=True, message="봇 본문")
    # 하루(24시간) 밖으로 밀면 다시 받는다
    for receipt in (one, two):
        await age_inquiry(db, await _id_of(db, receipt.receipt_no), seconds=90_000)
    three = await _receive(db, daily_max=2, message="셋째 문의")
    four = await _receive(db, daily_max=2, message="넷째 문의")
    assert three.created and four.created
    with pytest.raises(TooManyRequests):
        await _receive(db, daily_max=2, message="다섯째 문의")
    assert await _count(db, func.lower(Inquiry.email) == NORMALIZED_EMAIL) == 4


async def test_inquiry_receipt_collision_retries_then_409(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = db_session
    taken = (await _receive(db, message="기존 문의")).receipt_no
    real = rules_inquiry.new_receipt_no
    calls: list[str] = []

    def collide_twice() -> str:
        value = taken if len(calls) < 2 else real()
        calls.append(value)
        return value

    monkeypatch.setattr(rules_inquiry, "new_receipt_no", collide_twice)
    fresh = await _receive(db, message="새 문의")
    assert fresh.created and fresh.receipt_no not in (taken,)
    assert len(calls) == 3
    assert (await _count(db), await _outbox(db)) == (2, 4)

    calls.clear()

    def always_taken() -> str:
        calls.append(taken)
        return taken

    monkeypatch.setattr(rules_inquiry, "new_receipt_no", always_taken)
    with pytest.raises(Conflict):
        await _receive(db, message="또 다른 문의")
    assert len(calls) == rules_inquiry.RECEIPT_TRIES == 3
    # 실패한 SAVEPOINT 만 되돌아가 세션이 산다 — 행·outbox 그대로
    assert (await _count(db), await _outbox(db)) == (2, 4)


async def test_inquiry_outbox_preview_renders(
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = db_session
    full = await _receive(db)
    bare = await _receive(
        db,
        email="b@example.com",
        dept_title=None,
        company_size=None,
        message=None,
    )
    full_id = await _id_of(db, full.receipt_no)

    assert await outbox_preview.run([], factory) == 0
    out = capsys.readouterr()
    messages = json.loads(out.out)["messages"]
    assert "롤백" in out.err and "--limit 200" in out.err
    by_kind: dict[tuple[str, str], str] = {}
    for m in messages:
        assert "code_status" not in m, m
        by_kind[(m["kind"], m["to"])] = m["body"]
    assert (
        set(by_kind)
        == {
            ("inquiry_received", NORMALIZED_EMAIL),
            ("inquiry_received", "b@example.com"),
            ("inquiry_notify", NOTIFY_TO),
        }
        and len(messages) == 4
    )

    # 확인 메일: 영수증 번호와 고정 문구만 — 제출한 글자는 하나도 없다(결정 ix)
    confirm = by_kind[("inquiry_received", NORMALIZED_EMAIL)]
    assert full.receipt_no in confirm
    assert confirm == outbox_preview.RECEIVED_BODY.format(receipt_no=full.receipt_no)
    for value in submitted_values(INQUIRY_BODY):
        assert value not in confirm, value
    assert bare.receipt_no in by_kind[("inquiry_received", "b@example.com")]

    # 알림: 칸 일곱 전부 · 규모 라벨 · 비어 있는 선택 칸은 (없음)
    notify = [m["body"] for m in messages if m["kind"] == "inquiry_notify"]
    full_notify = next(b for b in notify if NORMALIZED_EMAIL in b)
    for value in (
        INQUIRY_BODY["company_name"],
        INQUIRY_BODY["contact_name"],
        NORMALIZED_EMAIL,
        INQUIRY_BODY["phone"],
        INQUIRY_BODY["dept_title"],
        "30 ~ 99명",
        INQUIRY_BODY["message"],
    ):
        assert value in full_notify, value
    bare_notify = next(b for b in notify if "b@example.com" in b)
    assert "문의 내용: (없음)" in bare_notify
    assert "부서 · 직함: (없음)" in bare_notify and "임직원 규모: (없음)" in bare_notify
    assert all(sent is None for *_, sent in await outbox_rows(db))  # 미리 보기는 롤백

    # --limit: 앞(id 순) N 건만 · 0 은 인자 틀림
    assert await outbox_preview.run(["--limit", "1"], factory) == 0
    (only,) = json.loads(capsys.readouterr().out)["messages"]
    assert (only["kind"], only["to"]) == ("inquiry_received", NORMALIZED_EMAIL)
    for bad in ("0", "-1", "x"):
        assert await outbox_preview.run(["--limit", bad], factory) == 2
    capsys.readouterr()

    # params 모양이 틀리거나 문의 행이 없으면 3(전제 거절)
    first_outbox = await db.scalar(select(func.min(MailOutbox.id)))
    for params in ({}, {"inquiry_id": full_id + 1_000_000}):
        await db.execute(
            update(MailOutbox)
            .where(MailOutbox.id == first_outbox)
            .values(params=params)
        )
        assert await outbox_preview.run([], factory) == 3
        assert "전제 거절" in capsys.readouterr().err


# C1(NEL·CSI) · bidi(RLO·LRI) · DEL · 줄·문단 구분 · BMP 밖 서식 문자(U+E0001)를 한글 사이에 둔다
HOSTILE = "홍길\x85\x9b\u202e\u2066\x7f\u2028\u2029\U000e0001동"
HOSTILE_ESCAPES = (
    "\\u0085",
    "\\u009b",
    "\\u202e",
    "\\u2066",
    "\\u007f",
    "\\u2028",
    "\\u2029",
    "\\udb40\\udc01",  # 서로게이트 쌍 — 1 이면 다른 글자가 된다
)


async def test_outbox_preview_escapes_controls(
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = db_session
    await _receive(db, contact_name=HOSTILE, message=f"첫 줄\n{HOSTILE}")
    # 다른 kind · to 칸도 같은 출력 자리를 지난다(이미 저장된 행)
    to = "learner\u202e@example.com"
    opened = {
        "survey_id": 1,
        "course_title": HOSTILE,
        "open_on": "2026-11-02",
        "close_on": "2026-11-05",
    }
    db.add(MailOutbox(kind="survey_opened", params=opened, to=to))
    await db.flush()

    assert await outbox_preview.run([], factory) == 0
    out = capsys.readouterr().out
    # 줄을 끊는 print 의 줄바꿈 말고는 Cc·Cf·Zl·Zp·Cs 글자가 하나도 없다
    assert out.endswith("\n")
    line = out[:-1]
    categories = outbox_preview.ESCAPED_CATEGORIES
    assert [ch for ch in line if unicodedata.category(ch) in categories] == []
    for escaped in HOSTILE_ESCAPES:
        assert escaped in line, escaped
    assert "홍길" in line  # 한글은 날 글자 그대로

    # json.loads 하면 원문 그대로 · json.dumps 가 만든 \n 이스케이프도 그대로
    messages = json.loads(line)["messages"]
    by_kind = {m["kind"]: m for m in messages}
    notify = by_kind["inquiry_notify"]["body"]
    assert f"담당자: {HOSTILE}\n" in notify
    assert f"문의 내용:\n첫 줄\n{HOSTILE}" in notify
    assert HOSTILE in by_kind["survey_opened"]["body"]
    assert by_kind["survey_opened"]["to"] == to
    assert line.count("\\n") == sum(m["body"].count("\n") for m in messages)
    assert "\\u000a" not in line


def _callers(pattern: str) -> list[str]:
    """부르는 파일(src/classfit 기준 상대 경로, scripts 는 scripts/ 로) — 정의 줄은 세지 않는다."""
    rx = re.compile(pattern)
    found = []
    for base, root in ((SRC, SRC), (ROOT / "scripts", ROOT)):
        for path in sorted(base.rglob("*.py")):
            lines = path.read_text(encoding="utf-8").splitlines()
            if any(rx.search(line) for line in lines if not _DEFINITION.match(line)):
                found.append(path.relative_to(root).as_posix())
    return found


def test_inquiry_created_only_in_receive() -> None:
    # 넣기는 service/inquiries/receive.py 하나, 생성자는 crud/inquiry.py 하나, 지우기는 scripts/inquiry_gc.py 하나(결정 xi)
    assert _callers(r"\binsert_inquiry\(") == ["service/inquiries/receive.py"]
    assert _callers(r"\bInquiry\(") == ["crud/inquiry.py"]
    assert _callers(r"\bdelete_inquiries\(") == ["scripts/inquiry_gc.py"]
