"""강사 첨부 끝점(InstructorCaller, T6 계획 결정 i·ii·iii·iv·v·vii·viii·xi·xii).

- 쓰기는 그 세션의 현재 담당 강사만이다(남의 세션·미배정 403). 그 세션의 첨부는 전부 — 관리자가 넣은 것과 기본
  강의안 사본도 — 고치고 지운다(결정 v). 쓰기마다 audit 1행(actor instructor:<id>, service.files). 판정은 404(없음)
  → 403(내 세션 아님)이고 경로 id 는 IdPath(1 ≤ id < 2**63, 밖이면 DB 를 치지 않고 422 loc ["path", <이름>]).
- GET /v1/me/sessions/{session_id}/attachments: 내 세션의 첨부 전부((sort, id) 순, 공개 전 포함)를 한 쪽에 준다
  (has_more 거짓). 항목은 T2b 첨부 칸 + origin 이다.
- POST /v1/me/sessions/{session_id}/attachments(폼 title·description?·file) 판정 순서:
  401 → 403(InstructorCaller) → 422(경로 id) → 404(세션) → 403(내 세션 아님) → 409(세션당 ATTACHMENTS_MAX, limit)
  → 411 · 413(Content-Length, 종류별 상한 중 가장 큰 값 + 1MiB) → 400(깨진 폼, Starlette) → 422(title·file 모양)
  → 501(FILE_STORE_ROOT 미구성) → 422(머리 8KiB 로 확장자·첫 바이트) → 413(그 종류 상한) → 201.
  종류는 파일 이름의 확장자로 정하고(service.rules.attachment.classify) 머리가 통과해야 그 종류 상한 + 1바이트까지만
  읽는다. content_type 은 받은 값이 아니라 확장자 표의 값이다.
- POST …/attachments:link 본문 {title, url, description?}: 201. 상한은 파일과 같이 센다.
- PATCH /v1/me/attachments/{attachment_id} 본문 {title?, description?, url?, position?}: url 은 link 만(아니면 409).
  position 은 목록 자리이고 세션의 순서를 다시 매긴다. 같은 값이면 200 · audit 없음.
- POST /v1/me/attachments/{attachment_id}:replace(폼 file 하나): 같은 행의 파일만 바꾼다(id·제목·자리 그대로, 옛 파일
  행은 같은 트랜잭션에서 지워 옛 href 는 404). 같은 종류만(아니면 422 file), link 는 409. origin 은 비운다.
- DELETE /v1/me/attachments/{attachment_id}: 204. 그 첨부의 파일 행도 지운다(바이트는 gc 몫).
- 폼 매개변수를 선언하지 않는다 — 인증·세션 판정 뒤에 폼을 읽는다(T2b 첨부 끝점과 같은 까닭). 411·413 판정은
  app.upload 의 공용 도우미다(T11 결정 v).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import FormData, UploadFile

from classfit.app.deps import DbSession, IdPath, InstructorCaller
from classfit.app.endpoints.attachments import attachment_out
from classfit.app.errors import AppError
from classfit.app.upload import check_length, invalid
from classfit.core.config import Settings
from classfit.core.errors import Conflict, NotConfigured
from classfit.crud.attachment import AttachmentRow
from classfit.models.attachment import ATTACHMENTS_MAX
from classfit.schemas.my_attachment import (
    MyAttachmentOut,
    MyAttachmentPatchIn,
    MyFileFormIn,
    MyLinkIn,
)
from classfit.schemas.page import Page
from classfit.service.files import my_attachment_edit, my_attachments
from classfit.service.rules.attachment import HEAD_BYTES, FileRejected, classify

router = APIRouter(prefix="/v1/me", tags=["my-attachments"])

_TEXT_FIELDS = ("title", "description")
_FILE = {
    "type": "string",
    "format": "binary",
    "description": "확장자로 종류를 정한다: .pdf · .pptx .docx .xlsx .csv · .zip(HTML 패키지)"
    " · .png .jpg .jpeg .webp",
}


def _form_doc(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "requestBody": {
            "required": True,
            "content": {"multipart/form-data": {"schema": schema}},
        }
    }


_FILE_DOC = _form_doc(
    {
        "type": "object",
        "required": ["title", "file"],
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "description": {"type": "string"},
            "file": _FILE,
        },
    }
)
_REPLACE_DOC = _form_doc(
    {"type": "object", "required": ["file"], "properties": {"file": _FILE}}
)
_SESSION = {
    403: {"description": "내 세션이 아님(남의 세션 · 미배정)"},
    404: {"description": "세션이 없음"},
}
_ATTACHMENT = {
    403: {"description": "내 세션의 첨부가 아님"},
    404: {"description": "첨부가 없음"},
}
_FULL = {409: {"description": f"세션의 첨부가 이미 {ATTACHMENTS_MAX}개(limit 칸)"}}
_BYTES = {
    400: {"description": "깨진 폼(boundary 없음 · 파트 수 초과)"},
    411: {"description": "Content-Length 없음"},
    413: {"description": "본문·파일이 그 종류 상한보다 큼"},
    501: {"description": "FILE_STORE_ROOT 미구성"},
}


def my_attachment_out(item: AttachmentRow) -> MyAttachmentOut:
    """T2b 첨부 칸(href 는 attachment_out 이 단다) + origin."""
    out = attachment_out(item)
    return MyAttachmentOut.model_validate(
        {**out.model_dump(), "origin": item[0].origin}
    )


def _rejected(exc: FileRejected) -> Exception:
    if exc.reason == "too_large":
        return AppError(413, f"이 종류의 파일은 {exc.limit_mb}MB 까지입니다")
    if exc.reason == "kind_changed":
        return invalid("file", "같은 종류의 파일로만 바꿀 수 있습니다")
    if exc.reason == "mismatch":
        return invalid("file", "파일 내용이 확장자와 맞지 않습니다")
    return invalid("file", "받지 않는 파일 종류입니다")


def _form_fields(form: FormData) -> MyFileFormIn:
    """아는 글자 칸만 읽는다(kind 같은 다른 칸은 무시)."""
    raw: dict[str, str] = {}
    for name in _TEXT_FIELDS:
        value = form.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise invalid(name, "글자 필드여야 합니다")
        raw[name] = value
    try:
        return MyFileFormIn.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(
            [
                {"loc": ("body", *e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ]
        ) from None


async def _file_part(
    form: FormData,
    settings: Settings,
    limits: dict[str, int],
    *,
    same_kind: str | None = None,
) -> tuple[Path, str, bytes]:
    """(저장소 루트, 파일 이름, 바이트). 머리만 먼저 읽어 종류를 판정하고 그 종류 상한 + 1바이트까지만 읽는다."""
    upload = form.get("file")
    if not isinstance(upload, UploadFile) or not upload.filename:
        raise invalid("file", "file 파트(파일 이름 포함)가 필요합니다")
    root = settings.file_store_root
    if root is None:
        missing = settings.missing("file_store_root")
        raise NotConfigured("파일 저장소가 구성되지 않았습니다", missing=missing)
    try:
        kind, _ = classify(upload.filename, await upload.read(HEAD_BYTES))
    except FileRejected as exc:
        raise _rejected(exc) from None
    if same_kind is not None and kind != same_kind:
        raise invalid("file", "같은 종류의 파일로만 바꿀 수 있습니다")
    await upload.seek(0)
    return root, upload.filename, await upload.read(limits[kind] + 1)


@router.get(
    "/sessions/{session_id}/attachments",
    response_model=Page[MyAttachmentOut],
    responses=_SESSION,
)
async def list_my_attachments(
    session_id: IdPath, session: DbSession, caller: InstructorCaller
) -> Page[MyAttachmentOut]:
    items = await my_attachments.list_my_attachments(
        session, caller, session_id=session_id
    )
    return Page[MyAttachmentOut](
        items=[my_attachment_out(i) for i in items], next_cursor=None, has_more=False
    )


@router.post(
    "/sessions/{session_id}/attachments",
    response_model=MyAttachmentOut,
    status_code=201,
    openapi_extra=_FILE_DOC,
    responses={
        **_SESSION,
        **_FULL,
        **_BYTES,
        422: {
            "description": "title·file 모양 · 받지 않는 확장자 · 내용이 확장자와 다름"
        },
    },
)
async def upload_my_attachment(
    session_id: IdPath, request: Request, session: DbSession, caller: InstructorCaller
) -> MyAttachmentOut:
    settings: Settings = request.app.state.settings
    await my_attachments.writable_session(
        session, instructor_id=caller.id, session_id=session_id, adding=True
    )
    limits = my_attachments.upload_limits(settings)
    check_length(request, max(limits.values()))
    async with request.form(max_files=1, max_fields=4) as form:
        fields = _form_fields(form)
        root, filename, data = await _file_part(form, settings, limits)
        try:
            row, stored = await my_attachments.add_my_file(
                session,
                root=root,
                max_bytes=limits,
                instructor_id=caller.id,
                session_id=session_id,
                title=fields.title,
                description=fields.description,
                filename=filename,
                data=data,
                actor=f"instructor:{caller.id}",
            )
        except FileRejected as exc:
            raise _rejected(exc) from None
    return my_attachment_out((row, stored.key, stored.size))


@router.post(
    "/sessions/{session_id}/attachments:link",
    response_model=MyAttachmentOut,
    status_code=201,
    responses={**_SESSION, **_FULL},
)
async def add_my_link_attachment(
    session_id: IdPath, body: MyLinkIn, session: DbSession, caller: InstructorCaller
) -> MyAttachmentOut:
    row = await my_attachments.add_my_link(
        session,
        instructor_id=caller.id,
        session_id=session_id,
        title=body.title,
        description=body.description,
        url=body.url,
        actor=f"instructor:{caller.id}",
    )
    return my_attachment_out((row, None, None))


@router.patch(
    "/attachments/{attachment_id}",
    response_model=MyAttachmentOut,
    responses={**_ATTACHMENT, 409: {"description": "link 가 아닌 첨부에 url"}},
)
async def patch_my_attachment(
    attachment_id: IdPath,
    body: MyAttachmentPatchIn,
    session: DbSession,
    caller: InstructorCaller,
) -> MyAttachmentOut:
    item = await my_attachment_edit.patch_my_attachment(
        session,
        instructor_id=caller.id,
        attachment_id=attachment_id,
        changes=body.changes(),
        actor=f"instructor:{caller.id}",
    )
    return my_attachment_out(item)


@router.post(
    "/attachments/{attachment_id}:replace",
    response_model=MyAttachmentOut,
    openapi_extra=_REPLACE_DOC,
    responses={
        **_ATTACHMENT,
        **_BYTES,
        409: {"description": "link 첨부(주소는 PATCH url)"},
        422: {
            "description": "file 모양 · 받지 않는 확장자 · 내용이 확장자와 다름 · 다른 종류"
        },
    },
)
async def replace_my_attachment_file(
    attachment_id: IdPath,
    request: Request,
    session: DbSession,
    caller: InstructorCaller,
) -> MyAttachmentOut:
    settings: Settings = request.app.state.settings
    row, _, _ = await my_attachments.writable_attachment(
        session, instructor_id=caller.id, attachment_id=attachment_id
    )
    kind = row.kind
    if kind == "link":
        raise Conflict(my_attachment_edit.LINK_REPLACE_REFUSED)
    limits = my_attachments.upload_limits(settings)
    check_length(request, limits[kind])
    async with request.form(max_files=1, max_fields=1) as form:
        root, filename, data = await _file_part(form, settings, limits, same_kind=kind)
        try:
            item = await my_attachment_edit.replace_my_file(
                session,
                root=root,
                max_bytes=limits,
                instructor_id=caller.id,
                attachment_id=attachment_id,
                filename=filename,
                data=data,
                actor=f"instructor:{caller.id}",
            )
        except FileRejected as exc:
            raise _rejected(exc) from None
    return my_attachment_out(item)


@router.delete(
    "/attachments/{attachment_id}",
    status_code=204,
    response_class=Response,
    responses=_ATTACHMENT,
)
async def delete_my_attachment(
    attachment_id: IdPath, session: DbSession, caller: InstructorCaller
) -> Response:
    await my_attachments.delete_my_attachment(
        session,
        instructor_id=caller.id,
        attachment_id=attachment_id,
        actor=f"instructor:{caller.id}",
    )
    return Response(status_code=204)
