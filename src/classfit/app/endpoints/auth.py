"""인증 끝점: POST /v1/auth/admin/login · POST /v1/auth/instructor/login · POST /v1/auth/logout.

로그인 실패·잠김은 예외가 아니라 problem() 을 반환한다. 그래야 db() 가 정상 종료로 보고 auth_attempt 행을
커밋한다(Design 5절 7). raise 로 바꾸면 그 행이 롤백되어 잠금이 영영 걸리지 않는다.
강사 로그인(T3 계획 결정 v·viii·xiii)도 같다: 잠김 429 + Retry-After · 틀림(없는 이메일 포함) 401 ·
정지 403 /problems/instructor-suspended(자격은 맞았으니 시도 행은 ok). 대기·반려 강사도 로그인한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from classfit.app.deps import CurrentPrincipal, DbSession, bearer_token, no_store
from classfit.app.errors import problem
from classfit.core.config import Settings
from classfit.schemas.auth import AdminLoginIn, TokenOut
from classfit.schemas.instructor import InstructorLoginIn
from classfit.service.auth import login, sessions

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/admin/login",
    response_model=TokenOut,
    dependencies=[Depends(no_store)],
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


@router.post(
    "/instructor/login",
    response_model=TokenOut,
    dependencies=[Depends(no_store)],
    responses={
        401: {"description": "이메일 또는 비밀번호가 틀림(없는 이메일과 같은 응답)"},
        403: {"description": "정지된 강사(/problems/instructor-suspended)"},
        429: {"description": "같은 (이메일, 클라이언트 주소)의 실패가 많아 잠김"},
    },
)
async def instructor_login(
    body: InstructorLoginIn, request: Request, session: DbSession
) -> TokenOut | JSONResponse:
    settings: Settings = request.app.state.settings
    client = request.client.host if request.client else "unknown"
    result = await login.instructor_login(
        session, settings, email=body.email, password=body.password, client=client
    )
    if result.outcome == "locked":
        return problem(
            request,
            status=429,
            detail="로그인 실패가 많아 잠시 막혔습니다. 나중에 다시 시도하세요",
            headers={"Retry-After": str(settings.login_lock_minutes * 60)},
        )
    if result.outcome == "suspended":
        return problem(
            request,
            status=403,
            type="/problems/instructor-suspended",
            detail="정지된 강사 계정입니다. 운영자에게 문의하세요",
        )
    if result.outcome == "failed" or result.token is None or result.expires_at is None:
        return problem(
            request, status=401, detail="이메일 또는 비밀번호가 맞지 않습니다"
        )
    return TokenOut(access_token=result.token, expires_at=result.expires_at)


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request, session: DbSession, _: CurrentPrincipal) -> Response:
    await sessions.revoke(session, bearer_token(request))
    return Response(status_code=204)
