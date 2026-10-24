"""안 보낸 메일 outbox 를 본문으로 찍는다: python -m scripts.outbox_preview [--apply] [--limit N]

- 1차에는 메일을 보내지 않는다(ADR-003 결정 5). 본문은 이 명령으로 본다.
- kind 마다 본문을 만든다. `email_code` 는 issue_email_code() 를 부른다(인증 코드를 만드는 곳은 그 함수 하나).
- `instructor_approved`·`instructor_rejected`(T3)는 params {instructor_id, audit_id} 로 강사 이름과 반려 사유를 읽는다.
  사유는 강사 행이 아니라 그 audit 행의 detail.reason(불변 스냅샷)이다 — 재신청이 행의 사유를 비워도 본문은 같다.
  사유 칸이 비면 빈 글자로 찍는다. 강사·audit 행이 없거나 audit 이 그 강사의 반려(instructor.reject) 기록이 아니면 3 이다.
- `session_assigned`(T5)는 params {instructor_id, audit_id} 로 강사 이름과 그 audit(session.assign, target course)의
  detail 스냅샷(강의 제목·세션 제목)을 읽는다 — 강의가 그 뒤 지워져도 본문은 같다. audit 이 배정 기록이 아니거나
  detail 의 강사가 params 와 다르면 3 이다.
- `survey_opened`·`survey_closed`(T8)는 params 스냅샷({survey_id, course_title, open_on, close_on} · {survey_id,
  course_title, closed_on})만으로 본문을 만들고 DB 를 읽지 않는다 — 강의·설문이 지워져도 본문은 같다. 칸이 빠지면 3 이다.
- `inquiry_received`·`inquiry_notify`(T9b)는 params {inquiry_id} 로 문의 행을 읽는다. 확인 메일(→ 문의자)은 영수증 번호와
  고정 문구만 찍고 회사명·이름·연락처·내용을 되비치지 않는다. 알림(→ INQUIRY_NOTIFY_TO)은 접수 칸 전부를 찍고 비어 있는
  선택 칸은 "(없음)" 이다. 문의 행이 없으면(지웠으면) 3 이다.
- `--limit N`(기본 200, 1 이상): 안 보낸 행을 앞(id 순) N 건만 읽는다 — 공개 문의가 쌓여도 전부를 메모리에 올리지 않는다.
- 미리 보기(기본): 끝까지 돈 뒤 롤백한다. 해시가 저장되지 않으니 코드 자리는 `******` 로 가리고 "무효 코드(미리 보기)" 라고 찍는다.
  실제 숫자는 `--apply` 때만 stdout 에 나온다.
- `--apply`: 해시를 저장하고 sent_at 을 채운 뒤 커밋한다. 다시 보내면 새 코드가 이전 해시를 덮는다. 행마다 id 오름차순으로
  잡고(crud.outbox.lock_unsent — FOR UPDATE 뒤 다시 읽기) 렌더한다 — 그 사이 inquiry_gc 가 지웠거나 다른 --apply 가 보낸
  행은 건너뛰고 stderr 에 그 수를 찍는다(T9b codex 구현 리뷰 1차 ①). 미리 보기는 커밋하지 않으니 잡지 않는다.
- 모르는 kind · params 모양 틀림은 3(전제 거절)이고 아무것도 커밋하지 않는다.
- 종료 코드 0 끝 · 2 인자 틀림 · 3 전제 거절. 결과 JSON 은 stdout, 안내는 stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from classfit.core.config import get_settings
from classfit.core.errors import DomainError, NotFound
from classfit.crud.inquiry import get_inquiry
from classfit.crud.outbox import lock_unsent, mark_sent, unsent
from classfit.database.session import make_engine, make_session_factory
from classfit.models import AuditLog, Inquiry, Instructor
from classfit.models.inquiry import INQUIRY_SIZE_LABELS
from classfit.service.auth.email_code import issue_email_code

PREVIEW_CODE = "무효 코드(미리 보기)"
MASK = "******"
DEFAULT_LIMIT = 200
# 확인 메일 본문 — 제출 칸에 들어올 법한 낱말(이름·회사·내용)을 쓰지 않는다(T9b 결정 ix)
RECEIVED_BODY = (
    "교육 문의가 접수되었습니다. 접수 번호 {receipt_no}. 영업일 1일 안에 연락드립니다."
)
NONE_MARK = "(없음)"


async def _email_code(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    code = await issue_email_code(session, int(params["verification_id"]))
    return f"인증 코드: {code if reveal else MASK}"


async def _instructor(session: AsyncSession, params: dict[str, Any]) -> Instructor:
    row = await session.get(Instructor, int(params["instructor_id"]))
    if row is None:
        raise NotFound("강사가 없습니다")
    return row


async def _instructor_approved(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    row = await _instructor(session, params)
    return f"{row.name} 강사님, 가입이 승인되었습니다. 로그인해 프로필과 서류를 확인하세요."


async def _instructor_rejected(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    row = await _instructor(session, params)
    audit = await session.get(AuditLog, int(params["audit_id"]))
    if audit is None:
        raise NotFound("audit 행이 없습니다")
    expected = ("instructor.reject", "instructor", str(row.id))
    if (audit.action, audit.target_type, audit.target_id) != expected:
        raise ValueError("audit 행이 그 강사의 반려 기록이 아니다")
    reason = audit.detail.get("reason") or ""
    return (
        f"{row.name} 강사님, 가입 신청이 반려되었습니다. 사유: {reason}\n"
        "프로필을 고친 뒤 다시 신청할 수 있습니다."
    )


async def _session_assigned(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    row = await _instructor(session, params)
    audit = await session.get(AuditLog, int(params["audit_id"]))
    if audit is None:
        raise NotFound("audit 행이 없습니다")
    is_assign = (audit.action, audit.target_type) == ("session.assign", "course")
    if not is_assign or audit.detail.get("instructor_id") != row.id:
        raise ValueError("audit 행이 그 강사의 배정 기록이 아니다")
    titles = ", ".join(str(s["title"]) for s in audit.detail["sessions"])
    return (
        f"{row.name} 강사님, 「{audit.detail['course_title']}」 강의에 배정되었습니다.\n"
        f"배정된 세션: {titles}\n로그인해 내 세션을 확인하세요."
    )


def _day(value: Any) -> str:
    d = date.fromisoformat(str(value))
    return f"{d.month}월 {d.day}일"


async def _survey_opened(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    return (
        f"「{params['course_title']}」 강의의 만족도 조사가 {_day(params['open_on'])}에 열립니다.\n"
        f"{_day(params['close_on'])}까지 응답할 수 있습니다. 답변은 이름과 연결되지 않습니다."
    )


async def _survey_closed(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    return (
        f"「{params['course_title']}」 강의의 만족도 조사가 {_day(params['closed_on'])}에 닫혔습니다.\n"
        "응답 수가 최소 기준 이상이면 로그인해 결과를 볼 수 있습니다."
    )


async def _inquiry(session: AsyncSession, params: dict[str, Any]) -> Inquiry:
    row = await get_inquiry(session, int(params["inquiry_id"]))
    if row is None:
        raise NotFound("문의가 없습니다")
    return row


async def _inquiry_received(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    row = await _inquiry(session, params)
    return RECEIVED_BODY.format(receipt_no=row.receipt_no)


async def _inquiry_notify(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    row = await _inquiry(session, params)
    size = INQUIRY_SIZE_LABELS.get(row.company_size or "", NONE_MARK)
    message = f"문의 내용:\n{row.message}" if row.message else f"문의 내용: {NONE_MARK}"
    return (
        "교육 문의가 들어왔습니다.\n"
        f"회사명: {row.company_name}\n"
        f"담당자: {row.contact_name}\n"
        f"부서 · 직함: {row.dept_title or NONE_MARK}\n"
        f"이메일: {row.email}\n"
        f"연락처: {row.phone}\n"
        f"임직원 규모: {size}\n\n{message}"
    )


# (session, params, reveal) → 본문. reveal 은 --apply 일 때만 참이다(미리 보기의 코드는 무효라 가린다)
RENDERERS: dict[str, Callable[[AsyncSession, dict[str, Any], bool], Awaitable[str]]] = {
    "email_code": _email_code,
    "instructor_approved": _instructor_approved,
    "instructor_rejected": _instructor_rejected,
    "session_assigned": _session_assigned,
    "survey_opened": _survey_opened,
    "survey_closed": _survey_closed,
    "inquiry_received": _inquiry_received,
    "inquiry_notify": _inquiry_notify,
}
CODE_KINDS = frozenset({"email_code"})


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.outbox_preview",
        description="안 보낸 outbox 의 본문을 찍는다(기본 미리 보기)",
        allow_abbrev=False,
    )
    p.add_argument(
        "--apply", action="store_true", help="해시 저장 + sent_at 을 커밋한다"
    )
    p.add_argument(
        "--limit",
        type=_positive_int,
        default=DEFAULT_LIMIT,
        help=f"안 보낸 행을 앞(id 순) N 건만(기본 {DEFAULT_LIMIT})",
    )
    return p


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("1 이상이어야 합니다")
    return n


def _err(message: str) -> None:
    print(message, file=sys.stderr)


async def run(
    argv: list[str], session_factory: async_sessionmaker[AsyncSession]
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    messages: list[dict[str, Any]] = []
    skipped = 0
    async with session_factory() as session:
        for row in await unsent(session, limit=args.limit):
            if args.apply:
                locked = await lock_unsent(session, row.id)
                if locked is None:  # 그 사이 지워졌거나(inquiry_gc) 보냈다
                    skipped += 1
                    continue
                row = locked
            render = RENDERERS.get(row.kind)
            if render is None:
                _err(
                    f"전제 거절: 모르는 kind {row.kind!r} (outbox id {row.id}). 아무것도 커밋하지 않았다"
                )
                return 3
            try:
                body = await render(session, row.params, args.apply)
            except (KeyError, TypeError, ValueError, DomainError) as exc:
                _err(
                    f"전제 거절: outbox id {row.id} 의 params 를 쓸 수 없다({type(exc).__name__})"
                )
                return 3
            entry: dict[str, Any] = {
                "id": row.id,
                "kind": row.kind,
                "to": row.to,
                "body": body,
            }
            if row.kind in CODE_KINDS:
                entry["code_status"] = "저장됨" if args.apply else PREVIEW_CODE
            messages.append(entry)
            if args.apply:
                await mark_sent(session, row)
        if args.apply:
            await session.commit()
        else:
            await session.rollback()
    print(json.dumps({"applied": args.apply, "messages": messages}, ensure_ascii=False))
    if skipped:
        _err(f"건너뜀: 읽은 뒤 지워졌거나 이미 보낸 행 {skipped}건")
    if not args.apply:
        _err(
            f"미리 보기: {len(messages)}건(--limit {args.limit} 까지), 롤백했다."
            " 찍힌 코드는 무효다. 보내려면 --apply"
        )
    return 0


async def _main(argv: list[str]) -> int:
    settings = get_settings()
    if missing := settings.missing("database_url"):
        _err(f"전제 거절: 미구성 {', '.join(missing)}")
        return 3
    engine = make_engine(settings.require_database_url())
    try:
        return await run(argv, make_session_factory(engine))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
