"""공개 진단 링크 끝점(인증 없음 — 토큰이 주체, Design 2절 · T9a 계획 결정 i·vi·xii·xxv).

- GET /v1/ax/{token}: open ∧ 만료일 ≥ 오늘(당일 유효)이면 200 {company_name, phase, expires_on, areas, options} — 답·증빙
  문구·담당자·받는 분·토큰이 없다.
- POST /v1/ax/{token} 본문 {answers(17지표 전부), field?, matrix?, respondent{name, title?, email?}}: 본문 422 가 먼저다
  (FastAPI 가 핸들러 전에 검증) → 404 → 410. 제출은 검토 대기(review) 회차를 만들고 링크를 바로 닫는다.
  201 {phase, submitted_at} — 점수·레벨·회차 번호가 없다.
- 없는 토큰·모양 밖 토큰은 같은 404 본문이다(있는지 흘리지 않는다). 만료·회수·제출은 410 이유 코드
  /problems/diag-link-expired · -revoked · -submitted 이고 본문에 회사명·받는 분·답이 없다. service 의 Gone(reason) 을
  끝점이 그 type 의 AppError 로 바꿔 던진다(reason 글자가 본문에 따로 실리지 않고, 트랜잭션은 롤백된다).
- Authorization 헤더는 보지 않는다. 로그·instance 의 {token} 과 Cache-Control: no-store 는 미들웨어·app/errors.py 가 단다
  (결정 xxv — 끝점은 헤더를 달지 않는다). 공개 GET 은 audit 하지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter

from classfit.app.deps import DbSession, Today
from classfit.app.errors import AppError
from classfit.core.errors import Gone
from classfit.schemas.ax import (
    AxAreaOut,
    AxLinkOut,
    AxOptionsOut,
    AxSubmitIn,
    AxSubmittedOut,
)
from classfit.service.diagnosis import public

router = APIRouter(prefix="/v1", tags=["ax"])

# Gone 의 reason → problem type(본문에 reason 글자를 따로 싣지 않는다)
_GONE = {
    "expired": "/problems/diag-link-expired",
    "revoked": "/problems/diag-link-revoked",
    "submitted": "/problems/diag-link-submitted",
}
_RESPONSES: dict[int | str, dict[str, str]] = {
    404: {"description": "없는 토큰 · 모양 밖 토큰(같은 본문)"},
    410: {
        "description": "만료(diag-link-expired) · 회수(diag-link-revoked) · 제출됨(diag-link-submitted)"
    },
}


def _gone(exc: Gone) -> AppError:
    return AppError(410, exc.message, type=_GONE[exc.extra["reason"]])


@router.get("/ax/{token}", response_model=AxLinkOut, responses=_RESPONSES)
async def get_link(token: str, session: DbSession, today: Today) -> AxLinkOut:
    try:
        view = await public.link_view(session, token=token, today=today)
    except Gone as exc:
        raise _gone(exc) from None
    return AxLinkOut(
        company_name=view.company_name,
        phase=view.phase,  # type: ignore[arg-type]  # CHECK 가 두 값으로 막는다
        expires_on=view.expires_on,
        areas=[AxAreaOut.model_validate(a) for a in view.areas],
        options=AxOptionsOut.model_validate(view.options),
    )


@router.post(
    "/ax/{token}", response_model=AxSubmittedOut, status_code=201, responses=_RESPONSES
)
async def submit_link(
    token: str,
    body: AxSubmitIn,
    session: DbSession,
    today: Today,
) -> AxSubmittedOut:
    try:
        link = await public.submit(
            session,
            token=token,
            answers=body.answers,
            field=body.field.model_dump(),
            matrix=body.matrix,
            respondent=body.respondent.model_dump(),
            today=today,
        )
    except Gone as exc:
        raise _gone(exc) from None
    if link.submitted_at is None:  # submit 이 채운다(CHECK submitted ⇒ submitted_at)
        raise RuntimeError("제출한 링크에 submitted_at 이 없습니다")
    return AxSubmittedOut(phase=link.phase, submitted_at=link.submitted_at)  # type: ignore[arg-type]
