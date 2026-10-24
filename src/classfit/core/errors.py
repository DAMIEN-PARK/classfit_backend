"""도메인 오류. service·crud 가 던지고 app/errors.py 가 HTTP 상태로 바꾼다. 이 모듈은 HTTP 를 모른다.

kind → 상태 (app 에서 매핑):
  not_found 404 · forbidden 403(남의 회사 자원도 404 대신 403) · conflict 409(상태 충돌)
  gone 410(파기됨) · not_configured 501(미구성) · unavailable 503(지금 확인 불가)
  too-many-requests 429(하이픈 — 기존 로그인 잠김 429 의 slug 와 통일, T9b 결정 xxiv)
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    kind: str = "conflict"

    def __init__(self, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra


class NotFound(DomainError):
    kind = "not_found"


class Forbidden(DomainError):
    kind = "forbidden"


class Conflict(DomainError):
    kind = "conflict"


class Gone(DomainError):
    kind = "gone"


class NotConfigured(DomainError):
    kind = "not_configured"


class Unavailable(DomainError):
    kind = "unavailable"


class TooManyRequests(DomainError):
    kind = "too-many-requests"
