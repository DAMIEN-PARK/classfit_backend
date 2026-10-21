"""crud/page.py 의 키셋 페이지. 라이브 PG, 행은 기존 표(mail_outbox)에 직접 넣는다."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.cursor import decode_cursor
from classfit.crud.page import keyset_page
from classfit.models import MailOutbox


async def test_keyset_page_has_more_and_next_cursor(db_session: AsyncSession) -> None:
    base = datetime(2026, 10, 22, 0, 0, tzinfo=UTC)
    # 같은 시각 둘(id 로 갈린다) + 범위 밖 kind 하나(stmt 의 WHERE 가 그대로 남는지)
    offsets = [0, 1, 1, 2, 3]
    rows = [
        MailOutbox(
            kind="probe",
            params={},
            to="a@example.com",
            created_at=base + timedelta(minutes=m),
        )
        for m in offsets
    ]
    other = MailOutbox(
        kind="other",
        params={},
        to="b@example.com",
        created_at=base + timedelta(minutes=9),
    )
    db_session.add_all([*rows, other])
    await db_session.flush()
    expected = [
        r.id for r in sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)
    ]

    stmt = select(MailOutbox).where(MailOutbox.kind == "probe")
    seen: list[int] = []
    pages: list[tuple[int, bool]] = []
    cursor: str | None = None
    while True:
        items, cursor, has_more = await keyset_page(db_session, stmt, cursor, 2)
        seen += [r.id for r in items]
        pages.append((len(items), has_more))
        if not has_more:
            assert cursor is None
            break
        assert cursor is not None
        assert decode_cursor(cursor) == (items[-1].created_at, items[-1].id)

    assert pages == [(2, True), (2, True), (1, False)]
    assert seen == expected  # (created_at, id) 내림차순, 빠짐·겹침 없음
    assert other.id not in seen

    # 딱 맞으면 다음 쪽 없음
    items, cursor, has_more = await keyset_page(db_session, stmt, None, 5)
    assert (len(items), cursor, has_more) == (5, None, False)
