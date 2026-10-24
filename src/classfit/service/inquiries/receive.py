"""교육 문의 접수(T9b 결정 i·iv·v·vi·ix·x·xxiv). flush 까지만 — 커밋은 요청 트랜잭션이 한다.

판정 순서(결정 iv): 415 · 413 · 422 · 501 은 끝점 몫이고, 이 함수는 honeypot → 이메일 잠금 → 1분 재제출 → 하루 상한 →
넣기 + outbox 둘 이다.
- honeypot 이면 아무것도 쓰지 않고(행·outbox·audit 0) 새 난수 영수증과 트랜잭션 now() 를 돌려준다 — 정상 응답(행의
  created_at = 트랜잭션 now())과 모양·정밀도가 같다.
- 이메일 잠금(advisory, crud.inquiry.lock_email) 뒤에 읽는다. 같은 이메일 + 같은 내용(NULL 끼리도 같다)의 1분 안 행이 있으면
  그 행의 영수증을 그대로 돌려주고 쓰지 않는다. 재제출 판정이 하루 상한보다 먼저라 상한에 걸려도 같은 영수증이다.
- 같은 이메일의 24시간 접수가 daily_max 이상이면 TooManyRequests(429)이고 쓰지 않는다. honeypot 은 행이 없어 세지 않는다.
- 영수증이 겹치면(23505 → Conflict) 새 난수로 RECEIPT_TRIES 번까지 넣어 보고, 마지막도 겹치면 Conflict(409)를 그대로 던진다.
  실패한 SAVEPOINT 는 crud.flush.flush_or_conflict 안에서 되돌아가 요청 트랜잭션이 산다.
- outbox 두 행(확인 메일 → 문의자, 알림 → notify_to)의 params 는 {inquiry_id} 뿐이다 — 본문 글자를 넣지 않는다(결정 ix).
  보내지 않는다(ADR-003 결정 5). audit 은 남기지 않는다(결정 x — 관리자 처리가 아니다).
- 수신 주소 미구성(501)은 끝점이 설정으로 판정한다. 이 함수는 notify_to · daily_max 를 받기만 한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, TooManyRequests
from classfit.crud import inquiry as crud_inquiry
from classfit.crud import outbox as crud_outbox
from classfit.models import Inquiry
from classfit.service.rules import inquiry as rules_inquiry
from classfit.service.rules.inquiry import InquiryFields

MAIL_RECEIVED = (
    "inquiry_received"  # 접수 확인 → 문의자(본문은 영수증 번호와 고정 문구만)
)
MAIL_NOTIFY = "inquiry_notify"  # 알림 → INQUIRY_NOTIFY_TO(본문은 접수 칸 전부)
TOO_MANY = "이 이메일로는 하루에 보낼 수 있는 문의 수를 넘었습니다"


@dataclass(frozen=True)
class Receipt:
    """접수 결과. created 는 새 행을 넣었는가(시험·로그용) — 응답에 싣지 않는다(새 접수·재제출·honeypot 이 같은 모양)."""

    receipt_no: str
    received_at: datetime
    created: bool


async def receive_inquiry(
    session: AsyncSession,
    *,
    fields: InquiryFields,
    honeypot: bool,
    notify_to: str,
    daily_max: int,
) -> Receipt:
    if honeypot:
        received_at = await crud_inquiry.now(session)
        return Receipt(rules_inquiry.new_receipt_no(), received_at, created=False)
    await crud_inquiry.lock_email(session, fields.email)
    found = await crud_inquiry.find_recent_duplicate(
        session,
        email=fields.email,
        message=fields.message,
        window=rules_inquiry.DUPLICATE_WINDOW,
    )
    if found is not None:
        return Receipt(found.receipt_no, found.created_at, created=False)
    recent = await crud_inquiry.count_recent(
        session, email=fields.email, window=rules_inquiry.DAILY_WINDOW
    )
    if recent >= daily_max:
        raise TooManyRequests(TOO_MANY)
    row = await _insert(session, fields)
    await crud_outbox.enqueue(
        session, kind=MAIL_RECEIVED, params={"inquiry_id": row.id}, to=row.email
    )
    await crud_outbox.enqueue(
        session, kind=MAIL_NOTIFY, params={"inquiry_id": row.id}, to=notify_to
    )
    return Receipt(row.receipt_no, row.created_at, created=True)


async def _insert(session: AsyncSession, fields: InquiryFields) -> Inquiry:
    """새 난수 영수증으로 넣는다. 겹치면 다시 — 마지막 시도의 Conflict 는 그대로 나간다(409)."""
    for _ in range(rules_inquiry.RECEIPT_TRIES - 1):
        try:
            return await _insert_once(session, fields)
        except Conflict:
            continue
    return await _insert_once(session, fields)


async def _insert_once(session: AsyncSession, fields: InquiryFields) -> Inquiry:
    return await crud_inquiry.insert_inquiry(
        session, receipt_no=rules_inquiry.new_receipt_no(), values=asdict(fields)
    )
