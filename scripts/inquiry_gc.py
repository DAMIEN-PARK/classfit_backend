"""교육 문의 행과 그 outbox 행을 지운다: python -m scripts.inquiry_gc (--receipt R | --email E | --older-than-days [N]) [--apply]

- 1차 보유 규칙(T9b 결정 xxv): 문의 행은 접수 시각(created_at) + 365일이 지나면 만료다. 운영자가 월 1회
  `--older-than-days 365 --apply` 를 수동 실행한다. 요청 시 즉시 삭제는 `--receipt`(영수증 하나) · `--email`(그 이메일 전부).
- 선택자는 셋 중 하나다(상호 배타 필수). `--older-than-days` 를 값 없이 쓰면 365, 값은 1 이상이다. 이메일은 앞뒤 공백을
  지우고 소문자로 비교하고(scripts → schemas 의존을 피해 normalize_email 을 거치지 않는다), 영수증은 대문자로 비교한다.
- 대상 문의 행마다 그 outbox 행(kind inquiry_* · params inquiry_id)도 지운다 — 남기면 매달린 참조가 되어 outbox_preview 가
  3 으로 멈춘다(mail_outbox 에 FK 가 없다). 문의 행을 지우는 곳은 이 명령 하나다(crud.inquiry.delete_inquiries).
- 기본은 미리 보기다. file_gc 와 달리 같은 트랜잭션에서 실제로 지운 뒤 롤백한다(미리 보기 수치가 --apply 와 같은 경로에서
  나온다). `--apply` 만 커밋한다.
- 종료 코드 0 끝 · 2 인자 틀림 · 3 전제 거절(DB 미구성). 결과 JSON 은 stdout, 안내는 stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from classfit.core.config import get_settings
from classfit.crud.inquiry import delete_inquiries, select_for_gc
from classfit.database.session import make_engine, make_session_factory

RETENTION_DAYS = 365


def _days(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("1 이상이어야 합니다")
    return n


def _filled(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise argparse.ArgumentTypeError("빈 값을 쓰지 않는다")
    return cleaned


def _receipt(value: str) -> str:
    return _filled(value).upper()


def _email(value: str) -> str:
    return _filled(value).lower()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.inquiry_gc",
        description="교육 문의 행과 그 outbox 행을 지운다(기본 미리 보기 — 지운 뒤 되돌린다)",
        allow_abbrev=False,
    )
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--receipt", type=_receipt, help="영수증 번호 하나")
    which.add_argument("--email", type=_email, help="그 이메일의 문의 전부")
    which.add_argument(
        "--older-than-days",
        type=_days,
        nargs="?",
        const=RETENTION_DAYS,
        help=f"접수 뒤 N 일이 지난 문의(값 없이 쓰면 {RETENTION_DAYS})",
    )
    p.add_argument(
        "--apply", action="store_true", help="지운다(없으면 지운 뒤 되돌린다)"
    )
    return p


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _selector(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    """(결과 JSON 의 selector, select_for_gc 인자)."""
    if args.receipt is not None:
        return {"receipt": args.receipt}, {"receipt_no": args.receipt}
    if args.email is not None:
        return {"email": args.email}, {"email": args.email}
    days = args.older_than_days
    return {"older_than_days": days}, {"older_than": timedelta(days=days)}


async def run(
    argv: list[str], session_factory: async_sessionmaker[AsyncSession]
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    selector, chosen = _selector(args)
    async with session_factory() as session:
        rows = await select_for_gc(session, **chosen)
        selected = [
            {
                "id": r.id,
                "receipt_no": r.receipt_no,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
        outbox_deleted, deleted = await delete_inquiries(session, [r.id for r in rows])
        if args.apply:
            await session.commit()
        else:
            await session.rollback()
    result = {
        "applied": args.apply,
        "selector": selector,
        "selected": selected,
        "outbox_deleted": outbox_deleted,
        "deleted": deleted,
    }
    print(json.dumps(result, ensure_ascii=False))
    if not args.apply:
        _err(
            f"미리 보기: 대상 {deleted}건(outbox {outbox_deleted}건), 되돌렸다. 지우려면 --apply"
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
