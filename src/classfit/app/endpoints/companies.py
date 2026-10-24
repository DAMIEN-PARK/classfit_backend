"""회사·진단 링크 관리 끝점(관리자만, AdminCaller, T9a 계획 결정 i·ii·iii·vi·ix·x·xii·xiii·xxiv).

- GET /v1/admin/companies?q=&cursor=&limit=: 키셋 커서 {items, next_cursor, has_more}. 첫 WHERE 는 주체 범위
  (crud.scope.company_scope)다. q 는 이름·담당자·업종 부분 일치(% · _ 는 글자). 깨진 커서는 422 loc ["query", "cursor"].
- POST /v1/admin/companies 201 · GET …/{company_id} 상세(회차 · 링크 · 연결 강의) · PATCH 200 상세(바뀐 칸이 없으면 audit 없음) ·
  DELETE 204(활성 연결 강의가 있으면 409 — 회차·링크는 같이 지워지고 보관 강의의 연결은 풀린다).
- POST …/{company_id}/diagnoses {phase, diagnosed_on?} 201: 방문 회차(draft · round_no = 그 회사 최대 + 1). 진단일 기본은 오늘.
- POST …/{company_id}/links {phase, recipient?, expires_on?} 201: 회사당 open 하나다. 만료가 지난 open 은 먼저 회수하고 발급하고,
  만료 전 open 이 있으면 409. expires_on 은 오늘 ~ 오늘 + 365(밖은 422 loc ["body", "expires_on"]), 비우면 오늘 + 14.
- POST /v1/admin/links/{token}:revoke 200: open(만료 지남 포함) → revoked · 이미 revoked 면 그대로(audit 없음) · submitted 는
  409. 없는 토큰과 모양 밖 토큰은 같은 404 다(모양 밖은 service 가 DB 를 치지 않고 막는다).
- 경로 id 는 IdPath(밖이면 DB 를 치지 않고 422). 링크 state 는 오늘(Today) 기준 계산값이다. 토큰 경로의 instance·로그 {token}
  과 Cache-Control: no-store 는 app/errors.py·미들웨어가 단다(결정 xxv).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.exceptions import RequestValidationError

from classfit.app.deps import AdminCaller, DbSession, Today
from classfit.app.endpoints.admin_instructors import query_text
from classfit.app.endpoints.assign import IdPath
from classfit.app.endpoints.diagnoses import diagnosis_out
from classfit.core.cursor import decode_cursor
from classfit.schemas.company import (
    CompanyDetailOut,
    CompanyIn,
    CompanyOut,
    CompanyPatchIn,
    LinkedCourseOut,
    LinkOut,
    RoundBriefOut,
    RoundSummaryOut,
)
from classfit.schemas.diagnosis import DiagnosisCreateIn, DiagnosisOut, LinkIssueIn
from classfit.schemas.page import Page
from classfit.service.diagnosis import companies, links, rounds

router = APIRouter(prefix="/v1/admin", tags=["companies"])

_ONE = {404: {"description": "회사가 없음"}}


# ── 응답 조립(service 의 요약 dataclass → 응답 모양. 점수·level·링크 state 는 service 가 계산해 담는다)


def _brief(brief: companies.RoundBrief | None) -> RoundBriefOut | None:
    return (
        None
        if brief is None
        else RoundBriefOut.model_validate(brief, from_attributes=True)
    )


def link_out(link: companies.LinkSummary) -> LinkOut:
    return LinkOut.model_validate(link, from_attributes=True)


def _company_fields(view: companies.CompanyView) -> dict[str, Any]:
    row = view.company
    return {
        "id": row.id,
        "name": row.name,
        "contact": row.contact,
        "phone": row.phone,
        "industry": row.industry,
        "size": row.size,
        "depts": list(row.depts),
        "memo": row.memo,
        "last_round": _brief(view.last_round),
        "latest_final_round": _brief(view.latest_final_round),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def company_out(view: companies.CompanyView) -> CompanyOut:
    return CompanyOut(**_company_fields(view))


def detail_out(view: companies.CompanyDetail) -> CompanyDetailOut:
    return CompanyDetailOut(
        **_company_fields(view),
        rounds=[
            RoundSummaryOut.model_validate(r, from_attributes=True) for r in view.rounds
        ],
        links=[link_out(r) for r in view.links],
        courses=[LinkedCourseOut(id=i, title=t) for i, t in view.courses],
    )


def _bad_expiry(msg: str) -> RequestValidationError:
    return RequestValidationError(
        [{"loc": ("body", "expires_on"), "msg": msg, "type": "value_error"}]
    )


# ── 회사


@router.get("/companies", response_model=Page[CompanyOut])
async def list_companies(
    session: DbSession,
    caller: AdminCaller,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CompanyOut]:
    try:
        if cursor is not None:
            decode_cursor(cursor)  # 깨진 커서만 422 로 — 목록 읽기의 다른 ValueError 는 500 그대로
    except ValueError:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "cursor"),
                    "msg": "깨진 커서입니다",
                    "type": "value_error",
                }
            ]
        ) from None
    views, next_cursor, has_more = await companies.company_list(
        session, caller, q=query_text(q), cursor=cursor, limit=limit
    )
    return Page[CompanyOut](
        items=[company_out(v) for v in views],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/companies", response_model=CompanyOut, status_code=201)
async def create_company(
    body: CompanyIn, session: DbSession, caller: AdminCaller
) -> CompanyOut:
    row = await companies.create_company(
        session, fields=body.model_dump(), actor=f"admin:{caller.id}"
    )
    return company_out(
        companies.CompanyView(company=row, last_round=None, latest_final_round=None)
    )


@router.get("/companies/{company_id}", response_model=CompanyDetailOut, responses=_ONE)
async def get_company(
    company_id: IdPath, session: DbSession, _: AdminCaller, today: Today
) -> CompanyDetailOut:
    view = await companies.company_detail(session, company_id=company_id, today=today)
    return detail_out(view)


@router.patch(
    "/companies/{company_id}", response_model=CompanyDetailOut, responses=_ONE
)
async def patch_company(
    company_id: IdPath,
    body: CompanyPatchIn,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> CompanyDetailOut:
    await companies.patch_company(
        session,
        company_id=company_id,
        fields=body.changes(),
        actor=f"admin:{caller.id}",
    )
    view = await companies.company_detail(session, company_id=company_id, today=today)
    return detail_out(view)


@router.delete(
    "/companies/{company_id}",
    status_code=204,
    response_class=Response,
    responses={**_ONE, 409: {"description": "활성(보관하지 않은) 연결 강의가 있음"}},
)
async def delete_company(
    company_id: IdPath, session: DbSession, caller: AdminCaller
) -> Response:
    await companies.delete_company(
        session, company_id=company_id, actor=f"admin:{caller.id}"
    )
    return Response(status_code=204)


# ── 회차 생성 · 링크


@router.post(
    "/companies/{company_id}/diagnoses",
    response_model=DiagnosisOut,
    status_code=201,
    responses=_ONE,
)
async def create_diagnosis(
    company_id: IdPath,
    body: DiagnosisCreateIn,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> DiagnosisOut:
    row = await rounds.create_round(
        session,
        company_id=company_id,
        phase=body.phase,
        diagnosed_on=body.diagnosed_on or today,
        actor=f"admin:{caller.id}",
    )
    return diagnosis_out(row)


@router.post(
    "/companies/{company_id}/links",
    response_model=LinkOut,
    status_code=201,
    responses={**_ONE, 409: {"description": "만료 전 open 링크가 있음(먼저 회수)"}},
)
async def issue_link(
    company_id: IdPath,
    body: LinkIssueIn,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> LinkOut:
    if body.expires_on is not None:
        _, latest = links.link_window(today)
        if body.expires_on < today:
            raise _bad_expiry("만료일은 오늘보다 앞일 수 없습니다")
        if body.expires_on > latest:
            raise _bad_expiry(f"만료일은 오늘부터 {links.LINK_MAX_DAYS}일 안입니다")
    row = await links.issue_link(
        session,
        company_id=company_id,
        phase=body.phase,
        recipient=body.recipient,
        expires_on=body.expires_on,
        today=today,
        actor=f"admin:{caller.id}",
    )
    return link_out(companies.link_summary(row, today))


@router.post(
    "/links/{token}:revoke",
    response_model=LinkOut,
    responses={
        404: {"description": "링크가 없음(모양 밖 토큰 포함, 같은 본문)"},
        409: {"description": "제출된 링크"},
    },
)
async def revoke_link(
    token: str, session: DbSession, caller: AdminCaller, today: Today
) -> LinkOut:
    row, _changed = await links.revoke_link(
        session, token=token, actor=f"admin:{caller.id}"
    )
    return link_out(companies.link_summary(row, today))
