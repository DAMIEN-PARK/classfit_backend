"""참조 없는 오래된 파일 바이트를 지운다: python -m scripts.file_gc [--apply]

- 지우는 것: `<FILE_STORE_ROOT>/<sha 앞 2자>/<sha>` 중 stored_file 행이 하나도 가리키지 않고
  mtime 이 FILE_GC_GRACE_HOURS(기본 24) 지난 바이트만(ADR-003 결정 4 · Design 5절 9).
  업로드는 바이트가 있으면 mtime 을 갱신하므로, 행이 커밋되기 전의 바이트는 유예 안에 있다.
- 지우기는 후보마다 service.files.store.remove_stale 이다(무덤으로 옮긴 뒤 mtime 을 다시 보고 지운다) — 확인과
  지우기 사이에 같은 바이트를 다시 올린 업로드의 바이트를 지우지 않는다. --apply 는 먼저 restore_leftovers 로
  앞선 gc 가 옮긴 채 남긴 무덤을 되살린다(결과 JSON 의 restored).
- 기본은 미리 보기다(후보만 찍는다). `--apply` 일 때만 지운다. DB 에는 쓰지 않는다.
- 종료 코드 0 끝 · 2 인자 틀림 · 3 전제 거절(FILE_STORE_ROOT · DB 미구성). 결과 JSON 은 stdout, 안내는 stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from classfit.core.config import Settings, get_settings
from classfit.crud.stored_file import referenced_sha256
from classfit.database.session import make_engine, make_session_factory
from classfit.service.files.store import (
    gc_candidates,
    remove_stale,
    restore_leftovers,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.file_gc",
        description="참조 없는 오래된 파일 바이트를 지운다(기본 미리 보기)",
        allow_abbrev=False,
    )
    p.add_argument("--apply", action="store_true", help="지운다(없으면 후보만 찍는다)")
    return p


def _err(message: str) -> None:
    print(message, file=sys.stderr)


async def run(
    argv: list[str],
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    root = settings.file_store_root
    if root is None:
        _err(f"전제 거절: 미구성 {', '.join(settings.missing('file_store_root'))}")
        return 3
    grace = timedelta(hours=settings.file_gc_grace_hours)
    async with session_factory() as session:
        referenced = await referenced_sha256(session)
    restored = restore_leftovers(root) if args.apply else []
    candidates = gc_candidates(root, referenced, grace)
    deleted: list[str] = []
    if args.apply:
        for path in candidates:
            # 후보를 고른 뒤 같은 바이트가 다시 올라왔으면(mtime 갱신·새로 씀) 남긴다
            if remove_stale(path, time.time() - grace.total_seconds()):
                deleted.append(path.name)
    result = {
        "applied": args.apply,
        "grace_hours": settings.file_gc_grace_hours,
        "candidates": [p.name for p in candidates],
        "deleted": deleted,
        "restored": restored,
    }
    print(json.dumps(result, ensure_ascii=False))
    if not args.apply:
        _err(f"미리 보기: 후보 {len(candidates)}개, 지우지 않았다. 지우려면 --apply")
    return 0


async def _main(argv: list[str]) -> int:
    settings = get_settings()
    if missing := settings.missing("database_url"):
        _err(f"전제 거절: 미구성 {', '.join(missing)}")
        return 3
    engine = make_engine(settings.require_database_url())
    try:
        return await run(argv, make_session_factory(engine), settings)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
