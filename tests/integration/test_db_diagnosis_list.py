"""진단 회차 목록(T9b 결정 xxvii): list_stmt 의 범위·상태 · 키셋 순서 · 두 문장 사이 지워진 회차 건너뛰기. 라이브 PG.

회차는 T9a 픽스처의 crud 판(make_company · insert_round)으로 넣는다. 같은 트랜잭션의 created_at 은 같으니 순서를 재려고
행의 시각을 민다.
"""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import diagnosis as crud_diagnosis
from classfit.crud.page import keyset_page
from classfit.models import Diagnosis
from classfit.service.auth.sessions import Principal
from classfit.service.diagnosis.round_list import round_list
from tests.fixtures.diagnosis import insert_round, make_company

ADMIN = Principal("admin", 1)


async def _age(db: AsyncSession, row: Diagnosis, minutes: int) -> None:
    await db.execute(
        text(
            "UPDATE diagnosis SET created_at = created_at - make_interval(mins => :m)"
            " WHERE id = :id"
        ),
        {"m": minutes, "id": row.id},
    )
    await db.refresh(
        row
    )  # 커서는 행 객체의 created_at 으로 만든다 — 민 값으로 다시 읽는다


async def _ids(db: AsyncSession, subject: Any, status: str) -> list[int]:
    rows, _, _ = await keyset_page(
        db, crud_diagnosis.list_stmt(subject, status), None, 50
    )
    return [r.id for r in rows]


async def test_diagnosis_list_stmt_scope_and_status(db_session: AsyncSession) -> None:
    db = db_session
    a = await make_company(db, name="A사")
    b = await make_company(db, name="B사")
    a_draft = await insert_round(db, a.id, round_no=1, status="draft")
    a_review = await insert_round(db, a.id, round_no=2, status="review")
    a_final = await insert_round(db, a.id, round_no=3, status="final")
    b_review = await insert_round(db, b.id, round_no=1, status="review")
    b_draft = await insert_round(db, b.id, round_no=2, status="draft")
    # 받은 순서: a_review(30분 전) → b_review(10분 전) — 목록은 새로 받은 것부터
    await _age(db, a_review, 30)
    await _age(db, b_review, 10)
    await _age(db, a_draft, 5)

    assert await _ids(db, ADMIN, "review") == [b_review.id, a_review.id]
    assert set(await _ids(db, ADMIN, "draft")) == {a_draft.id, b_draft.id}
    assert await _ids(db, ADMIN, "draft") == [b_draft.id, a_draft.id]
    assert await _ids(db, ADMIN, "final") == [a_final.id]
    assert await _ids(db, ADMIN, "submitted") == []

    # 회사 범위는 관리자만 — 강사·수강생·그 밖 주체는 0행
    for subject in (
        Principal("instructor", 1),
        Principal("learner", 1, 1),
        Principal("other", 1),
    ):
        for status in ("draft", "review", "final"):
            assert await _ids(db, subject, status) == [], (subject, status)

    # 쪽 넘김: limit 1 로 끝까지 넘긴 합집합 == 전부
    seen: list[int] = []
    cursor = None
    for _ in range(5):  # 끝나지 않는 커서가 시험을 멈추지 않게 상한을 둔다
        items, cursor, more = await round_list(
            db, ADMIN, status="review", cursor=cursor, limit=1
        )
        seen += [i.id for i in items]
        if not more:
            break
    assert (seen, cursor) == ([b_review.id, a_review.id], None)
    (first, *_), _, _ = await round_list(
        db, ADMIN, status="review", cursor=None, limit=5
    )
    assert (first.company_id, first.company_name, first.round_no) == (b.id, "B사", 1)
    # 방문 회차: 응답자·제출 시각 없음 · 답 없으면 총점 0 · 17지표 전이라 레벨 없음
    assert (first.mode, first.respondent_name, first.submitted_at) == (
        "visit",
        None,
        None,
    )
    assert (first.total, first.level) == (0, None)


async def test_diagnosis_list_skips_vanished_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = db_session
    company = await make_company(db)
    rows = [
        await insert_round(db, company.id, round_no=n, status="review")
        for n in (1, 2, 3)
    ]
    for minutes, row in zip((30, 20, 10), rows, strict=True):
        await _age(db, row, minutes)
    whole, whole_cursor, whole_more = await round_list(
        db, ADMIN, status="review", cursor=None, limit=2
    )
    assert [i.id for i in whole] == [rows[2].id, rows[1].id]
    assert whole_more and whole_cursor is not None

    # 쪽을 읽은 뒤 그 회차가 지워지고 커밋된 것처럼 — 머리 문장이 그 id 를 돌려주지 않는다
    real = crud_diagnosis.list_heads
    vanished = rows[2].id

    async def without_vanished(
        session: AsyncSession, ids: Any
    ) -> dict[int, tuple[str, Any]]:
        heads = await real(session, ids)
        heads.pop(vanished, None)
        return heads

    monkeypatch.setattr(crud_diagnosis, "list_heads", without_vanished)
    items, next_cursor, has_more = await round_list(
        db, ADMIN, status="review", cursor=None, limit=2
    )
    assert [i.id for i in items] == [rows[1].id]  # 그 회차만 빠지고 KeyError 없음
    assert (next_cursor, has_more) == (whole_cursor, whole_more)
