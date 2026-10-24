"""강사 풀 파일 끝점(InstructorCaller, T4 계획 결정 i·viii·ix·xxi): 고유 과정·역량·커리큘럼 파일 넣기·지우기.

넣기(POST …/files) 판정 순서(결정 viii):
  401 → 403(InstructorCaller) → 대상 판정(service.pool.file_targets: 404 과정·역량·커리큘럼 → 403 AX·남의 것 →
  409 비활성 → 409 소유자당 파일 POOL_FILES_MAX 개, limit 칸 — 바이트를 읽기 전) → Content-Length 없음 411 ·
  상한 + 1MiB 초과 413 → 폼 파싱(파트 수 초과·boundary 없음은 Starlette 가 400) → 422(kind·title·url·file 모양)
  → 501(pdf 인데 FILE_STORE_ROOT 미구성) → 실제 크기 413 → 첫 5바이트 %PDF- 아니면 422 → 201.
- 종류는 pdf·link 둘이다(T2b 첨부와 같다). 상한은 새 설정 없이 attachment_pdf_max_mb 를 쓴다.
- 폼 매개변수를 선언하지 않고 대상 판정 뒤 `async with request.form(max_files=1, max_fields=5)` 로 읽는다.
  411·413 판정과 MIB 는 app.upload 의 공용 도우미다(결정 xxi 기본 · T11 결정 v 에서 공용 모듈로).
- 역량 파일은 경로가 (호출자, pool_id) 라 남의 역량을 가리킬 길이 없다: 내 역량이 없으면 404, 그 풀 과정이
  비활성이면 409 다.
- stored_file.owner_id 는 그 파일 행의 id 이고, /v1/files/{key} 판정은 관리자 ∨ 소유 강사다(OWNER_KINDS 세 종류).
- 지우기(DELETE /v1/me/{pool,capability,curriculum}-files/{id})는 파일 행과 그 stored_file 행을 같은 트랜잭션에서
  지운다(바이트는 gc 몫). 없으면 404, 남의 것이면 403(service.files.pool_files.remove_file). 소유 행이 비활성이어도
  지울 수 있다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData, UploadFile

from classfit.app.deps import DbSession, IdPath, InstructorCaller
from classfit.app.endpoints.pool import file_outs, id_or_404
from classfit.app.errors import AppError
from classfit.app.upload import MIB, check_length, invalid
from classfit.core.config import Settings
from classfit.core.errors import NotConfigured
from classfit.models.pool import POOL_FILES_MAX
from classfit.schemas.attachment import URL_MAX
from classfit.schemas.pool import PoolFileFormIn, PoolFileOut
from classfit.service.auth.sessions import Principal
from classfit.service.files import attachments as files_attachments
from classfit.service.files import pool_files
from classfit.service.pool import file_targets

router = APIRouter(prefix="/v1/me", tags=["pool-files"])

_TEXT_FIELDS = ("kind", "title", "url")
_FORM_SCHEMA = {
    "type": "object",
    "required": ["kind", "title"],
    "properties": {
        "kind": {"type": "string", "enum": ["pdf", "link"]},
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
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
_UPLOAD = {
    400: {"description": "깨진 폼(boundary 없음 · 파트 수 초과)"},
    403: {"description": "AX 과정 · 남의 것"},
    404: {"description": "과정·역량·커리큘럼이 없음"},
    409: {"description": f"사용 중지된 것 · 파일이 이미 {POOL_FILES_MAX}개(limit 칸)"},
    411: {"description": "Content-Length 없음"},
    413: {"description": "본문·파일이 상한(attachment_pdf_max_mb)보다 큼"},
    422: {"description": "kind·title·url·file 모양 · PDF 가 아님"},
    501: {"description": "pdf 인데 FILE_STORE_ROOT 미구성"},
}
_DELETE = {
    403: {"description": "남의 파일"},
    404: {"description": "파일이 없음"},
}


def _form_fields(form: FormData) -> PoolFileFormIn:
    raw: dict[str, str] = {}
    for name in _TEXT_FIELDS:
        value = form.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise invalid(name, "글자 필드여야 합니다")
        raw[name] = value
    try:
        return PoolFileFormIn.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(
            [
                {"loc": ("body", *e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ]
        ) from None


async def _upload(
    request: Request,
    session: AsyncSession,
    caller: Principal,
    target: file_targets.UploadTarget,
) -> PoolFileOut:
    """대상 판정이 끝난 뒤의 공통 부분: 길이 → 폼 → 저장."""
    owner_kind, owner_id = target
    settings: Settings = request.app.state.settings
    max_bytes = settings.attachment_pdf_max_mb * MIB
    check_length(request, max_bytes)
    actor = f"instructor:{caller.id}"
    async with request.form(max_files=1, max_fields=5) as form:
        fields = _form_fields(form)
        if fields.kind == "link":
            if fields.url is None:  # PoolFileFormIn 이 422 로 먼저 막는다
                raise invalid("url", "link 는 url 이 필요합니다")
            row = await pool_files.add_link_file(
                session,
                owner_kind=owner_kind,
                owner_id=owner_id,
                title=fields.title,
                url=fields.url,
                actor=actor,
            )
            return file_outs([(row, None, None)])[0]
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise invalid("file", "pdf 는 file 파트가 필요합니다")
        root = settings.file_store_root
        if root is None:
            missing = settings.missing("file_store_root")
            raise NotConfigured("파일 저장소가 구성되지 않았습니다", missing=missing)
        data = await upload.read(max_bytes + 1)
    try:
        row, stored = await pool_files.add_pdf_file(
            session,
            owner_kind=owner_kind,
            owner_id=owner_id,
            root=root,
            max_bytes=max_bytes,
            title=fields.title,
            data=data,
            actor=actor,
        )
    except files_attachments.PdfRejected as exc:
        if exc.reason == "too_large":
            raise AppError(
                413, f"PDF 는 {settings.attachment_pdf_max_mb}MB 까지입니다"
            ) from None
        raise invalid("file", "PDF 파일이 아닙니다") from None
    return file_outs([(row, stored.key, stored.size)])[0]


@router.post(
    "/own-courses/{pool_id}/files",
    response_model=PoolFileOut,
    status_code=201,
    openapi_extra=_FORM_DOC,
    responses=_UPLOAD,
)
async def add_own_course_file(
    pool_id: str, request: Request, session: DbSession, caller: InstructorCaller
) -> PoolFileOut:
    target = await file_targets.own_course_upload_target(
        session, instructor_id=caller.id, pool_id=id_or_404(pool_id, "과정이 없습니다")
    )
    return await _upload(request, session, caller, target)


@router.post(
    "/capabilities/{pool_id}/files",
    response_model=PoolFileOut,
    status_code=201,
    openapi_extra=_FORM_DOC,
    responses=_UPLOAD,
)
async def add_capability_file(
    pool_id: str, request: Request, session: DbSession, caller: InstructorCaller
) -> PoolFileOut:
    target = await file_targets.capability_upload_target(
        session, instructor_id=caller.id, pool_id=id_or_404(pool_id, "역량이 없습니다")
    )
    return await _upload(request, session, caller, target)


@router.post(
    "/curricula/{curriculum_id}/files",
    response_model=PoolFileOut,
    status_code=201,
    openapi_extra=_FORM_DOC,
    responses=_UPLOAD,
)
async def add_curriculum_file(
    curriculum_id: str, request: Request, session: DbSession, caller: InstructorCaller
) -> PoolFileOut:
    target = await file_targets.curriculum_upload_target(
        session,
        instructor_id=caller.id,
        curriculum_id=id_or_404(curriculum_id, "커리큘럼이 없습니다"),
    )
    return await _upload(request, session, caller, target)


async def _remove(
    session: AsyncSession, caller: Principal, owner_kind: str, file_row_id: int
) -> Response:
    await pool_files.remove_file(
        session,
        owner_kind=owner_kind,
        file_row_id=file_row_id,
        subject=caller,
        actor=f"instructor:{caller.id}",
    )
    return Response(status_code=204)


@router.delete(
    "/pool-files/{pool_course_file_id}",
    status_code=204,
    response_class=Response,
    responses=_DELETE,
)
async def delete_pool_course_file(
    pool_course_file_id: IdPath, session: DbSession, caller: InstructorCaller
) -> Response:
    return await _remove(session, caller, "pool_course_file", pool_course_file_id)


@router.delete(
    "/capability-files/{capability_file_id}",
    status_code=204,
    response_class=Response,
    responses=_DELETE,
)
async def delete_capability_file(
    capability_file_id: IdPath, session: DbSession, caller: InstructorCaller
) -> Response:
    return await _remove(session, caller, "capability_file", capability_file_id)


@router.delete(
    "/curriculum-files/{curriculum_file_id}",
    status_code=204,
    response_class=Response,
    responses=_DELETE,
)
async def delete_curriculum_file(
    curriculum_file_id: IdPath, session: DbSession, caller: InstructorCaller
) -> Response:
    return await _remove(session, caller, "curriculum_file", curriculum_file_id)
