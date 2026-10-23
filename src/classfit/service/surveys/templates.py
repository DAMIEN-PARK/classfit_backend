"""설문 양식 쓰기 다섯(T8 결정 viii·xviii·xix): 만들기 · 고치기 · 지우기 · 기본 지정 · 복제. flush 까지만.

- 교차 규칙(rules.survey.question_errors)에 걸리면 QuestionsRejected(끝점이 422). 모양은 schemas 가 먼저 잰다.
- 쓰기는 양식 행(SurveyTemplate)을 돌려준다. 배포 수(deployed)를 붙인 응답 모양은 views.template_view 가 만든다.
- 고치기·지우기는 맨 앞에서 양식 행을 FOR UPDATE(lock_template)로 잡는다(없으면 404). 지우기는 기본 양식이면 409, 그 양식으로
  배포한 설문의 강의를 id 오름차순으로 잡고(그 사이 지워진 강의는 건너뛴다) 그 설문 행들을 id 순으로 잡은 뒤 지운다 — 배포
  설문의 template_id 는 SET NULL 로 끊기고 이름·문항 스냅샷은 남는다.
- 기본 지정은 옛 기본을 읽고 → 옛 기본·대상 두 행을 id 오름차순 FOR UPDATE(lock_templates) → 대상 없음 404 → 이미 기본이면
  그대로(멱등) → 잠근 뒤 지금 기본을 다시 읽어 옛 기본과 다르면 409 → 옛 false · flush → 새 true · flush. flush 는
  flush_or_conflict 라 부분 유일 색인 위반도 409 다.
- 양식을 고쳐도 이미 배포한 설문은 바뀌지 않는다(배포 시점 스냅샷).
- audit 은 바뀐 것이 있을 때만 1행: survey_template.create · update(detail {fields}) · delete · set_default · duplicate.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import audit as crud_audit
from classfit.crud import course as crud_course
from classfit.crud import flush as crud_flush
from classfit.crud import survey as crud_survey
from classfit.crud import survey_template as crud_survey_template
from classfit.models import SurveyTemplate
from classfit.service.rules.survey import QuestionIssue, question_errors
from classfit.service.surveys.views import NO_TEMPLATE

EDITABLE = ("name", "note", "questions")
DUPLICATE_SUFFIX = " (복제)"
DUPLICATE_PREFIX_MAX = 95  # 95 + " (복제)" 5자 = 이름 상한 100
DEFAULT_TAKEN = "기본 양식이 둘이 될 수 없습니다"


class QuestionsRejected(ValueError):
    """문항 교차 규칙 위반(끝점이 422 violations[].loc = ["body","questions",<i>,<칸>])."""

    def __init__(self, errors: list[QuestionIssue]) -> None:
        super().__init__("문항 규칙에 맞지 않습니다")
        self.errors = errors


def check_questions(questions: list[dict[str, Any]]) -> None:
    if errors := question_errors(questions):
        raise QuestionsRejected(errors)


async def _audit(
    session: AsyncSession, actor: str, action: str, template_id: int, **detail: Any
) -> None:
    await crud_audit.insert_audit(
        session,
        actor=actor,
        action=f"survey_template.{action}",
        target_type="survey_template",
        target_id=str(template_id),
        detail=detail,
    )


async def create_template(
    session: AsyncSession,
    *,
    name: str,
    note: str | None,
    questions: list[dict[str, Any]],
    actor: str,
) -> SurveyTemplate:
    check_questions(questions)
    row = await crud_survey_template.insert_template(
        session, name=name, note=note, is_default=False, questions=questions
    )
    await _audit(session, actor, "create", row.id)
    return row


async def update_template(
    session: AsyncSession,
    *,
    template_id: int,
    changes: Mapping[str, Any],
    actor: str,
) -> SurveyTemplate:
    """준 칸(name · note · questions)만 바꾼다. 바뀐 칸이 없으면 쓰지 않는다(audit 없음)."""
    row = await crud_survey_template.lock_template(session, template_id)
    if row is None:
        raise NotFound(NO_TEMPLATE)
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValueError(f"고칠 수 없는 칸: {sorted(unknown)}")
    if "questions" in changes:
        check_questions(changes["questions"])
    changed = [f for f in EDITABLE if f in changes and getattr(row, f) != changes[f]]
    if not changed:
        return row
    await crud_survey_template.apply_template(
        session, row, **{f: changes[f] for f in changed}
    )
    await crud_flush.flush_or_conflict(session, DEFAULT_TAKEN)
    await _audit(session, actor, "update", template_id, fields=changed)
    fresh = await crud_survey_template.get_template(session, template_id, fresh=True)
    assert fresh is not None  # 행을 잡고 있다
    return fresh


async def delete_template(
    session: AsyncSession, *, template_id: int, actor: str
) -> None:
    row = await crud_survey_template.lock_template(session, template_id)
    if row is None:
        raise NotFound(NO_TEMPLATE)
    if row.is_default:
        raise Conflict(
            "기본 양식은 지울 수 없습니다. 다른 양식을 기본으로 지정한 뒤 지우세요"
        )
    name = row.name
    for course_id in await crud_survey_template.course_ids_using(session, template_id):
        if await crud_course.lock_course(session, course_id) is None:
            continue  # 그 사이 강의가 지워졌다 — 설문도 CASCADE 로 없다
    await crud_survey.lock_in_id_order(session, template_id=template_id)
    await crud_survey_template.delete_template(session, template_id)
    await _audit(session, actor, "delete", template_id, name=name)


async def set_default_template(
    session: AsyncSession, *, template_id: int, actor: str
) -> SurveyTemplate:
    old = await crud_survey_template.default_template(session)
    old_id = None if old is None else old.id
    locked = await crud_survey_template.lock_templates(
        session, {template_id} | ({old_id} if old_id is not None else set())
    )
    by_id = {r.id: r for r in locked}
    target = by_id.get(template_id)
    if target is None:
        raise NotFound(NO_TEMPLATE)
    if target.is_default:
        return target
    now = await crud_survey_template.default_template(session)
    if (None if now is None else now.id) != old_id:
        raise Conflict("기본 양식이 방금 바뀌었습니다. 다시 시도하세요")
    if old_id is not None:
        await crud_survey_template.apply_template(
            session, by_id[old_id], is_default=False
        )
        await crud_flush.flush_or_conflict(session, DEFAULT_TAKEN)
    await crud_survey_template.apply_template(session, target, is_default=True)
    await crud_flush.flush_or_conflict(session, DEFAULT_TAKEN)
    await _audit(session, actor, "set_default", template_id, previous_id=old_id)
    fresh = await crud_survey_template.get_template(session, template_id, fresh=True)
    assert fresh is not None  # 행을 잡고 있다
    return fresh


async def duplicate_template(
    session: AsyncSession, *, template_id: int, actor: str
) -> SurveyTemplate:
    """이름은 원본 앞 95자 + " (복제)", 기본 아님, 문항 복사."""
    source = await crud_survey_template.get_template(session, template_id)
    if source is None:
        raise NotFound(NO_TEMPLATE)
    row = await crud_survey_template.insert_template(
        session,
        name=source.name[:DUPLICATE_PREFIX_MAX] + DUPLICATE_SUFFIX,
        note=source.note,
        is_default=False,
        questions=copy.deepcopy(source.questions),
    )
    await _audit(session, actor, "duplicate", row.id, source_id=template_id)
    return row
