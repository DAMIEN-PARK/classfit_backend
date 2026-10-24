"""inquiry(교육 문의) 읽기·쓰기·잠금(T9b 결정 v·vi·xxiv·xxv). flush 까지만.

- lock_email 은 같은 이메일(소문자)의 접수를 트랜잭션 끝까지 줄 세우는 advisory 잠금이다(T1 lock_attempt_key 꼴, 키
  "inquiry|<소문자 이메일>"). 행 잠금이 아니라 다른 경로의 행 잠금 순서와 만나지 않는다(문의는 어느 표도 참조하지 않는다).
  재제출 조회 → 하루 상한 셈 → 넣기는 이 잠금 뒤에 한다(동시 둘은 뒤엣것이 앞엣것의 커밋을 보고 같은 영수증을 받는다).
- 창 비교는 SQL now() 기준이다(created_at >= now() - window). 시험 트랜잭션은 now() 가 고정이라 시험이 행의 시각을 민다.
- 넣기 insert_inquiry 는 service.inquiries.receive 의 receive_inquiry() 만 부른다(단일 진입). 영수증 유일 위반만 Conflict.
- 지우기 delete_inquiries 는 scripts.inquiry_gc 만 부른다. 대상 문의 행과 그 outbox 행(kind inquiry_* · params inquiry_id)을
  id 오름차순으로 잡은 뒤 지운다 — outbox_preview --apply 가 안 보낸 행을 id 순으로 하나씩 잡으므로 같은 순서다(교착 없음).
  mail_outbox 에 FK 가 없어 outbox 행을 남기면 매달린 참조가 된다(outbox_preview 가 3 으로 멈춘다).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.flush import flush_or_conflict
from classfit.models import Inquiry, MailOutbox

RECEIPT_TAKEN = "영수증 번호가 겹쳤습니다"
OUTBOX_KIND_PREFIX = (
    "inquiry_"  # inquiry_received · inquiry_notify(service.inquiries.receive)
)


async def lock_email(session: AsyncSession, email: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"inquiry|{email.lower()}"},
    )


def _same_email(email: str) -> ColumnElement[bool]:
    # 식 색인 ix_inquiry_email_lower_created_at 을 타게 lower(email) 로 비교한다
    return func.lower(Inquiry.email) == email.lower()


def _within(window: timedelta) -> ColumnElement[bool]:
    return Inquiry.created_at >= func.now() - window


async def find_recent_duplicate(
    session: AsyncSession, *, email: str, message: str | None, window: timedelta
) -> Inquiry | None:
    """창 안의 같은 이메일 + 같은 내용(NULL 끼리도 같다) 가운데 가장 최근 행. 없으면 None.

    잠근 뒤 읽는 자리라 populate_existing 이다(identity map 의 옛 created_at 이 응답 시각을 가리지 않게).
    """
    stmt = (
        select(Inquiry)
        .where(
            _same_email(email),
            Inquiry.message.is_not_distinct_from(message),
            _within(window),
        )
        .order_by(Inquiry.created_at.desc(), Inquiry.id.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def count_recent(session: AsyncSession, *, email: str, window: timedelta) -> int:
    """창 안의 같은 이메일 접수 수(이메일당 하루 상한, 결정 xxiv)."""
    stmt = (
        select(func.count())
        .select_from(Inquiry)
        .where(_same_email(email), _within(window))
    )
    return int(await session.scalar(stmt) or 0)


async def insert_inquiry(
    session: AsyncSession, *, receipt_no: str, values: Mapping[str, Any]
) -> Inquiry:
    """문의 한 행(동의 시각 = 트랜잭션 now()). 영수증이 겹치면 Conflict — 실패한 SAVEPOINT 는 되돌아가 세션이 산다."""
    row = Inquiry(receipt_no=receipt_no, privacy_agreed_at=func.now(), **values)
    await flush_or_conflict(session, RECEIPT_TAKEN, row)
    await session.refresh(row)
    return row


async def get_inquiry(session: AsyncSession, inquiry_id: int) -> Inquiry | None:
    return await session.get(Inquiry, inquiry_id)


async def now(session: AsyncSession) -> datetime:
    """트랜잭션 now() — honeypot 응답 시각이 정상 응답(행의 created_at)과 같은 정밀도가 되게."""
    value = await session.scalar(select(func.now()))
    if value is None:
        raise RuntimeError("now() 가 비었다")
    return value


async def select_for_gc(
    session: AsyncSession,
    *,
    receipt_no: str | None = None,
    email: str | None = None,
    older_than: timedelta | None = None,
) -> list[Inquiry]:
    """선택자 셋 중 하나로 고른 문의 행, id 순으로 잡는다(FOR UPDATE). 선택자가 하나가 아니면 ValueError."""
    chosen = [s for s in (receipt_no, email, older_than) if s is not None]
    if len(chosen) != 1:
        raise ValueError("선택자는 receipt_no · email · older_than 중 하나다")
    stmt = select(Inquiry)
    if receipt_no is not None:
        stmt = stmt.where(Inquiry.receipt_no == receipt_no)
    elif email is not None:
        stmt = stmt.where(_same_email(email))
    else:
        assert older_than is not None
        stmt = stmt.where(Inquiry.created_at < func.now() - older_than)
    stmt = (
        stmt.order_by(Inquiry.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def delete_inquiries(
    session: AsyncSession, ids: Collection[int]
) -> tuple[int, int]:
    """(지운 outbox 수, 지운 문의 수). 그 문의의 outbox 행을 id 순으로 잡고 먼저 지운 뒤 문의 행을 지운다."""
    wanted = list(ids)
    if not wanted:
        return 0, 0
    of_these = MailOutbox.params["inquiry_id"].astext.in_([str(i) for i in wanted])
    outbox_ids = list(
        (
            await session.scalars(
                select(MailOutbox.id)
                .where(
                    MailOutbox.kind.startswith(OUTBOX_KIND_PREFIX, autoescape=True),
                    of_these,
                )
                .order_by(MailOutbox.id)
                .with_for_update()
            )
        ).all()
    )
    outbox_deleted = 0
    if outbox_ids:
        gone = await session.execute(
            delete(MailOutbox)
            .where(MailOutbox.id.in_(outbox_ids))
            .returning(MailOutbox.id)
        )
        outbox_deleted = len(gone.scalars().all())
    deleted = await session.execute(
        delete(Inquiry).where(Inquiry.id.in_(wanted)).returning(Inquiry.id)
    )
    return outbox_deleted, len(deleted.scalars().all())
