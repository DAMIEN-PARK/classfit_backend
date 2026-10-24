"""강사 서류 끝점(T3 계획 결정 ix·x): 본인 올리기·교체·지우기 · 관리자 열람(audit).

올리기(PUT /v1/me/documents/{type_id}) 판정 순서는 T2b 첨부 넣기와 같다:
  401 → 403(InstructorCaller) → 404(서류 종류) → Content-Length 없음 411 · 상한 + 1MiB 초과 413
  → 폼 파싱(파트 수 초과·boundary 없음은 Starlette 가 400) → file 파트 없음 422 → 501(FILE_STORE_ROOT 미구성)
  → 실제 크기 413 → 첫 5바이트 %PDF- 아니면 422 → 새로 201 · 교체 200.
- 폼 매개변수를 선언하지 않고 인증 뒤 `async with request.form(max_files=1, max_fields=1)` 로 읽는다(인증 전 스풀 없음).
  411·413 판정은 app.upload 의 공용 도우미다(T11 결정 v). content_type 은 application/pdf 로 고정한다(service).
- 교체는 새 stored_file 행 → 서류 행의 file_id 바꿈 → 옛 stored_file 행 삭제를 한 트랜잭션에서 한다. 바이트는 gc 몫.
  stored_file.owner_id 는 강사 id 이고, /v1/files/{key} 판정은 본인 강사만 참이다(관리자는 거짓).
- 관리자 열람(GET /v1/admin/instructors/{instructor_id}/documents/{type_id})은 매 요청 audit 1행
  (instructor_document.view, detail {instructor_id, type_id}) 뒤에 바이트를 내려받기로 준다. db() 가 응답 전에 커밋한다.
- 서류 종류 id 는 소문자·숫자·밑줄 32자까지다. 이 모양 밖은 DB 를 치지 않고 같은 404 다.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from classfit.app.deps import AdminCaller, DbSession, InstructorCaller
from classfit.app.endpoints.admin_instructors import instructor_or_404
from classfit.app.endpoints.files import SAFE_HEADERS
from classfit.app.errors import AppError
from classfit.app.upload import MIB, check_length, invalid
from classfit.core.config import Settings
from classfit.core.errors import NotConfigured, NotFound
from classfit.crud import instructor_document as crud_document
from classfit.crud.audit import insert_audit
from classfit.models import DocumentType
from classfit.schemas.instructor import DocumentOut
from classfit.service.files import attachments as files_attachments
from classfit.service.files import documents
from classfit.service.files.store import href_for, path_for

log = logging.getLogger("classfit.files")

router = APIRouter(prefix="/v1", tags=["instructor-documents"])

_TYPE_ID = re.compile(r"[a-z0-9_]{1,32}")
_FORM_DOC: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "PDF 만(첫 5바이트 %PDF-)",
                        }
                    },
                }
            }
        },
    }
}


def _store_root(settings: Settings) -> Path:
    root = settings.file_store_root
    if root is None:
        missing = settings.missing("file_store_root")
        raise NotConfigured("파일 저장소가 구성되지 않았습니다", missing=missing)
    return root


async def document_type_or_404(session: AsyncSession, type_id: str) -> DocumentType:
    row = (
        await crud_document.get_document_type(session, type_id)
        if _TYPE_ID.fullmatch(type_id)
        else None
    )
    if row is None:
        raise NotFound("서류 종류가 없습니다")
    return row


@router.put(
    "/me/documents/{type_id}",
    response_model=DocumentOut,
    status_code=201,
    openapi_extra=_FORM_DOC,
    responses={
        200: {"description": "교체(이전 파일 행은 지운다)", "model": DocumentOut},
        400: {"description": "깨진 폼(boundary 없음 · 파트 수 초과)"},
        404: {"description": "서류 종류가 없음"},
        411: {"description": "Content-Length 없음"},
        413: {"description": "본문·파일이 상한(document_pdf_max_mb)보다 큼"},
        422: {"description": "file 파트 없음 · PDF 가 아님"},
        501: {"description": "FILE_STORE_ROOT 미구성"},
    },
)
async def put_document(
    type_id: str,
    request: Request,
    response: Response,
    session: DbSession,
    caller: InstructorCaller,
) -> DocumentOut:
    settings: Settings = request.app.state.settings
    kind = await document_type_or_404(session, type_id)
    max_bytes = settings.document_pdf_max_mb * MIB
    check_length(request, max_bytes)
    async with request.form(max_files=1, max_fields=1) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise invalid("file", "file 파트(PDF)가 필요합니다")
        root = _store_root(settings)
        data = await upload.read(max_bytes + 1)
    try:
        _, created = await documents.put_document(
            session,
            root=root,
            max_bytes=max_bytes,
            instructor_id=caller.id,
            type_id=kind.id,
            data=data,
        )
    except files_attachments.PdfRejected as exc:
        if exc.reason == "too_large":
            raise AppError(
                413, f"PDF 는 {settings.document_pdf_max_mb}MB 까지입니다"
            ) from None
        raise invalid("file", "PDF 파일이 아닙니다") from None
    found = await crud_document.get_document_file(session, caller.id, kind.id)
    if found is None:  # 방금 넣은 행이다
        raise RuntimeError(f"강사 {caller.id} 의 서류 {kind.id} 를 다시 못 읽었다")
    doc, stored = found
    if not created:
        response.status_code = 200
    return DocumentOut(
        type_id=kind.id,
        name=kind.name,
        required=kind.required,
        submitted_at=doc.submitted_at,
        size=stored.size,
        href=href_for(stored.key),
    )


@router.delete(
    "/me/documents/{type_id}",
    status_code=204,
    response_class=Response,
    responses={404: {"description": "서류 종류가 없음 · 제출한 서류가 없음"}},
)
async def delete_document(
    type_id: str, session: DbSession, caller: InstructorCaller
) -> Response:
    """서류 행과 그 stored_file 행을 지운다. 바이트는 gc 몫이다."""
    kind = await document_type_or_404(session, type_id)
    if not await documents.remove_document(
        session, instructor_id=caller.id, type_id=kind.id
    ):
        raise NotFound("제출한 서류가 없습니다")
    return Response(status_code=204)


@router.get(
    "/admin/instructors/{instructor_id}/documents/{type_id}",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "강사·서류 종류가 없음 · 제출한 서류가 없음"},
        501: {"description": "FILE_STORE_ROOT 미구성"},
    },
)
async def view_document(
    instructor_id: int,
    type_id: str,
    request: Request,
    session: DbSession,
    caller: AdminCaller,
) -> FileResponse:
    settings: Settings = request.app.state.settings
    await instructor_or_404(session, caller, instructor_id)
    kind = await document_type_or_404(session, type_id)
    found = await crud_document.get_document_file(session, instructor_id, kind.id)
    if found is None:
        raise NotFound("제출한 서류가 없습니다")
    root = _store_root(settings)
    doc, stored = found
    path = path_for(root, stored.sha256)
    if not path.is_file():
        # 행은 있는데 바이트가 없다: 서버 쪽 불일치. 내부 경로는 로그에도 응답에도 싣지 않는다
        log.error(
            "파일 바이트 없음: stored_file id %s · sha256 %s…",
            stored.id,
            stored.sha256[:12],
        )
        raise AppError(
            500, "파일을 읽지 못했습니다", title="서버 오류", type="/problems/internal"
        )
    await insert_audit(
        session,
        actor=f"admin:{caller.id}",
        action="instructor_document.view",
        target_type="instructor_document",
        target_id=str(doc.id),
        detail={"instructor_id": instructor_id, "type_id": kind.id},
    )
    return FileResponse(
        path,
        media_type=stored.content_type,
        headers=SAFE_HEADERS,
        filename=f"{instructor_id}-{kind.id}.pdf",
    )
