"""인증 끝점: POST /v1/auth/admin/login · POST /v1/auth/logout.

로그인 실패·잠김은 예외가 아니라 problem() 을 반환한다. 그래야 db() 가 정상 종료로 보고 auth_attempt 행을
커밋한다(Design 5절 7). raise 로 바꾸면 그 행이 롤백되어 잠금이 영영 걸리지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from classfit.app.deps import CurrentPrincipal, DbSession, bearer_token
from classfit.app.errors import problem
from classfit.core.config import Settings
from classfit.schemas.auth import AdminLoginIn, TokenOut
from classfit.service.auth import login, sessions

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/admin/login",
    response_model=TokenOut,
    responses={
        401: {"description": "아이디 또는 비밀번호가 틀림(없는 아이디와 같은 응답)"},
        429: {"description": "같은 (계정, 클라이언트 주소)의 실패가 많아 잠김"},
    },
)
async def admin_login(
    body: AdminLoginIn, request: Request, session: DbSession
) -> TokenOut | JSONResponse:
    settings: Settings = request.app.state.settings
    client = request.client.host if request.client else "unknown"
    result = await login.admin_login(
        session, settings, login_id=body.login_id, password=body.password, client=client
    )
    if result.outcome == "locked":
        return problem(
            request,
            status=429,
            detail="로그인 실패가 많아 잠시 막혔습니다. 나중에 다시 시도하세요",
            headers={"Retry-After": str(settings.login_lock_minutes * 60)},
        )
    if result.outcome == "failed" or result.token is None or result.expires_at is None:
        return problem(
            request, status=401, detail="아이디 또는 비밀번호가 맞지 않습니다"
        )
    return TokenOut(access_token=result.token, expires_at=result.expires_at)


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request, session: DbSession, _: CurrentPrincipal) -> Response:
    await sessions.revoke(session, bearer_token(request))
    return Response(status_code=204)
