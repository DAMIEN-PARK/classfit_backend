"""교육 문의 표(0011, Design 부록 A T9b): CHECK · 유일 · NULL. 라이브 PG.

alembic check 는 CHECK 를 비교하지 않으므로 CHECK 는 여기서 잰다. 행 id·영수증 글자 값은 단언하지 않는다(모양·동치만).
"""

from typing import Any

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import Inquiry

CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
UNIQUE_VIOLATION = "23505"


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
