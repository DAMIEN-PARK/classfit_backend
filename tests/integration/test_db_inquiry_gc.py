"""문의 삭제 관리 명령 scripts.inquiry_gc(T9b 결정 xxv): 미리 보기는 지운 뒤 되돌리고, --apply 만 문의와 그 outbox 를 지운다.

라이브 PG, 시험 연결에 묶은 session_factory 를 넘긴다(T1 test_db_admin_commands 꼴). 시험 이름에 gc_ 를 쓰지 않는다
(규약 이름 셈 E-14 와 겹치지 않게 — 계획 확인값 칸).
바인드 상한 시험(T11 결정 viii)은 문의·outbox 를 generate_series 로 한 문장씩 넣고, 실제로 보낸 문장의 매개변수를 엔진
before_cursor_execute 이벤트로 본다.
"""

import json
from typing import Any

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from classfit.database.session import make_session_factory
from classfit.models import EmailVerification, Inquiry, MailOutbox
from classfit.service.inquiries import receive
from classfit.service.inquiries.receive import Receipt
from scripts import inquiry_gc, outbox_preview
from tests.fixtures.inquiry import NORMALIZED_EMAIL, NOTIFY_TO, age_inquiry, fields

OTHER_EMAIL = "b@example.com"


@pytest.fixture
def factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(db_connection, join_transaction_mode="create_savepoint")


async def _receive(db: AsyncSession, **over: Any) -> Receipt:
    receipt = await receive.receive_inquiry(
        db, fields=fields(**over), honeypot=False, notify_to=NOTIFY_TO, daily_max=20
    )
    assert receipt.created
    return receipt


async def _seed(db: AsyncSession) -> list[Receipt]:
    """문의 셋(이메일 둘) + 그 outbox 6 + 인증 코드 outbox 1(T3 꼴 — 문의와 무관한 행)."""
    receipts = [
        await _receive(db, message="첫째 문의"),
        await _receive(db, message="둘째 문의"),
        await _receive(db, email=OTHER_EMAIL, message="셋째 문의"),
    ]
    verification = EmailVerification(email="code@example.com")
    db.add(verification)
    await db.flush()
    db.add(
        MailOutbox(
            kind="email_code",
            params={"verification_id": verification.id},
            to="code@example.com",
        )
    )
    await db.flush()
    return receipts


async def _counts(db: AsyncSession) -> tuple[int, int, int]:
    """(문의 행, 문의 outbox 행, 그 밖 outbox 행)."""
    inquiries = await db.scalar(select(func.count()).select_from(Inquiry)) or 0
    of_inquiry = MailOutbox.kind.startswith("inquiry_")
    outbox = await db.scalar(select(func.count()).where(of_inquiry)) or 0
    others = await db.scalar(select(func.count()).where(~of_inquiry)) or 0
    return inquiries, outbox, others


