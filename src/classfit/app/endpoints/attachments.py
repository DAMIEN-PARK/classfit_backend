"""세션 첨부 끝점(T2b 계획 결정 viii·x·xii): 수강생 목록 · 관리자 넣기(pdf·link) · 관리자 지우기.

넣기(POST /v1/admin/sessions/{session_id}/attachments) 판정 순서:
  401 → 403(AdminCaller) → 404(세션) → Content-Length 없음 411 · 상한 + 1MiB 초과 413
  → 폼 파싱(파트 수 초과·boundary 없음은 Starlette 가 400 /problems/bad-request) → 422(kind·title·url·file 모양)
  → 501(pdf 인데 FILE_STORE_ROOT 미구성) → 실제 크기 413 → 첫 5바이트 %PDF- 아니면 422 → 201.
- 폼 매개변수를 선언하지 않는다. FastAPI 는 폼 본문을 의존성보다 먼저 읽으므로(fastapi/routing.py:451-475),
  선언하면 인증 전에 대용량 본문이 스풀된다. 인증 뒤 `async with request.form(...)` 로 읽어 스풀 파일까지 닫는다.
- content_type 은 받은 값이 아니라 application/pdf 로 고정한다. OpenAPI 의 본문 모양은 openapi_extra 로 적는다.
- 수강생 목록은 열린 카드(is_open ∧ 첨부 ≥ 1)의 첨부만이다. 잠긴 세션·남의 강의 세션은 403, 없는 세션은 404.
  목록 모양은 {items, next_cursor, has_more} 이고, 한 세션의 첨부는 한 쪽에 다 준다(has_more 거짓).
- 넣기·지우기는 audit 1행이다(service.files.attachments).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import FormData, UploadFile

from classfit.app.deps import AdminCaller, DbSession, LearnerCaller
from classfit.app.errors import AppError
from classfit.app.upload import MIB, check_length, invalid
from classfit.core.config import Settings
from classfit.core.errors import NotConfigured, NotFound
from classfit.crud.attachment import AttachmentRow
from classfit.crud.schedule import get_session_and_course
from classfit.schemas.attachment import URL_MAX, AttachmentFormIn, AttachmentOut
from classfit.schemas.page import Page
from classfit.service.courses.portal import session_attachments
from classfit.service.files import attachments as files_attachments
from classfit.service.files.store import href_for

router = APIRouter(prefix="/v1", tags=["attachments"])

_TEXT_FIELDS = ("kind", "title", "description", "url")
_TEXT = {"type": "string"}
_FORM_SCHEMA = {
    "type": "object",
    "required": ["kind", "title"],
    "properties": {
        "kind": {"type": "string", "enum": ["pdf", "link"]},
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "description": _TEXT,
        "url": {
            "type": "string",
            "maxLength": URL_MAX,
            "description": "link 만, http·https",
        },
        "file": {"type": "string", "format": "binary", "description": "pdf 만"},
    },
}
_FORM_DOC: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {"schema": _FORM_SCHEMA},
            "application/x-www-form-urlencoded": {
                "schema": {
                    **_FORM_SCHEMA,
                    "properties": {
                        k: v
                        for k, v in _FORM_SCHEMA["properties"].items()
                        if k != "file"
                    },
                }
            },
        },
    }
}


def attachment_out(item: AttachmentRow) -> AttachmentOut:
    row, key, size = item
    href = href_for(key) if key is not None else row.url
    # CHECK target: link 면 url 이 있다. pdf 는 넣기가 file_id 까지 채운다
    if href is None:
        raise RuntimeError(f"첨부 {row.id} 에 파일도 주소도 없습니다")
    return AttachmentOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        description=row.description,
        href=href,
        size=size,
    )


def _form_fields(form: FormData) -> AttachmentFormIn:
    raw: dict[str, str] = {}
    for name in _TEXT_FIELDS:
        value = form.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise invalid(name, "글자 필드여야 합니다")
        raw[name] = value
    try:
        return AttachmentFormIn.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(
            [
                {"loc": ("body", *e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ]
        ) from None


@router.get(
    "/learner/sessions/{session_id}/attachments",
    response_model=Page[AttachmentOut],
    responses={
        403: {"description": "잠긴 세션(준비 중) · 남의 강의 세션"},
        404: {"description": "세션이 없음"},
    },
)
async def list_learner_attachments(
    session_id: int, session: DbSession, caller: LearnerCaller
) -> Page[AttachmentOut]:
    items = await session_attachments(session, caller, session_id=session_id)
    return Page[AttachmentOut](
        items=[attachment_out(i) for i in items], next_cursor=None, has_more=False
    )


@router.post(
    "/admin/sessions/{session_id}/attachments",
    response_model=AttachmentOut,
    status_code=201,
    openapi_extra=_FORM_DOC,
    responses={
        400: {"description": "깨진 폼(boundary 없음 · 파트 수 초과)"},
        404: {"description": "세션이 없음"},
        411: {"description": "Content-Length 없음"},
        413: {"description": "본문·파일이 상한(attachment_pdf_max_mb)보다 큼"},
        422: {"description": "kind·title·url·file 모양 · PDF 가 아님"},
        501: {"description": "pdf 인데 FILE_STORE_ROOT 미구성"},
    },
)
async def add_attachment(
    session_id: int, request: Request, session: DbSession, caller: AdminCaller
) -> AttachmentOut:
    settings: Settings = request.app.state.settings
    if await get_session_and_course(session, session_id) is None:
        raise NotFound("세션이 없습니다")
    max_bytes = settings.attachment_pdf_max_mb * MIB
    check_length(request, max_bytes)
    actor = f"admin:{caller.id}"
    async with request.form(max_files=1, max_fields=5) as form:
        fields = _form_fields(form)
        if fields.kind == "link":
            if fields.url is None:  # AttachmentFormIn 이 422 로 먼저 막는다
                raise invalid("url", "link 는 url 이 필요합니다")
            row = await files_attachments.add_link_attachment(
                session,
                session_id=session_id,
                title=fields.title,
                description=fields.description,
                url=fields.url,
                actor=actor,
            )
            return attachment_out((row, None, None))
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise invalid("file", "pdf 는 file 파트가 필요합니다")
        root = settings.file_store_root
        if root is None:
            missing = settings.missing("file_store_root")
            raise NotConfigured("파일 저장소가 구성되지 않았습니다", missing=missing)
        data = await upload.read(max_bytes + 1)
        try:
            row, stored = await files_attachments.add_pdf_attachment(
                session,
                root=root,
                max_bytes=max_bytes,
                session_id=session_id,
                title=fields.title,
                description=fields.description,
                data=data,
                actor=actor,
            )
        except files_attachments.PdfRejected as exc:
            if exc.reason == "too_large":
                raise AppError(
                    413, f"PDF 는 {settings.attachment_pdf_max_mb}MB 까지입니다"
                ) from None
            raise invalid("file", "PDF 파일이 아닙니다") from None
        return attachment_out((row, stored.key, stored.size))


@router.delete(
    "/admin/attachments/{attachment_id}",
    status_code=204,
    response_class=Response,
    responses={404: {"description": "첨부가 없음"}},
)
async def delete_attachment(
    attachment_id: int, session: DbSession, caller: AdminCaller
) -> Response:
    await files_attachments.delete_attachment(
        session, attachment_id=attachment_id, actor=f"admin:{caller.id}"
    )
    return Response(status_code=204)
