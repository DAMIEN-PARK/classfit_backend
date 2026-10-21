"""요청 단위 의존성: 세션(= 트랜잭션), 나중에 인증.

인증 갈래는 도메인 설계 때 넣는다 — 관리자·강사 로그인 / 수강생은 초대코드+이메일(비밀번호 없음) /
진단 링크 토큰(/ax/{token}) / 완전 공개 쓰기(교육 문의). 권한은 타입 별칭(ReadCaller …)으로 건다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def db(request: Request) -> AsyncIterator[AsyncSession]:
    """요청 1개 = 트랜잭션 1개. 핸들러가 정상 종료하면 커밋, 예외면 롤백.

    scope="function": 응답을 보내기 전에 커밋한다(yield 의존성 기본값은 응답 뒤에 닫혀서,
    302 를 따라온 다음 요청이 방금 쓴 것을 못 본다).
    """
    factory = request.app.state.session_factory
    if factory is None:
        raise RuntimeError("미구성: app.state.session_factory 가 없습니다 (lifespan 또는 시험이 채운다)")
    async with factory() as session, session.begin():
        yield session


DbSession = Annotated[AsyncSession, Depends(db, scope="function")]
