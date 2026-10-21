"""인증 코드 생성의 단일 진입점(Design 5절 8·13). 코드는 issue_email_code() 에서만 만든다.

요청 끝점은 outbox 에 kind="email_code", params={"verification_id": …} 만 쌓는다(평문 코드 없음).
scripts.outbox_preview 가 이 함수를 부른다: 미리 보기는 롤백하고, --apply 는 해시를 저장하고 sent_at 을 채운다.
다시 부르면 새 코드의 해시가 이전 해시를 덮고 tries 가 0 이 된다. _new_code 는 이 파일 밖에서 부르지 않는다.
"""

from __future__ import annotations

import asyncio
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import NotFound
from classfit.core.passwords import hash_password
from classfit.crud import auth as crud_auth

CODE_DIGITS = 6


def _new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


async def issue_email_code(session: AsyncSession, verification_id: int) -> str:
    """새 6자리 코드를 만들어 argon2id 해시를 저장(flush)하고 평문을 돌려준다. 행이 없으면 NotFound."""
    code = _new_code()
    code_hash = await asyncio.to_thread(hash_password, code)
    if not await crud_auth.set_code_hash(session, verification_id, code_hash):
        raise NotFound("인증 요청이 없습니다")
    return code
