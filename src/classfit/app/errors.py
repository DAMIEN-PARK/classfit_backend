"""오류 본문은 하나: application/problem+json {type, title, status, detail, instance, …}.

처리기 다섯: 우리 오류(AppError) · 도메인 오류(DomainError) · Starlette HTTP · 요청 검증 422 · 마지막 그물 500.
401 에는 WWW-Authenticate: Bearer. 422 는 violations[{loc, msg, type}].
pydantic.ValidationError 는 전역 처리기에 걸지 않는다 — 응답 모델 버그까지 422 가 되어 서버 버그가 손님 잘못처럼 보인다.
토큰 네임스페이스(TOKEN_PATH_RE — /v1/ax/<토큰> · /v1/admin/links/<토큰>)는 instance·로그 경로에 {token} 을 쓰고 응답은
Cache-Control: no-store 다. 500 로그와 uvicorn.error 는 TokenRedactFilter 가 값 모양 토큰을 가린다(T9a 결정 xxv).
"""

from __future__ import annotations

import logging
import re
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from classfit.core.errors import DomainError

# 경로에 토큰이 오는 네임스페이스. 앵커 없이 접두 뒤 세그먼트 하나 전체다 — 32자가 아닌 기형 토큰 · 뒤에 붙은
# :revoke·/extra · 프록시 접두(/api/v1/ax/…)도 그 세그먼트를 가린다. 두 접두 밖에 온 토큰은 가리지 못한다
TOKEN_PATH_RE = re.compile(r"(/v1/ax/|/v1/admin/links/)[^/:]+")
# 로그 글자 속 값 모양 토큰(진단 링크 token_urlsafe(24) = 32자). 31·33자 글자는 건드리지 않는다
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32}(?![A-Za-z0-9_-])")
_FORMATTER = logging.Formatter()


def is_token_path(scope: Scope) -> bool:
    """토큰 네임스페이스 요청인가. problem() 과 요청 기록 미들웨어가 같이 쓰는 서술어 하나."""
    return TOKEN_PATH_RE.search(scope["path"]) is not None


def request_path(scope: Scope) -> str:
    """로그·instance 에 남기는 경로. 토큰 세그먼트만 {token} 으로 바꾸고 나머지는 그대로, 네임스페이스 밖은 실제 경로."""
    return TOKEN_PATH_RE.sub(r"\1{token}", scope["path"], count=1)


def redact(text: str) -> str:
    return TOKEN_RE.sub("{token}", text)


class TokenRedactFilter(logging.Filter):
    """로그 레코드의 값 모양 토큰을 {token} 으로 가린다(예외 글자 · DB DETAIL · SQLAlchemy parameters).

    메시지는 치환이 생겼을 때만 바꾼다 — args 를 늘 지우면 uvicorn ColourizedFormatter 의 color_message 재포맷이 깨진다.
    트레이스백은 지금 글자로 만들어 가린 뒤 exc_text 에 두고 exc_info 를 지운다(Formatter 는 exc_text 를 그대로 붙인다).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        if record.exc_info:
            record.exc_text = redact(_FORMATTER.formatException(record.exc_info))
            record.exc_info = None
        return True


log = logging.getLogger("classfit.errors")
log.addFilter(TokenRedactFilter())

PROBLEM_JSON = "application/problem+json"
# problem+json 본문의 예약 키. 예외의 extra 에 섞여 들어오면 버린다(TypeError 로 500 이 되거나 본문을 덮어쓰지 않게).
RESERVED_KEYS = frozenset({"type", "title", "status", "detail", "instance", "headers"})

# DomainError.kind → (status, type slug)
_DOMAIN_STATUS: dict[str, int] = {
    "not_found": 404,
    "forbidden": 403,
    "conflict": 409,
    "gone": 410,
    "not_configured": 501,
    "unavailable": 503,
}


class AppError(Exception):
    """app 층이 직접 던지는 HTTP 오류(인증 401, 자격 403 등)."""

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        title: str | None = None,
        type: str | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.title = title or HTTPStatus(status).phrase
        self.type = type or _slug(status)
        self.headers = headers or {}
        self.extra = extra


def unauthorized(detail: str = "인증이 필요합니다") -> AppError:
    return AppError(401, detail, headers={"WWW-Authenticate": "Bearer"})


def forbidden(detail: str) -> AppError:
    return AppError(403, detail)


def problem(
    request: Request,
    *,
    status: int,
    detail: str | None = None,
    title: str | None = None,
    type: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type or _slug(status),
        "title": title or HTTPStatus(status).phrase,
        "status": status,
        "instance": request_path(request.scope),
    }
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    hdrs = dict(headers or {})
    if status == 401:
        hdrs.setdefault("WWW-Authenticate", "Bearer")
    if is_token_path(request.scope):
        # 바깥 ServerErrorMiddleware 가 보내는 500 은 요청 기록 미들웨어가 못 보므로 여기서도 단다(set — 하나만)
        hdrs["Cache-Control"] = "no-store"
    return JSONResponse(body, status_code=status, headers=hdrs, media_type=PROBLEM_JSON)


def _extras(extra: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in extra.items() if k not in RESERVED_KEYS}


def _slug(status: int) -> str:
    return "/problems/" + HTTPStatus(status).phrase.lower().replace(" ", "-")


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    return problem(
        request,
        status=exc.status,
        detail=exc.detail,
        title=exc.title,
        type=exc.type,
        headers=exc.headers,
        **_extras(exc.extra),
    )


async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
    status = _DOMAIN_STATUS.get(exc.kind, 409)
    return problem(request, status=status, detail=exc.message, type="/problems/" + exc.kind, **_extras(exc.extra))


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem(request, status=exc.status_code, detail=detail, headers=exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    violations = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return problem(
        request,
        status=422,
        title="요청 검증 실패",
        detail="요청 본문·경로·질의 값이 모양에 맞지 않습니다",
        violations=violations,
    )


async def _last_resort(request: Request, exc: Exception) -> JSONResponse:
    log.exception("처리되지 않은 예외: %s %s", request.method, request_path(request.scope))
    return problem(request, status=500, title="서버 오류", detail="서버에서 처리하지 못했습니다")


def _install_uvicorn_filter() -> None:
    """ServerErrorMiddleware 가 500 을 보낸 뒤 다시 던진 예외를 uvicorn 이 uvicorn.error 에 트레이스백으로 찍는다.
    create_app 을 여러 번 불러도(--reload · 시험) 필터는 하나다."""
    target = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, TokenRedactFilter) for f in target.filters):
        target.addFilter(TokenRedactFilter())


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, _domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _last_resort)
    _install_uvicorn_filter()