async def test_inquiry_delete_preview_changes_nothing(
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = db_session
    first, *_ = await _seed(db)
    assert await _counts(db) == (3, 6, 1)

    # 미리 보기: 같은 경로로 실제로 지운 뒤 되돌린다 — 수치는 apply 와 같고 행은 그대로
    assert await inquiry_gc.run(["--receipt", first.receipt_no.lower()], factory) == 0
    out = capsys.readouterr()
    result = json.loads(out.out)
    assert result["applied"] is False
    assert result["selector"] == {"receipt": first.receipt_no}
    assert [s["receipt_no"] for s in result["selected"]] == [first.receipt_no]
    assert set(result["selected"][0]) == {"id", "receipt_no", "created_at"}
    assert (result["deleted"], result["outbox_deleted"]) == (1, 2)
    assert "되돌렸다" in out.err
    assert await _counts(db) == (3, 6, 1)

    # 선택자는 셋 중 정확히 하나 · 값 모양이 틀리면 2(인자 틀림)
    for argv in (
        [],
        ["--apply"],
        ["--receipt", first.receipt_no, "--email", NORMALIZED_EMAIL],
        ["--older-than-days", "0"],
        ["--older-than-days", "36501"],  # 날짜 넘침 전에 막는다(MAX_DAYS)
        ["--older-than-days", "10000000000"],
        ["--older-than-days", "x"],
        ["--email", "  "],
    ):
        assert await inquiry_gc.run(argv, factory) == 2, argv
    capsys.readouterr()
    assert await _counts(db) == (3, 6, 1)


async def test_inquiry_delete_apply_removes_inquiry_and_outbox(
    db_session: AsyncSession,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = db_session
    *_, other = await _seed(db)

    # 이메일 선택자는 앞뒤 공백·대소문자를 무시한다 — 그 이메일 문의 둘과 outbox 넷만 지운다
    argv = ["--email", " Contact.A@Example.com ", "--apply"]
    assert await inquiry_gc.run(argv, factory) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["applied"] is True
    assert result["selector"] == {"email": NORMALIZED_EMAIL}
    assert (len(result["selected"]), result["deleted"], result["outbox_deleted"]) == (
        2,
        2,
        4,
    )
    assert await _counts(db) == (1, 2, 1)
    left = await db.scalars(select(Inquiry.receipt_no))
    assert list(left) == [other.receipt_no]
    # 매달린 outbox 가 없어 미리 보기가 끝까지 돈다
    assert await outbox_preview.run([], factory) == 0
    capsys.readouterr()

    # 보유 만료: 접수 뒤 N 일이 지난 것만
    other_id = await db.scalar(select(Inquiry.id))
    assert other_id is not None
    assert await inquiry_gc.run(["--older-than-days", "1"], factory) == 0
    assert json.loads(capsys.readouterr().out)["selected"] == []
    await age_inquiry(db, other_id, seconds=2 * 86_400)
    assert await inquiry_gc.run(["--older-than-days", "1", "--apply"], factory) == 0
    result = json.loads(capsys.readouterr().out)
    assert (result["deleted"], result["outbox_deleted"]) == (1, 2)
    assert await _counts(db) == (0, 0, 1)  # 인증 코드 outbox 는 그대로

    # 상한 36500일(100년)은 받는다 — PG 범위 오류 없이 0건
    assert await inquiry_gc.run(["--older-than-days", "36500"], factory) == 0
    assert json.loads(capsys.readouterr().out)["selected"] == []

    # 값 없이 쓰면 365일
    assert await inquiry_gc.run(["--older-than-days"], factory) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["selector"] == {"older_than_days": 365}
    assert result["selected"] == [] and result["applied"] is False


# outbox 가 2N = 65,536 — id 마다 바인드면 PG 바인드 상한 65,535 를 넘는다
BULK_INQUIRIES = 32_768
BULK_SEED = (
    "INSERT INTO inquiry (receipt_no, company_name, contact_name, email, phone,"
    " privacy_agreed_at, created_at)"
    " SELECT 'BULK' || lpad(g::text, 6, '0'), 'A사', '홍길동', 'bulk@example.com',"
    " '010-0000-0000', now(), now() - interval '400 days'"
    " FROM generate_series(1, :n) AS g"
)
BULK_OUTBOX = (
    'INSERT INTO mail_outbox (kind, params, "to")'
    " SELECT CASE k WHEN 1 THEN 'inquiry_received' ELSE 'inquiry_notify' END,"
    " jsonb_build_object('inquiry_id', i.id), 'bulk@example.com'"
    " FROM inquiry AS i CROSS JOIN generate_series(1, 2) AS k"
    " WHERE i.receipt_no LIKE 'BULK%'"
)


async def test_inquiry_delete_beyond_bind_limit(
    db_session: AsyncSession,
    db_connection: AsyncConnection,
    factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = db_session
    await db.execute(text(BULK_SEED), {"n": BULK_INQUIRIES})
    await db.execute(text(BULK_OUTBOX))
    bulk_id = await db.scalar(select(func.min(Inquiry.id)))
    # cutoff 안쪽 문의(그 outbox 2) · kind 가 다른 outbox(inquiry_id 가 같아도 남는다)
    await _receive(db, message="최근 문의")
    db.add(
        MailOutbox(
            kind="survey_closed", params={"inquiry_id": bulk_id}, to="x@example.com"
        )
    )
    await db.flush()
    n = BULK_INQUIRIES
    assert await _counts(db) == (n + 1, 2 * n + 2, 1)

    sent: list[tuple[str, dict[str, Any]]] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, *_: Any
    ) -> None:
        sent.append((statement, parameters))

    engine = db_connection.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        argv = ["--older-than-days", "365", "--apply"]
        assert await inquiry_gc.run(argv, factory) == 0
    finally:
        event.remove(engine, "before_cursor_execute", record)
    result = json.loads(capsys.readouterr().out)
    assert (len(result["selected"]), result["deleted"], result["outbox_deleted"]) == (
        n,
        n,
        2 * n,
    )
    assert await _counts(db) == (1, 2, 1)

    # 세 문장 모두 id 배열 바인드가 하나다 — 매개변수 수가 N 과 상관없다
    def bound(prefix: str) -> dict[str, Any]:
        (params,) = [p for s, p in sent if s.lstrip().startswith(prefix)]
        arrays = [v for v in params.values() if isinstance(v, list)]
        assert len(arrays) == 1, (prefix, len(arrays))
        return params

    found = dict(bound("SELECT mail_outbox.id"))
    ids = found.pop(next(k for k, v in found.items() if isinstance(v, list)))
    assert len(ids) == n
    # 남는 것은 kind 앞글자와 JSON 키(inquiry_id) 둘
    assert len(found) == 2 and "inquiry_id" in found.values(), found
    for prefix, size in (
        ("DELETE FROM mail_outbox", 2 * n),
        ("DELETE FROM inquiry", n),
    ):
        (only,) = bound(prefix).values()
        assert len(only) == size, prefix
