"""관리자 계정을 만든다: python -m scripts.create_admin --login-id <아이디> [--apply]

- 비밀번호는 getpass 로 두 번 받는다. argv 칸이 없다(셸 기록·ps 에 남지 않게). 모르는 인자는 값을 찍지 않고 2 다.
- 기본은 미리 보기다. 끝까지 돈 뒤 롤백한다. `--apply` 일 때만 커밋한다. audit 1행(actor system)도 같은 트랜잭션이다.
- 종료 코드 0 끝 · 2 인자 틀림(비밀번호 불일치·모양 틀림 포함) · 3 전제 거절(같은 아이디 · DB 미구성).
  결과 JSON 은 stdout, 안내는 stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from collections.abc import Callable

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from classfit.core.config import get_settings
from classfit.core.errors import Conflict
from classfit.core.passwords import hash_password
from classfit.crud.admin import insert_admin
from classfit.crud.audit import insert_audit
from classfit.database.session import make_engine, make_session_factory
from classfit.schemas.admin import AdminCreateIn


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.create_admin",
        description="관리자 계정을 만든다. 비밀번호는 getpass 로 받는다(기본 미리 보기)",
        allow_abbrev=False,
    )
    p.add_argument("--login-id", required=True)
    p.add_argument(
        "--apply", action="store_true", help="커밋한다(없으면 끝까지 돈 뒤 롤백)"
    )
    return p


def _err(message: str) -> None:
    print(message, file=sys.stderr)


async def run(
    argv: list[str],
    session_factory: async_sessionmaker[AsyncSession],
    *,
    ask: Callable[[str], str] = getpass.getpass,
) -> int:
    try:
        args, unknown = _parser().parse_known_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if unknown:
        _err(
            f"인자 틀림: 모르는 인자 {len(unknown)}개(값은 찍지 않는다). 비밀번호는 getpass 로만 받는다"
        )
        return 2
    password = ask("비밀번호: ")
    if ask("비밀번호 확인: ") != password:
        _err("인자 틀림: 두 비밀번호가 다르다")
        return 2
    try:
        data = AdminCreateIn(login_id=args.login_id, password=password)
    except ValidationError as exc:
        # 입력값(비밀번호)은 찍지 않는다. 위치와 사유만
        reasons = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        )
        _err(f"인자 틀림: {reasons}")
        return 2
    async with session_factory() as session:
        try:
            admin = await insert_admin(
                session,
                login_id=data.login_id,
                password_hash=hash_password(data.password),
            )
        except Conflict as exc:
            _err(f"전제 거절: {exc.message}")
            return 3
        await insert_audit(
            session,
            actor="system",
            action="admin.create",
            target_type="admin_account",
            target_id=str(admin.id),
        )
        result = {
            "applied": args.apply,
            "admin": {"id": admin.id, "login_id": admin.login_id},
        }
        if args.apply:
            await session.commit()
        else:
            await session.rollback()
    print(json.dumps(result, ensure_ascii=False))
    if not args.apply:
        _err("미리 보기: 롤백했다. 만들려면 --apply")
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
