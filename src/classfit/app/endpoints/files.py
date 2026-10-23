"""GET /v1/files/{key} — Bearer 인증과 범위 판정 뒤 앱이 바이트를 준다(ADR-003 결정 1·3).

판정 순서: 401(bearer_principal) → 501(FILE_STORE_ROOT 미구성) → 404(key 모양 틀림 · 행 없음 · 등록 안 된 owner_kind,
모두 같은 본문) → 403(범위 밖) → 501(HTML 패키지, T6) → 200. FILE_SIGNING_KEY 는 예약 칸이라 보지 않는다.
HTML 패키지(content_type 이 rules.attachment 의 고정값)는 1차에 보관만 하고 열지 않는다(T6 결정 ix). 범위 판정 뒤라
남의 강의 수강생은 403 을 받는다(있는지 흘리지 않는다). 주체·owner_kind 를 가리지 않는다.
디스크 경로는 행의 sha256 으로만 만든다(key 는 경로에 쓰지 않는다). 바이트는 내려받기(attachment)로만 준다.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from classfit.app.deps import CurrentPrincipal, DbSession
from classfit.app.errors import AppError
from classfit.core.config import Settings
from classfit.core.errors import Forbidden, NotConfigured, NotFound
from classfit.crud.scope import OWNER_KINDS
from classfit.crud.stored_file import get_by_key
from classfit.service.files.store import path_for
from classfit.service.rules.attachment import HTML_PACKAGE_CONTENT_TYPE

log = logging.getLogger("classfit.files")

router = APIRouter(prefix="/v1", tags=["files"])

# key 는 crud.stored_file 이 token_urlsafe 로 만든다. 이 모양 밖(NUL 등)은 DB 를 치지 않고 같은 404
_KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")
# 올린 사람이 정한 content_type 을 브라우저가 고쳐 읽거나 그 자리에서 열지 않게
SAFE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


@router.get(
    "/files/{key}",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/octet-stream": {}}},
        501: {
            "description": "FILE_STORE_ROOT 미구성(/problems/not_configured)"
            " · HTML 패키지(/problems/not-implemented, 1차는 보관만)"
        },
    },
)
async def get_file(
    key: str,
    request: Request,
    session: DbSession,
    principal: CurrentPrincipal,
) -> FileResponse:
    settings: Settings = request.app.state.settings
    root = settings.file_store_root
    if root is None:
        missing = settings.missing("file_store_root")
        raise NotConfigured("파일 저장소가 구성되지 않았습니다", missing=missing)
    row = await get_by_key(session, key) if _KEY.fullmatch(key) else None
    judge = OWNER_KINDS.get(row.owner_kind) if row is not None else None
    # 행 없음과 등록 안 된 종류는 같은 404 다. 등록 안 된 종류는 범위 판정 없이 열리지 않는다(기본 거절)
    if row is None or judge is None:
        raise NotFound("파일이 없습니다")
    if not await judge(session, principal, row.owner_id):
        raise Forbidden("이 파일을 볼 권한이 없습니다")
    if row.content_type == HTML_PACKAGE_CONTENT_TYPE:
        raise AppError(
            501,
            "HTML 패키지는 1차에 열지 않습니다(보관만)",
            type="/problems/not-implemented",
        )
    path = path_for(root, row.sha256)
    if not path.is_file():
        # 행은 있는데 바이트가 없다: 서버 쪽 불일치. 내부 경로는 로그에도 응답에도 싣지 않는다
        log.error(
            "파일 바이트 없음: stored_file id %s · sha256 %s…", row.id, row.sha256[:12]
        )
        raise AppError(
            500, "파일을 읽지 못했습니다", title="서버 오류", type="/problems/internal"
        )
    return FileResponse(
        path,
        media_type=row.content_type,
        headers=SAFE_HEADERS,
        filename=row.key,
    )
