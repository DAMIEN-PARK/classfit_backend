"""설문 양식 끝점(관리자만, AdminCaller, T8 계획 결정 i·ii·v·viii·xviii·xxv·xxvi).

- GET /v1/admin/survey-templates: 양식 전부 {items}(이름 → id 순, 커서 없음). deployed 는 그 양식으로 배포한 설문 수다.
- POST …: 201. GET·PATCH·DELETE …/{template_id}: PATCH 는 준 칸만 바꾸고(이미 배포한 설문은 그대로 — 배포본은
  복제본이다), DELETE 는 204 이고 기본 양식이면 409 다(다른 양식을 먼저 기본으로). 배포된 설문은 template_id 가 null 이
  되고 이름·문항 스냅샷이 남는다(결과 그대로).
- POST …:set-default: 그 양식만 기본(이미 기본이면 그대로 200). POST …:duplicate: 201, 이름 앞 95자 + " (복제)",
  기본 아님, 문항 그대로.
- 문항 모양은 schemas 가, 교차 규칙(key 유일 · star·is_overall 은 scale 만 · …)은 service 가 재고 둘 다 422 다 — 교차
  규칙 위반은 violations[].loc ["body", "questions", 차례, 칸](questions_invalid). 행은 남지 않는다.
- 경로 id 는 IdPath(1 ≤ id < 2**63, 밖이면 DB 를 치지 않고 422 loc ["path", "template_id"]). 없는 양식 404.
- 쓰기는 양식 행을 돌려받고, 응답은 service.surveys.views 의 TemplateView(속성 이름 = 응답 칸, deployed 포함)를
  from_attributes 로 읽는다.
- 바뀐 것이 있는 쓰기마다 audit 1행이다(service.surveys.templates).
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import AdminCaller, DbSession
from classfit.app.endpoints.assign import IdPath
from classfit.schemas.survey import (
    TemplateIn,
    TemplateListOut,
    TemplateOut,
    TemplatePatchIn,
)
from classfit.service.surveys import templates, views
from classfit.service.surveys.templates import QuestionsRejected

router = APIRouter(prefix="/v1/admin", tags=["survey-templates"])

_ONE = {404: {"description": "양식이 없음"}}
_INVALID = {
    422: {
        "description": "문항 모양 · 교차 규칙(key 유일 · star·is_overall 은 scale 만 …)"
    }
}

# rules.survey.question_errors 의 (칸, 까닭) → 안내 글자
_ISSUES = {
    ("key", "duplicate"): "문항 key 가 겹칩니다",
    ("star", "scale_only"): "비교 지표(star)는 척도 문항에만 둡니다",
    ("is_overall", "scale_only"): "종합(is_overall)은 척도 문항에만 둡니다",
    ("is_overall", "many"): "종합(is_overall) 문항은 하나까지입니다",
    ("options", "required"): "선택형 문항은 선택지가 있어야 합니다",
    ("options", "choice_only"): "선택지는 선택형 문항에만 둡니다",
    ("custom", "choice_only"): "직접 입력(custom)은 선택형 문항에만 둡니다",
    ("required", "info"): "안내문(info)은 필수일 수 없습니다",
    ("questions", "no_answer_question"): "답을 받는 문항이 하나 이상 있어야 합니다",
}


def questions_invalid(exc: QuestionsRejected) -> RequestValidationError:
    """service 의 교차 규칙 위반을 본문 422 로(배포 설문 PATCH 도 쓴다). loc 은 ["body", "questions", 차례, 칸]
    이고 목록 전체 규칙(답 문항 하나 이상)은 ["body", "questions"], type 은 까닭 글자다."""
    return RequestValidationError(
        [
            {
                "loc": ("body", "questions")
                + (() if issue.index is None else (issue.index, issue.field)),
                "msg": _ISSUES.get((issue.field, issue.reason), issue.reason),
                "type": issue.reason,
            }
            for issue in exc.errors
        ]
    )


def template_out(view: views.TemplateView) -> TemplateOut:
    return TemplateOut.model_validate(view, from_attributes=True)


@router.get("/survey-templates", response_model=TemplateListOut)
async def list_templates(session: DbSession, _: AdminCaller) -> TemplateListOut:
    rows = await views.list_templates(session)
    return TemplateListOut(items=[template_out(v) for v in rows])


@router.post(
    "/survey-templates", response_model=TemplateOut, status_code=201, responses=_INVALID
)
async def create_template(
    body: TemplateIn, session: DbSession, caller: AdminCaller
) -> TemplateOut:
    try:
        row = await templates.create_template(
            session,
            name=body.name,
            note=body.note,
            questions=[q.model_dump() for q in body.questions],
            actor=f"admin:{caller.id}",
        )
    except QuestionsRejected as exc:
        raise questions_invalid(exc) from None
    return template_out(await views.template_view(session, row))


@router.get(
    "/survey-templates/{template_id}", response_model=TemplateOut, responses=_ONE
)
async def get_template(
    template_id: IdPath, session: DbSession, _: AdminCaller
) -> TemplateOut:
    return template_out(await views.get_template(session, template_id))


@router.patch(
    "/survey-templates/{template_id}",
    response_model=TemplateOut,
    responses={**_ONE, **_INVALID},
)
async def patch_template(
    template_id: IdPath, body: TemplatePatchIn, session: DbSession, caller: AdminCaller
) -> TemplateOut:
    """준 칸만 바꾼다. 바뀐 칸이 없으면 그대로 200 · audit 없음."""
    try:
        row = await templates.update_template(
            session,
            template_id=template_id,
            changes=body.model_dump(include=set(body.model_fields_set)),
            actor=f"admin:{caller.id}",
        )
    except QuestionsRejected as exc:
        raise questions_invalid(exc) from None
    return template_out(await views.template_view(session, row))


@router.delete(
    "/survey-templates/{template_id}",
    status_code=204,
    response_class=Response,
    responses={**_ONE, 409: {"description": "기본 양식"}},
)
async def delete_template(
    template_id: IdPath, session: DbSession, caller: AdminCaller
) -> Response:
    await templates.delete_template(
        session, template_id=template_id, actor=f"admin:{caller.id}"
    )
    return Response(status_code=204)


@router.post(
    "/survey-templates/{template_id}:set-default",
    response_model=TemplateOut,
    responses={**_ONE, 409: {"description": "기본 양식이 방금 바뀜(다시 시도)"}},
)
async def set_default_template(
    template_id: IdPath, session: DbSession, caller: AdminCaller
) -> TemplateOut:
    """그 양식만 기본이 된다. 이미 기본이면 그대로 200 · audit 없음."""
    row = await templates.set_default_template(
        session, template_id=template_id, actor=f"admin:{caller.id}"
    )
    return template_out(await views.template_view(session, row))


@router.post(
    "/survey-templates/{template_id}:duplicate",
    response_model=TemplateOut,
    status_code=201,
    responses=_ONE,
)
async def duplicate_template(
    template_id: IdPath, session: DbSession, caller: AdminCaller
) -> TemplateOut:
    row = await templates.duplicate_template(
        session, template_id=template_id, actor=f"admin:{caller.id}"
    )
    return template_out(await views.template_view(session, row))
