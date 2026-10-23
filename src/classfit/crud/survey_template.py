"""survey_template(설문 양식) 읽기·쓰기·잠금(T8 결정 viii·xix). flush 까지만.

- 잠금 셋: 배포는 양식 행 FOR KEY SHARE(lock_template_shared — 배포끼리는 막지 않고 삭제·FOR UPDATE 와 줄 선다), 삭제·수정은
  FOR UPDATE(lock_template), 기본 지정은 옛 기본·새 대상 두 행을 id 오름차순 FOR UPDATE(lock_templates). 셋 다
  populate_existing 으로 기다린 사이 커밋된 값을 덮어 읽는다. 이 파일의 with_for_update 는 그 셋이다.
  잠금 꼴은 crud/materials.py 와 같다: FOR KEY SHARE 는 read 와 key_share 를 함께 준다(key_share 만 주면 FOR NO KEY UPDATE).
- 잠금 순서는 template → course → survey → survey_response 의 한 방향이다(결정 xix).
- 목록은 전부를 이름 → id 순으로(수십 개 — 커서 없음). 기본 양식은 부분 유일 색인이 많아야 하나로 지킨다.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.models import Survey, SurveyTemplate


async def insert_template(
    session: AsyncSession,
    *,
    name: str,
    note: str | None,
    is_default: bool,
    questions: list[dict[str, Any]],
) -> SurveyTemplate:
    row = SurveyTemplate(
        name=name, note=note, is_default=is_default, questions=questions
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_template(
    session: AsyncSession, template_id: int, *, fresh: bool = False
) -> SurveyTemplate | None:
    """범위 없는 getter(관리자만 쓴다). fresh 는 잠근 뒤 다시 읽을 때(populate_existing)."""
    stmt = select(SurveyTemplate).where(SurveyTemplate.id == template_id)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def lock_template_shared(
    session: AsyncSession, template_id: int
) -> SurveyTemplate | None:
    """배포: 양식 행 FOR KEY SHARE. 없으면(그 사이 지워졌으면) None."""
    stmt = (
        select(SurveyTemplate)
        .where(SurveyTemplate.id == template_id)
        .with_for_update(read=True, key_share=True)
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def lock_template(
    session: AsyncSession, template_id: int
) -> SurveyTemplate | None:
    """삭제·수정: 양식 행 FOR UPDATE. 없으면 None."""
    stmt = (
        select(SurveyTemplate)
        .where(SurveyTemplate.id == template_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def lock_templates(
    session: AsyncSession, ids: Collection[int]
) -> list[SurveyTemplate]:
    """기본 지정: 준 양식 행들을 id 오름차순 FOR UPDATE. 없는 id 는 빠진다."""
    stmt = (
        select(SurveyTemplate)
        .where(SurveyTemplate.id.in_(sorted(set(ids))))
        .order_by(SurveyTemplate.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def list_templates(session: AsyncSession) -> list[SurveyTemplate]:
    stmt = select(SurveyTemplate).order_by(SurveyTemplate.name, SurveyTemplate.id)
    return list((await session.scalars(stmt)).all())


async def apply_template(
    session: AsyncSession, row: SurveyTemplate, **fields: Any
) -> SurveyTemplate:
    """칸만 바꾼다 — flush 하지 않는다. 부르는 쪽이 crud.flush.flush_or_conflict 로 바로 flush 해 부분 유일 색인
    uq_survey_template_default 위반(23505)을 409 로 바꾼다(기본 지정은 옛 기본 false 와 새 대상 true 를 따로 flush 해
    ORM 이 두 UPDATE 순서를 바꾸지 못하게 한다, 결정 viii). flush 뒤 updated_at 이 만료되니 응답에 쓰려면
    get_template(fresh=True) 로 다시 읽는다."""
    for name, value in fields.items():
        setattr(row, name, value)
    return row


async def delete_template(session: AsyncSession, template_id: int) -> bool:
    """지웠으면 True. 그 양식으로 배포한 설문의 template_id 는 FK SET NULL 로 끊긴다(스냅샷은 남는다)."""
    stmt = (
        delete(SurveyTemplate)
        .where(SurveyTemplate.id == template_id)
        .returning(SurveyTemplate.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def default_template(session: AsyncSession) -> SurveyTemplate | None:
    """지금 기본 양식(없으면 None). 기본 지정이 잠근 뒤 다시 읽어 옛 기본과 대조한다(populate_existing)."""
    stmt = (
        select(SurveyTemplate)
        .where(SurveyTemplate.is_default.is_(True))
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def course_ids_using(session: AsyncSession, template_id: int) -> list[int]:
    """그 양식으로 배포한 설문의 강의 id(겹침 없이 오름차순) — 양식 삭제가 이 순서로 강의를 잠근다."""
    stmt = (
        select(Survey.course_id)
        .where(Survey.template_id == template_id)
        .distinct()
        .order_by(Survey.course_id)
    )
    return list((await session.scalars(stmt)).all())


async def deployed_counts(
    session: AsyncSession, template_ids: Collection[int]
) -> dict[int, int]:
    """양식마다 그 양식으로 배포한 설문 수(밀려난 설문 포함). 배포가 없으면 0."""
    wanted = list(template_ids)
    counts = dict.fromkeys(wanted, 0)
    if not wanted:
        return counts
    stmt = (
        select(Survey.template_id, func.count())
        .where(Survey.template_id.in_(wanted))
        .group_by(Survey.template_id)
    )
    for template_id, n in (await session.execute(stmt)).all():
        counts[template_id] = n
    return counts
