"""요청 단위 의존성: 세션(= 트랜잭션) · 인증 주체 · 오늘 날짜.

- 인증은 `Authorization: Bearer <불투명 토큰>` 하나다(관리자·강사·수강생 공용 auth_session).
  헤더 없음·모양 틀림·없는 토큰·폐기·만료는 전부 401 + WWW-Authenticate: Bearer.
- 권한은 타입 별칭으로 건다: CurrentPrincipal(로그인만) · AdminCaller(관리자, 아니면 403) ·
  LearnerCaller(수강생, 아니면 403). 수강생 주체는 토큰의 강의 하나에 묶인다(ADR-002 결정 1).
  LearnerCaller 는 learner 행을 찾지 않는다. 세션 행의 (principal_id, course_id) 가 주체다.
- 날짜는 Today(Asia/Seoul) 한 곳에서 받는다. 시험은 app.dependency_overrides[today] 로 주입한다.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.app.errors import forbidden, unauthorized
from classfit.core.clock import today_kst
from classfit.service.auth.sessions import Principal, authenticate

# token_urlsafe 글자만, 길이 상한. 모양이 틀리면 DB 를 보지 않고 401
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}")


async def db(request: Request) -> AsyncIterator[AsyncSession]:
    """요청 1개 = 트랜잭션 1개. 핸들러가 정상 종료하면 커밋, 예외면 롤백.

    scope="function": 응답을 보내기 전에 커밋한다(yield 의존성 기본값은 응답 뒤에 닫혀서,
    302 를 따라온 다음 요청이 방금 쓴 것을 못 본다).
    """
    factory = request.app.state.session_factory
    if factory is None:
        raise RuntimeError(
            "미구성: app.state.session_factory 가 없습니다 (lifespan 또는 시험이 채운다)"
        )
    async with factory() as session, session.begin():
        yield session


DbSession = Annotated[AsyncSession, Depends(db, scope="function")]


def bearer_token(request: Request) -> str:
    """Authorization 헤더의 토큰 글자. 헤더가 없거나 모양이 틀리면 401."""
    header = request.headers.get("authorization")
    if header is None:
        raise unauthorized()
    scheme, _, token = header.strip().partition(" ")
    if scheme.lower() != "bearer" or not _TOKEN.fullmatch(token.strip()):
        raise unauthorized("Authorization 헤더 모양이 틀렸습니다 (Bearer <토큰>)")
    return token.strip()


async def bearer_principal(request: Request, session: DbSession) -> Principal:
    principal = await authenticate(session, bearer_token(request))
    if principal is None:
        raise unauthorized("토큰이 없거나 폐기·만료됐습니다")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(bearer_principal)]


async def require_admin(principal: CurrentPrincipal) -> Principal:
    if principal.type != "admin":
        raise forbidden("관리자만 할 수 있습니다")
    return principal


AdminCaller = Annotated[Principal, Depends(require_admin)]


async def require_learner(principal: CurrentPrincipal) -> Principal:
    if principal.type != "learner" or principal.course_id is None:
        raise forbidden("수강생만 할 수 있습니다")
    return principal


LearnerCaller = Annotated[Principal, Depends(require_learner)]


def today() -> date:
    return today_kst()


Today = Annotated[date, Depends(today)]
