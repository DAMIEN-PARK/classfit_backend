"""교육 문의 접수 끝점(인증 없음): POST /v1/inquiries(공개홈 P6 · r3 §5.2 T9b · T9b 계획 결정 i·iv·v·vii·viii·xxiii·xxiv).

- 새 접수 · 1분 안 재제출(같은 이메일 + 같은 내용 — 같은 영수증) · honeypot(website 칸이 차 있음 — 행 0, 저장하지 않는
  난수) 셋 다 200 같은 모양 {receipt_no, received_at} 이다. 응답 코드로 "행이 생겼는지" 가 드러나지 않는다(결정 i·iv).
- 판정 순서: 415(JSON 이 아닌 Content-Type) → 413(본문 inquiry_body_max_bytes, 기본 64KiB) → 422(모양) → 501
  (INQUIRY_NOTIFY_TO 미구성 — honeypot 도 501) → honeypot → 이메일 잠금 → 재제출 → 이메일당 24시간 상한 429 → 넣기
  (영수증 겹침이 RECEIPT_TRIES 번이면 409). 429 type 은 로그인 잠김과 같은 /problems/too-many-requests 다.
- 본문은 T8 의 app.deps.limited_json 이 파싱 전에 읽는다. 상한이 설정 값이라 얇은 의존성 _inquiry_body 가 요청 때
  limited_json(InquiryIn, 상한) 을 부르고, 본문 매개변수가 없으니 OpenAPI requestBody 는 openapi_extra 로 남긴다.
- 인증 의존성이 없고 요청 주소(클라이언트 IP)를 읽지 않는다(결정 vii — IP 저장 없음). audit 없음(결정 x).
- 새 접수는 같은 트랜잭션에 outbox 두 행(inquiry_received → 문의자 · inquiry_notify → INQUIRY_NOTIFY_TO, params
  {inquiry_id} 뿐)을 쓴다. 보내지 않는다(ADR-003 결정 5) — 본문은 scripts.outbox_preview 가 만든다(결정 ix).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from classfit.app.deps import DbSession, limited_json
from classfit.core.config import Settings
from classfit.core.errors import NotConfigured
from classfit.schemas.inquiry import InquiryIn, InquiryReceiptOut
from classfit.service.inquiries.receive import receive_inquiry
from classfit.service.rules.inquiry import InquiryFields, is_honeypot

router = APIRouter(prefix="/v1", tags=["inquiries"])

_BODY_DOC: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": InquiryIn.model_json_schema()}},
    }
}


async def _inquiry_body(request: Request) -> InquiryIn:
    """설정 상한(inquiry_body_max_bytes)으로 limited_json 을 요청 때 부른다 — 415 → 413 → 422."""
    settings: Settings = request.app.state.settings
    return await limited_json(InquiryIn, settings.inquiry_body_max_bytes)(request)


@router.post(
    "/inquiries",
    response_model=InquiryReceiptOut,
    openapi_extra=_BODY_DOC,
    responses={
        409: {"description": "영수증 번호가 거듭 겹침(실제로는 닿지 않는다)"},
        413: {"description": "본문이 inquiry_body_max_bytes(기본 64KiB) 보다 큼"},
        415: {"description": "JSON 이 아닌 Content-Type"},
        422: {"description": "필수 넷 · 형식 · 동의 · 모르는 키"},
        429: {
            "description": "같은 이메일의 24시간 접수 상한(/problems/too-many-requests)"
        },
        501: {"description": "INQUIRY_NOTIFY_TO 미구성(/problems/not_configured)"},
    },
)
async def submit_inquiry(
    request: Request,
    # 본문(415 → 413 → 422)을 DB 세션보다 먼저 읽는다
    body: Annotated[InquiryIn, Depends(_inquiry_body)],
    session: DbSession,
) -> InquiryReceiptOut:
    settings: Settings = request.app.state.settings
    notify_to = settings.inquiry_notify_to
    if notify_to is None:
        missing = settings.missing("inquiry_notify_to")
        raise NotConfigured("문의 수신 주소가 구성되지 않았습니다", missing=missing)
    receipt = await receive_inquiry(
        session,
        fields=InquiryFields(**body.model_dump(exclude={"privacy_agreed", "website"})),
        honeypot=is_honeypot(body.website),
        notify_to=notify_to,
        daily_max=settings.inquiry_daily_max,
    )
    return InquiryReceiptOut(
        receipt_no=receipt.receipt_no, received_at=receipt.received_at
    )
