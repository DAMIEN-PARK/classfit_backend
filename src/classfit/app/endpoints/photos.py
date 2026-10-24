"""교육 사진 끝점(T7 계획 결정 i·ii·vii·viii·ix·xi·xii·xxi·xxii). 강사 셋(InstructorCaller) · 관리자 넷(AdminCaller).

- POST /v1/me/sessions/{session_id}/photos(폼 file · caption?) 판정 순서:
  401 → 403(InstructorCaller) → 422(경로 id) → 404(세션) → 403(내 세션 아님) → 409(예정 차시 · 일차 미정, 잠그지 않은
  미리 판정) → 411 · 413(Content-Length 가 이미지 상한 + 1MiB 초과) → 400(깨진 폼, Starlette) → 422(caption·file 모양)
  → 501(FILE_STORE_ROOT 미구성) → 422(머리 8KiB 로 확장자·첫 바이트 — png·jpg·jpeg·webp 만) → 413(실제 크기) → 201.
  종류 판정은 T6 service.rules.attachment.classify 이고 상한은 ATTACHMENT_IMAGE_MAX_MB 를 같이 쓴다. content_type 은
  받은 값이 아니라 확장자 표의 값이다. 한 요청에 한 장, 개수 상한·크기 변환은 없다.
- PATCH·DELETE /v1/me/photos/{photo_id}: 담당 강사 ∧ 내가 올린 사진만이다(남의 사진 · 담당이 아닌 세션 403). 같은 설명이면
  200 · audit 없음. 지우면 그 파일 행도 지운다(바이트는 gc 몫).
- GET /v1/admin/photos: 모아보기. 키셋 커서 {items, next_cursor, has_more}, 올린 시각(created_at, id) 내림차순 하나다
  (sort 없음, 결정 xi). 필터 company(강의 고객사와 같음) · course_id · q(설명 · 세션 제목 · 강의 제목 · 고객사 · 올린 강사
  이름, % _ 는 글자) · new_only(확인 표시 없음). 깨진 커서(photo_views.InvalidCursor)만 422 loc
  ["query", "cursor"] 다 — 다른 ValueError 는 커서 422 로 가리지 않는다(T6 my_course_views 꼴).
- POST /v1/admin/photos:download {ids}: 바이트가 아니라 {items:[{id, href, filename}], missing} 이다. 바이트는 파일 끝점
  으로만 준다. POST /v1/admin/photos:mark-seen {ids}: 준 사진 가운데 확인 표시 없는 것만 표시한다(audit 없음).
- DELETE /v1/admin/photos/{photo_id}: 관리자는 전부 지운다. 관리자 올리기·설명 고치기는 1차에 없다(결정 viii).
- 폼 매개변수를 선언하지 않는다 — 인증·세션 판정 뒤에 폼을 읽는다(T2b 첨부 끝점과 같은 까닭). 공개 칸은 없다(r3 §7-7).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.datastructures import FormData, UploadFile

from classfit.app.deps import AdminCaller, DbSession, IdPath, InstructorCaller, Today
from classfit.app.endpoints.admin_instructors import query_text
from classfit.app.errors import AppError
from classfit.app.upload import MIB, check_length, invalid
from classfit.core.config import Settings
from classfit.core.errors import NotConfigured
from classfit.schemas.course import DB_ID_LIMIT
from classfit.schemas.page import Page
from classfit.schemas.photo import (
    GalleryPhotoOut,
    MarkSeenOut,
    MyPhotoOut,
    PhotoDownloadItemOut,
    PhotoDownloadOut,
    PhotoFormIn,
    PhotoIdsIn,
    PhotoPatchIn,
    PhotoSeenIn,
)
from classfit.service.files import photo_views, photos
from classfit.service.rules.attachment import HEAD_BYTES, FileRejected, classify

router = APIRouter(prefix="/v1", tags=["photos"])

_IMAGE = "image"
_FORM_DOC: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "caption": {"type": "string", "maxLength": 200},
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "확장자로 종류를 정한다: .png .jpg .jpeg .webp",
                        },
                    },
                }
            }
        },
    }
}
_SESSION = {
    403: {"description": "내 세션이 아님(남의 세션 · 미배정)"},
    404: {"description": "세션이 없음"},
}
_MINE = {
    403: {"description": "내가 올린 사진이 아님 · 지금 내 세션이 아님"},
    404: {"description": "사진이 없음"},
}


NOT_IMAGE = "이미지 파일이 아닙니다(png·jpg·jpeg·webp 만 받습니다)"


def _rejected(exc: FileRejected) -> Exception:
    """too_large → 413. 이미지 확장자인데 첫 바이트가 틀리면 mismatch 문구, 그 밖(모르는 확장자 · 이미지가 아닌 종류 —
    그 종류의 첫 바이트가 틀린 경우도)은 사진 자리에서 받지 않는 종류다(결정 vii, reason unknown_type 꼴)."""
    if exc.reason == "too_large":
        return AppError(413, f"사진은 {exc.limit_mb}MB 까지입니다")
    if exc.reason == "mismatch" and exc.kind == _IMAGE:
        return invalid("file", "파일 내용이 확장자와 맞지 않습니다")
    return invalid("file", NOT_IMAGE)


def _form_fields(form: FormData) -> PhotoFormIn:
    """caption 하나만 읽는다(다른 글자 칸은 무시)."""
    raw: dict[str, str] = {}
    value = form.get("caption")
    if value is not None:
        if not isinstance(value, str):
            raise invalid("caption", "글자 필드여야 합니다")
        raw["caption"] = value
    try:
        return PhotoFormIn.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(
            [
                {"loc": ("body", *e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ]
        ) from None


@router.post(
    "/me/sessions/{session_id}/photos",
    response_model=MyPhotoOut,
    status_code=201,
    openapi_extra=_FORM_DOC,
    responses={
        **_SESSION,
        400: {"description": "깨진 폼(boundary 없음 · 파트 수 초과)"},
        409: {"description": "예정 차시 · 일차 미정 세션(지난 차시에만 올린다)"},
        411: {"description": "Content-Length 없음"},
        413: {"description": "본문·파일이 이미지 상한(attachment_image_max_mb)보다 큼"},
        422: {
            "description": "caption·file 모양 · 이미지가 아님 · 내용이 확장자와 다름"
        },
        501: {"description": "FILE_STORE_ROOT 미구성"},
    },
)
async def upload_my_photo(
    session_id: IdPath,
    request: Request,
    session: DbSession,
    caller: InstructorCaller,
    today: Today,
) -> MyPhotoOut:
    settings: Settings = request.app.state.settings
    await photos.writable_session(
        session, instructor_id=caller.id, session_id=session_id, today=today
    )
    max_bytes = settings.attachment_image_max_mb * MIB
    check_length(request, max_bytes)
    async with request.form(max_files=1, max_fields=2) as form:
        fields = _form_fields(form)
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
        if kind != _IMAGE:
            raise _rejected(FileRejected("unknown_type", kind=kind))
        await upload.seek(0)
        data = await upload.read(max_bytes + 1)
        try:
            row, stored = await photos.add_my_photo(
                session,
                root=root,
                max_bytes=max_bytes,
                instructor_id=caller.id,
                session_id=session_id,
                caption=fields.caption,
                filename=upload.filename,
                data=data,
                today=today,
                actor=f"instructor:{caller.id}",
            )
        except FileRejected as exc:
            raise _rejected(exc) from None
    view = await photo_views.photo_view(session, caller, (row, stored.key, stored.size))
    return MyPhotoOut.model_validate(view, from_attributes=True)


@router.patch("/me/photos/{photo_id}", response_model=MyPhotoOut, responses=_MINE)
async def patch_my_photo(
    photo_id: IdPath, body: PhotoPatchIn, session: DbSession, caller: InstructorCaller
) -> MyPhotoOut:
    item = await photos.patch_my_photo(
        session,
        instructor_id=caller.id,
        photo_id=photo_id,
        caption=body.caption,
        actor=f"instructor:{caller.id}",
    )
    view = await photo_views.photo_view(session, caller, item)
    return MyPhotoOut.model_validate(view, from_attributes=True)


@router.delete(
    "/me/photos/{photo_id}",
    status_code=204,
    response_class=Response,
    responses=_MINE,
)
async def delete_my_photo(
    photo_id: IdPath, session: DbSession, caller: InstructorCaller
) -> Response:
    await photos.delete_my_photo(
        session,
        instructor_id=caller.id,
        photo_id=photo_id,
        actor=f"instructor:{caller.id}",
    )
    return Response(status_code=204)


# ── 관리자


@router.get("/admin/photos", response_model=Page[GalleryPhotoOut])
async def list_photos(
    session: DbSession,
    caller: AdminCaller,
    company: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    course_id: Annotated[int | None, Query(ge=1, lt=DB_ID_LIMIT)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    new_only: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[GalleryPhotoOut]:
    try:
        page = await photo_views.gallery(
            session,
            caller,
            company=query_text(company, "company"),
            course_id=course_id,
            q=query_text(q),
            new_only=new_only,
            cursor=cursor,
            limit=limit,
        )
    except photo_views.InvalidCursor:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "cursor"),
                    "msg": "깨진 커서입니다",
                    "type": "value_error",
                }
            ]
        ) from None
    return Page[GalleryPhotoOut](
        items=[
            GalleryPhotoOut.model_validate(i, from_attributes=True) for i in page.items
        ],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post("/admin/photos:download", response_model=PhotoDownloadOut)
async def download_photos(
    body: PhotoIdsIn, session: DbSession, caller: AdminCaller
) -> PhotoDownloadOut:
    """내려받을 이름과 주소의 목록. 없거나 그 사이 지워진 사진은 missing 에 담는다."""
    items, missing = await photo_views.download_list(session, caller, ids=body.ids)
    return PhotoDownloadOut(
        items=[
            PhotoDownloadItemOut.model_validate(i, from_attributes=True) for i in items
        ],
        missing=missing,
    )


@router.post("/admin/photos:mark-seen", response_model=MarkSeenOut)
async def mark_photos_seen(
    body: PhotoSeenIn, session: DbSession, _: AdminCaller
) -> MarkSeenOut:
    """화면이 본 사진만 받는다(연 뒤 새로 올라온 사진은 새 사진으로 남는다)."""
    return MarkSeenOut(marked=await photo_views.mark_seen(session, ids=body.ids))


@router.delete(
    "/admin/photos/{photo_id}",
    status_code=204,
    response_class=Response,
    responses={404: {"description": "사진이 없음"}},
)
async def delete_photo(
    photo_id: IdPath, session: DbSession, caller: AdminCaller
) -> Response:
    await photos.delete_photo_as_admin(
        session, photo_id=photo_id, actor=f"admin:{caller.id}"
    )
    return Response(status_code=204)
