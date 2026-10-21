"""오류 본문은 하나: application/problem+json {type, title, status, detail, instance, …}.

처리기 다섯: 우리 오류(AppError) · 도메인 오류(DomainError) · Starlette HTTP · 요청 검증 422 · 마지막 그물 500.
401 에는 WWW-Authenticate: Bearer. 422 는 violations[{loc, msg, type}].
pydantic.ValidationError 는 전역 처리기에 걸지 않는다 — 응답 모델 버그까지 422 가 되어 서버 버그가 손님 잘못처럼 보인다.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from classfit.core.errors import DomainError

log = logging.getLogger("classfit.errors")

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
        "instance": request.url.path,
    }
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    hdrs = dict(headers or {})
    if status == 401:
        hdrs.setdefault("WWW-Authenticate", "Bearer")
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
    log.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
    return problem(request, status=500, title="서버 오류", detail="서버에서 처리하지 못했습니다")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, _domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _last_resort)
