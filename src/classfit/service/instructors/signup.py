"""강사 가입: 인증 코드 요청(request_email_code)과 가입(signup). flush 까지만.

- 요청은 코드를 만들지 않는다. 이메일의 열린 요청 행(없으면 새로)에 outbox 1행(kind email_code, params 는 요청 행 id
  뿐)을 더한다. 코드는 발송 때 생기고, 재발송이 해시를 덮어 이전 코드를 무효로 만든다(Design 5절 8, ADR-003 결정 5).
- 가입 판정 순서(T3 결정 i·ii·xiii): 시도 키 잠금(email_code, 이메일 해시, 주소) → 열린 요청 행 잠그며 읽기(없음·
  발송 전은 mismatch) → 만료(issued_at 기준, 지금은 DB now()) → 시도 상한 → 코드 대조(틀리면 tries + 1, mismatch)
  → 중지 태그 검사 → 새 분야 태그 → 강사 행 → 태그 잇기 → 요청 소비 → 성공 시도 행.
- 코드 실패 셋은 실패 시도 행을 남기고 결과 값으로 돌려준다(예외 없음 — 끝점이 problem() 을 반환해 tries 와 시도 행이
  커밋된다, Design 5절 7). 이미 가입된 이메일(Conflict)과 중지 태그(InactiveTags)는 예외라 그 요청은 롤백된다.
- 중지 태그 검사는 아무 행도 쓰기 전에 한다. 태그 이름은 crud.tag.normalize_tag_name 으로 맞춘 뒤 비교한다.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.core.errors import Conflict
from classfit.core.passwords import hash_password, verify_password
from classfit.crud import auth as crud_auth
from classfit.crud import instructor as crud_instructor
from classfit.crud import tag as crud_tag
from classfit.crud.outbox import enqueue
from classfit.schemas.enter import normalize_email
from classfit.service.rules.instructor import DEFAULT_TAG_GROUP, code_expired

ATTEMPT_KIND = "email_code"
MAIL_KIND = "email_code"
SignupOutcome = Literal["ok", "mismatch", "expired", "locked"]


@dataclass(frozen=True)
class SignupResult:
    outcome: SignupOutcome
    instructor_id: int | None = None


class InactiveTags(ValueError):
    """사용 중지된 분야 태그를 새로 붙이려 했다. indexes 는 받은 tags 목록의 자리(끝점이 loc ["body","tags",i] 로)."""

    def __init__(self, indexes: list[int]) -> None:
        super().__init__("사용 중지된 태그입니다")
        self.indexes = indexes


def subject_hash(email: str) -> str:
    """정규화한 이메일의 sha256 hex(auth_attempt.subject_hash)."""
    return hashlib.sha256(normalize_email(email).encode()).hexdigest()


async def resolve_field_tags(session: AsyncSession, names: Sequence[str]) -> list[int]:
    """분야 태그 이름들 → 태그 id(받은 순서, 겹침 제거). 중지 태그가 하나라도 있으면 InactiveTags(아무것도 쓰지 않는다).

    없는 이름은 source instructor · 대분류 기타 로 만든다.
    """
    normalized = [crud_tag.normalize_tag_name(n) for n in names]
    found = await crud_tag.find_tags(session, "field", normalized)
    inactive = [
        i for i, n in enumerate(normalized) if n in found and not found[n].active
    ]
    if inactive:
        raise InactiveTags(inactive)
    rows = await crud_tag.create_missing_field_tags(
        session, normalized, source="instructor", group=DEFAULT_TAG_GROUP
    )
    return list(dict.fromkeys(rows[n].id for n in normalized))


async def request_email_code(session: AsyncSession, *, email: str) -> int:
    """인증 코드 요청. 요청 행 id 를 돌려준다. 이미 가입된 이메일이면 Conflict(409)."""
    email = normalize_email(email)
    if await crud_instructor.find_by_email(session, email) is not None:
        raise Conflict("이미 가입된 이메일입니다")
    row = await crud_auth.insert_verification(session, email)
    await enqueue(session, kind=MAIL_KIND, params={"verification_id": row.id}, to=email)
    return row.id


async def _failed(
    session: AsyncSession, outcome: SignupOutcome, *, subject: str, client: str
) -> SignupResult:
    await crud_auth.insert_attempt(
        session, kind=ATTEMPT_KIND, subject_hash=subject, client=client, ok=False
    )
    return SignupResult(outcome)


async def signup(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    code: str,
    password: str,
    name: str,
    phone: str,
    org: str | None,
    intro: str | None = None,
    career: Sequence[str] = (),
    tags: Sequence[str],
    client: str,
) -> SignupResult:
    """가입. 성공이면 outcome ok 와 새 강사 id(상태 pending). 입력 모양(길이·약관 동의 등)은 끝점의 스키마가 본다."""
    email = normalize_email(email)
    subject = subject_hash(email)
    # 같은 (이메일, 주소)의 시도를 줄 세운다(T1 lock_attempt_key 재사용)
    await crud_auth.lock_attempt_key(
        session, kind=ATTEMPT_KIND, subject_hash=subject, client=client
    )
    found = await crud_auth.find_open_verification(session, email)
    if found is None:
        return await _failed(session, "mismatch", subject=subject, client=client)
    row, now = found
    if row.code_hash is None or row.issued_at is None:  # 아직 발송 전
        return await _failed(session, "mismatch", subject=subject, client=client)
    if code_expired(row.issued_at, now, settings.email_code_minutes):
        return await _failed(session, "expired", subject=subject, client=client)
    if row.tries >= settings.email_code_max_tries:
        return await _failed(session, "locked", subject=subject, client=client)
    if not await asyncio.to_thread(verify_password, row.code_hash, code):
        await crud_auth.bump_tries(session, row.id)
        return await _failed(session, "mismatch", subject=subject, client=client)

    tag_ids = await resolve_field_tags(session, tags)
    password_hash = await asyncio.to_thread(hash_password, password)
    instructor = await crud_instructor.insert_instructor(
        session,
        email=email,
        password_hash=password_hash,
        name=name,
        phone=phone,
        org=org,
        intro=intro,
        career=list(career),
        status="pending",
        terms_version=settings.terms_version,
    )
    await crud_instructor.replace_tags(session, instructor.id, tag_ids)
    await crud_auth.consume_verification(session, row.id, instructor.id)
    await crud_auth.insert_attempt(
        session, kind=ATTEMPT_KIND, subject_hash=subject, client=client, ok=True
    )
    return SignupResult("ok", instructor_id=instructor.id)
