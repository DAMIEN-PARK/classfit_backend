"""GET /v1/files/{key} — Bearer 인증과 범위 판정 뒤 앱이 바이트를 준다(ADR-003 결정 1·3).

판정 순서: 401(bearer_principal) → 501(FILE_STORE_ROOT 미구성) → 404(행 없음 · 등록 안 된 owner_kind)
→ 403(범위 밖) → 200. FILE_SIGNING_KEY 는 예약 칸이라 보지 않는다.
디스크 경로는 행의 sha256 으로만 만든다(key 는 경로에 쓰지 않는다).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from classfit.app.deps import CurrentPrincipal, DbSession
from classfit.core.config import Settings
from classfit.core.errors import Forbidden, NotConfigured, NotFound
from classfit.crud.scope import OWNER_KINDS
from classfit.crud.stored_file import get_by_key
from classfit.service.files.store import path_for

router = APIRouter(prefix="/v1", tags=["files"])

NO_STORE = {"Cache-Control": "private, no-store"}


@router.get(
    "/files/{key}",
    response_class=FileResponse,
    responses={200: {"content": {"application/octet-stream": {}}}},
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
    row = await get_by_key(session, key)
    judge = OWNER_KINDS.get(row.owner_kind) if row is not None else None
    # 행 없음과 등록 안 된 종류는 같은 404 다. 등록 안 된 종류는 범위 판정 없이 열리지 않는다(기본 거절)
    if row is None or judge is None:
        raise NotFound("파일이 없습니다")
    if not await judge(session, principal, row.owner_id):
        raise Forbidden("이 파일을 볼 권한이 없습니다")
    return FileResponse(
        path_for(root, row.sha256),
        media_type=row.content_type,
        headers=NO_STORE,
    )
