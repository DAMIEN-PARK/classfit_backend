"""안 보낸 메일 outbox 를 본문으로 찍는다: python -m scripts.outbox_preview [--apply]

- 1차에는 메일을 보내지 않는다(ADR-003 결정 5). 본문은 이 명령으로 본다.
- kind 마다 본문을 만든다. `email_code` 는 issue_email_code() 를 부른다(인증 코드를 만드는 곳은 그 함수 하나).
- 미리 보기(기본): 끝까지 돈 뒤 롤백한다. 해시가 저장되지 않으니 코드 자리는 `******` 로 가리고 "무효 코드(미리 보기)" 라고 찍는다.
  실제 숫자는 `--apply` 때만 stdout 에 나온다.
- `--apply`: 해시를 저장하고 sent_at 을 채운 뒤 커밋한다. 다시 보내면 새 코드가 이전 해시를 덮는다.
- 모르는 kind · params 모양 틀림은 3(전제 거절)이고 아무것도 커밋하지 않는다.
- 종료 코드 0 끝 · 2 인자 틀림 · 3 전제 거절. 결과 JSON 은 stdout, 안내는 stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from classfit.core.config import get_settings
from classfit.core.errors import DomainError
from classfit.crud.outbox import mark_sent, unsent
from classfit.database.session import make_engine, make_session_factory
from classfit.service.auth.email_code import issue_email_code

PREVIEW_CODE = "무효 코드(미리 보기)"
MASK = "******"


async def _email_code(
    session: AsyncSession, params: dict[str, Any], reveal: bool
) -> str:
    code = await issue_email_code(session, int(params["verification_id"]))
    return f"인증 코드: {code if reveal else MASK}"


# (session, params, reveal) → 본문. reveal 은 --apply 일 때만 참이다(미리 보기의 코드는 무효라 가린다)
RENDERERS: dict[str, Callable[[AsyncSession, dict[str, Any], bool], Awaitable[str]]] = {
    "email_code": _email_code,
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
    return p


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
    async with session_factory() as session:
        for row in await unsent(session):
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
    if not args.apply:
        _err(
            f"미리 보기: {len(messages)}건, 롤백했다. 찍힌 코드는 무효다. 보내려면 --apply"
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
