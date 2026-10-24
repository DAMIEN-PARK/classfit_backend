"""진단 회차 끝점(관리자만, AdminCaller, T9a 계획 결정 i·ii·iv·v·viii·x·xviii).

- GET /v1/admin/diagnoses/{diagnosis_id}: 회차 하나(답·증빙·현장·역량·권장 구성 — 작성 화면).
- PATCH …: 답·증빙·현장·역량·구분·진단일(하나 이상 · 칸마다 통째 교체). draft·review 만이다(final 은 409 — 새 회차로).
  링크 회차의 진단일(= 제출일)을 다른 값으로 바꾸면 422 violations[{loc: ["body", "diagnosed_on"], type: "frozen_field"}]
  (같은 값은 바뀐 칸이 아니다). 바뀐 칸이 없으면 audit 이 없다.
- DELETE … 204: draft·review 만. 링크 회차면 그 링크가 revoked 가 된다(응답을 받지 않은 것으로). 번호는 당기지 않는다.
- POST …:finalize 200: 17지표를 다 답해야 한다(아니면 409 + missing). 권장 구성은 저장한 것 ∨ 그 순간 초안을 남긴다.
  다시 확정 · 확정 뒤 PATCH·reco·DELETE 는 409 다.
- GET …/report: 영역 200 × 4 · 총 800 · L1~L5(17지표 전이면 level null) · 직전 완료 회차(final ∨ review, 17지표)와 증감 —
  읽는 시점에 계산한다. reco 는 저장한 것 ∨ 초안이고 GET 은 저장하지 않는다(reco_saved).
- PATCH …/reco: 권장 구성 전체(draft·review 만).
- GET …/pdf: 회차가 있으면 501 /problems/not-implemented(1차는 JSON 리포트만, ADR-003 결정 7). 상태와 무관하다.
- 경로 id 는 IdPath(밖이면 DB 를 치지 않고 422). 산식은 service/rules/diagnosis.py 한 곳이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.deps import AdminCaller, DbSession
from classfit.app.endpoints.assign import IdPath
from classfit.app.errors import AppError
from classfit.core.errors import NotFound
from classfit.crud import diagnosis as crud_diagnosis
from classfit.models import Diagnosis
from classfit.schemas.diagnosis import DiagnosisOut, DiagnosisPatchIn, RecoIn, ReportOut
from classfit.service.diagnosis import reports, rounds

router = APIRouter(prefix="/v1/admin", tags=["diagnoses"])

_ONE = {404: {"description": "회차가 없음"}}
_STATE = {**_ONE, 409: {"description": "확정한 회차(새 회차로)"}}
_FROZEN = {"diagnosed_on": "링크 회차의 제출일은 바꿀 수 없습니다"}


def diagnosis_out(row: Diagnosis) -> DiagnosisOut:
    return DiagnosisOut.model_validate(row, from_attributes=True)


async def diagnosis_or_404(session: AsyncSession, diagnosis_id: int) -> Diagnosis:
    row = await crud_diagnosis.get_diagnosis(session, diagnosis_id)
    if row is None:
        raise NotFound("진단 회차가 없습니다")
    return row


def report_out(rep: reports.Report) -> ReportOut:
    """service 가 계산한 리포트(영역·지표 점수 · level · 비교 대상과 증감 · reco) → 응답 모양."""
    return ReportOut.model_validate(rep, from_attributes=True)


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisOut, responses=_ONE)
async def get_diagnosis(
    diagnosis_id: IdPath, session: DbSession, _: AdminCaller
) -> DiagnosisOut:
    return diagnosis_out(await diagnosis_or_404(session, diagnosis_id))


@router.patch(
    "/diagnoses/{diagnosis_id}",
    response_model=DiagnosisOut,
    responses={
        **_STATE,
        422: {"description": "모양 · 링크 회차의 제출일(frozen_field)"},
    },
)
async def patch_diagnosis(
    diagnosis_id: IdPath,
    body: DiagnosisPatchIn,
    session: DbSession,
    caller: AdminCaller,
) -> DiagnosisOut:
    try:
        row = await rounds.patch_round(
            session,
            diagnosis_id=diagnosis_id,
            fields=body.model_dump(include=set(body.model_fields_set)),
            actor=f"admin:{caller.id}",
        )
    except rounds.FrozenField as exc:
        raise RequestValidationError(
            [
                {
                    "loc": ("body", exc.field),
                    "msg": _FROZEN.get(exc.field, "바꿀 수 없는 칸입니다"),
                    "type": "frozen_field",
                }
            ]
        ) from None
    return diagnosis_out(row)


@router.delete(
    "/diagnoses/{diagnosis_id}",
    status_code=204,
    response_class=Response,
    responses=_STATE,
)
async def delete_diagnosis(
    diagnosis_id: IdPath, session: DbSession, caller: AdminCaller
) -> Response:
    await rounds.delete_round(
        session, diagnosis_id=diagnosis_id, actor=f"admin:{caller.id}"
    )
    return Response(status_code=204)


@router.post(
    "/diagnoses/{diagnosis_id}:finalize",
    response_model=DiagnosisOut,
    responses={**_ONE, 409: {"description": "이미 확정 · 미응답 지표가 있음(missing)"}},
)
async def finalize_diagnosis(
    diagnosis_id: IdPath, session: DbSession, caller: AdminCaller
) -> DiagnosisOut:
    row = await rounds.finalize_round(
        session,
        diagnosis_id=diagnosis_id,
        admin_id=caller.id,
        actor=f"admin:{caller.id}",
    )
    return diagnosis_out(row)


@router.get(
    "/diagnoses/{diagnosis_id}/report", response_model=ReportOut, responses=_ONE
)
async def diagnosis_report(
    diagnosis_id: IdPath, session: DbSession, _: AdminCaller
) -> ReportOut:
    return report_out(await reports.report_of(session, diagnosis_id=diagnosis_id))


@router.patch(
    "/diagnoses/{diagnosis_id}/reco", response_model=DiagnosisOut, responses=_STATE
)
async def save_reco(
    diagnosis_id: IdPath, body: RecoIn, session: DbSession, caller: AdminCaller
) -> DiagnosisOut:
    row = await rounds.save_reco(
        session,
        diagnosis_id=diagnosis_id,
        reco=body.model_dump(),
        actor=f"admin:{caller.id}",
    )
    return diagnosis_out(row)


@router.get(
    "/diagnoses/{diagnosis_id}/pdf",
    response_class=Response,
    responses={
        **_ONE,
        501: {
            "description": "1차에 진단 PDF 를 만들지 않음(/problems/not-implemented)"
        },
    },
)
async def diagnosis_pdf(
    diagnosis_id: IdPath, session: DbSession, _: AdminCaller
) -> Response:
    await diagnosis_or_404(session, diagnosis_id)
    raise AppError(
        501,
        "진단 PDF 는 1차에 만들지 않습니다 — 리포트는 JSON(…/report)입니다",
        type="/problems/not-implemented",
    )
