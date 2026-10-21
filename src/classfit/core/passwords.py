"""비밀번호·인증 코드 해시. argon2id(argon2-cffi PasswordHasher 기본형).

없는 아이디도 DUMMY_HASH 와 같은 대조를 거쳐 응답 시간이 갈리지 않게 한다.
대조는 CPU 를 오래 쓰므로 async 쪽은 asyncio.to_thread 로 부른다.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """맞으면 True. 틀림·깨진 해시는 False(예외를 밖으로 내지 않는다)."""
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError, InvalidHashError:
        return False


# 없는 아이디용 대조 상대. 대조 결과와 무관하게 없는 아이디는 실패다(시간만 같게 맞춘다)
DUMMY_HASH = hash_password("classfit-dummy-" + "x" * 32)
