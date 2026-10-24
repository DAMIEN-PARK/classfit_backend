"""company(회사) 읽기·쓰기·잠금과 회차 요약(T9a 결정 iii·xi·xxiv). flush 까지만.

- 잠금 꼴 셋(이 파일의 with_for_update 는 이 셋뿐이다): 진단 쪽 쓰기(링크·회차·회사 고치기·지우기)는 lock_company(FOR UPDATE
  + populate_existing) 뒤 대상을 다시 읽고 쓴다. 강의 개설(회사 연결 · 시작점 ③)은 hold_company(FOR KEY SHARE)로 회사를
  잡은 뒤 새 course 를 넣는다 — KEY SHARE 끼리는 충돌하지 않아 같은 회사의 동시 개설은 줄 서지 않고, 회사 삭제의
  FOR UPDATE 와는 줄 선다. company 는 T5 잠금 순서의 참조 행 층(①′)이다. 회사 삭제는 연결 강의 행을
  lock_linked_courses(id 오름차순 FOR UPDATE)로 잡는다.
- 회사 삭제는 회사 행 → 연결 강의 행(id 오름차순) → 연결 풀기 UPDATE → 회사 DELETE 순이다. 강의 행을 일괄 UPDATE 가 실행
  계획 순서로 잡으면 강의를 id 오름차순으로 잡는 다른 경로(T8 양식 삭제 · 설문 배포)와 엇갈려 교착하므로(codex 구현 리뷰
  1차 ③) 먼저 오름차순으로 잠근다. 그 잠금은 강의 행 잠금(lock_course 보유자)을 기다릴 수 있다 — company → course 한
  방향이다. 연결 수가 audit 의 unlinked_courses 이고, 회차·링크는 FK CASCADE 로 같이 지워진다. 활성 연결 강의
  검사(409)는 service 몫이다.
- 목록 list_stmt 의 첫 WHERE 는 주체 범위 company_scope(관리자 전부)다.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud.like import LIKE_ESCAPE, contains_pattern
from classfit.crud.scope import Subject, company_scope
from classfit.models import Company, Course, Diagnosis


async def insert_company(session: AsyncSession, **fields: Any) -> Company:
    row = Company(**fields)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_company(session: AsyncSession, company_id: int) -> Company | None:
    """범위 없는 getter(404 판정용)."""
    return await session.scalar(select(Company).where(Company.id == company_id))


async def lock_company(session: AsyncSession, company_id: int) -> Company | None:
    """회사 행을 SELECT … FOR UPDATE 로 잠그고 새로 읽는다. 없으면(그 사이 지워졌으면) None.

    링크 발급·회수·제출, 회차 생성·수정·확정·삭제, 회사 삭제가 이 행 하나로 줄 선다(결정 xi).
    populate_existing: 잠금을 기다린 사이 커밋된 값을 identity map 의 옛 값이 가리지 않게 덮어 읽는다.
    """
    stmt = (
        select(Company)
        .where(Company.id == company_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def hold_company(session: AsyncSession, company_id: int) -> bool:
    """회사 행을 FOR KEY SHARE 로 잡는다(강의 개설의 회사 연결 확인). 없으면 False(→ 404)."""
    stmt = (
        select(Company.id)
        .where(Company.id == company_id)
        .with_for_update(read=True, key_share=True)
    )
    return await session.scalar(stmt) is not None


async def lock_linked_courses(session: AsyncSession, company_id: int) -> list[int]:
    """그 회사에 연결된 강의 행을 id 오름차순 FOR UPDATE 로 잡고 그 id 를 돌려준다(회사 삭제 — lock_company 뒤).

    LockRows 가 정렬 뒤에 있어 잡는 차례가 id 오름차순이다(T8 crud.survey_template.course_ids_using 순서와 같다).
    그 사이 지워진 강의는 PG 가 돌려주지 않는다.
    """
    stmt = (
        select(Course.id)
        .where(Course.company_id == company_id)
        .order_by(Course.id)
        .with_for_update()
    )
    return list((await session.scalars(stmt)).all())


async def update_company(session: AsyncSession, row: Company, **fields: Any) -> Company:
    """칸을 바꾸고 flush 한 뒤 다시 읽는다(updated_at 이 만료된다)."""
    for name, value in fields.items():
        setattr(row, name, value)
    await session.flush()
    await session.refresh(row)
    return row


async def delete_company(session: AsyncSession, company_id: int) -> tuple[bool, int]:
    """(지웠는가, 연결을 푼 강의 수). lock_company · lock_linked_courses 로 회사와 연결 강의를 잡은 뒤에 부른다.

    강의 연결을 먼저 명시적으로 푼다 — FK SET NULL 의 암묵 UPDATE 와 같은 행이고(이미 잡아 기다리지 않는다) 그 수를 audit
    이 쓴다. 원시 UPDATE 라 updated_at 을 직접 넣는다.
    """
    unlinked = await session.scalars(
        update(Course)
        .where(Course.company_id == company_id)
        .values(company_id=None, updated_at=func.now())
        .returning(Course.id)
    )
    count = len(unlinked.all())
    deleted = await session.execute(
        delete(Company).where(Company.id == company_id).returning(Company.id)
    )
    return deleted.scalar_one_or_none() is not None, count


def list_stmt(subject: Subject, q: str | None) -> Select[tuple[Company]]:
    """회사 목록. 첫 WHERE 는 주체 범위다. q 는 이름·담당자·업종 부분 일치(와일드카드는 글자로)."""
    stmt = select(Company).where(company_scope(subject))
    if q:
        pattern = contains_pattern(q)
        stmt = stmt.where(
            or_(
                Company.name.ilike(pattern, escape=LIKE_ESCAPE),
                Company.contact.ilike(pattern, escape=LIKE_ESCAPE),
                Company.industry.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    return stmt


async def _latest_rounds(
    session: AsyncSession, company_ids: list[int], *, final_only: bool
) -> dict[int, Diagnosis]:
    stmt = (
        select(Diagnosis)
        .where(Diagnosis.company_id.in_(company_ids))
        .distinct(Diagnosis.company_id)
        .order_by(Diagnosis.company_id, Diagnosis.round_no.desc())
    )
    if final_only:
        stmt = stmt.where(Diagnosis.status == "final")
    return {row.company_id: row for row in (await session.scalars(stmt)).all()}


async def round_summaries(
    session: AsyncSession, company_ids: Collection[int]
) -> tuple[dict[int, Diagnosis], dict[int, Diagnosis]]:
    """(회사 id → round_no 최대 회차, 회사 id → final 가운데 round_no 최대 회차). 회차 없는 회사는 빠진다.

    목록·상세와 다른 문장이라 그 사이 지워진 회사·회차는 그냥 빠진다 — 쓰는 쪽은 .get 으로 꺼낸다.
    """
    wanted = sorted(set(company_ids))
    if not wanted:
        return {}, {}
    last = await _latest_rounds(session, wanted, final_only=False)
    final = await _latest_rounds(session, wanted, final_only=True)
    return last, final


async def active_course_count(session: AsyncSession, company_id: int) -> int:
    """그 회사에 연결된 보관하지 않은 강의 수(회사 삭제 409 판정, 결정 iii)."""
    stmt = (
        select(func.count())
        .select_from(Course)
        .where(Course.company_id == company_id, Course.archived_at.is_(None))
    )
    return await session.scalar(stmt) or 0


async def linked_courses(
    session: AsyncSession, company_id: int
) -> list[tuple[int, str]]:
    """그 회사에 연결된 강의 (id, 제목) — 보관 포함, id 순."""
    stmt = (
        select(Course.id, Course.title)
        .where(Course.company_id == company_id)
        .order_by(Course.id)
    )
    return [(row.id, row.title) for row in (await session.execute(stmt)).all()]
