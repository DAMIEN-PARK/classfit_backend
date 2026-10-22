"""AX 과정·심화 과정 카탈로그를 JSON 파일에서 넣는다: python -m scripts.import_ax_catalog <json 경로> [--apply]

입력 형식(JSON 객체 하나, 두 구간 다 선택이지만 둘 다 비면 거절):
  {
    "courses": [
      {"id": "ax-common-1", "title": "…", "job_groups": ["공통(전 직원)"], "difficulty": "중", "minutes": 120,
       "goal": "…", "output": "…", "material": "…",
       "theory": ["…"], "practice": ["…"], "schedule": [["00:00", "이론", "…"]]}
    ],
    "advanced": [
      {"id": "adv-1", "title": "…", "audience": "…", "tool": "…", "hours": 18, "goal": "…", "features": ["…"]}
    ]
  }
  - 과정 필수 칸: id · title · job_groups · difficulty · minutes. goal·output·material 은 null 가능, theory·practice·
    schedule 은 빠지면 빈 목록. schedule 줄은 [시간, 종류, 내용] 세 글자다.
  - 심화 필수 칸: id · title · audience · tool · hours. goal 은 null 가능, features 는 5개까지.
  - id: 과정 ^ax-[a-z0-9]+(-[a-z0-9]+)*$ , 심화 ^adv-[a-z0-9]+(-[a-z0-9]+)*$ . ax-custom- 접두는 관리자 추가 전용이라
    거절한다. 파일 안에서 같은 id 가 두 번 나오면 거절한다.
  - job_groups 는 1개 이상이고 값은 공통(전 직원) · 경영·관리 · 사무·행정 · 기획·전략 · 인사·총무·회계 · 영업·마케팅 ·
    고객응대(CS) · 구매·자재·물류 · 생산·제조 · 품질·안전 · 연구개발·설계 · IT·개발·데이터 · 디자인·콘텐츠 13개 중에서.
    현행 정적 페이지의 deptId 를 직무군 이름으로 바꾸는 일은 운영자가 파일을 만들 때 한다(명령은 매핑하지 않는다).
  - difficulty 하·중·상 · minutes 10~600 · hours 1~200. 모르는 키(dept · deptName · deptId …)는 거절한다.
  - 글자·목록 상한은 API 와 같다: id 80자 · title 200자 · goal·output·material 2000자(빈 글자는 null) ·
    theory·practice 30줄 × 500자 · schedule 50줄(시간·종류 1~20자, 내용 1~500자) · audience 100자 · tool 50자 ·
    features 5줄 × 100자. 넘으면 거절한다(import 한 행이 끝점에서 열리고 관리자 PATCH 로 고칠 수 있게).

멱등 규칙:
  - 키는 id 다. 없는 id 만 넣는다(inserted). 있는 id 는 어떤 칸도 쓰지 않고 내용이 같으면 unchanged,
    다르면 differs 로 보고만 한다 — 이관 뒤 고치는 길은 관리자 PATCH 하나다. 두 번 돌려도 행과 칸이 같다.
  - 새 과정은 source ax · reviewed true · pub true · active true, 새 심화는 pub·active true 로 넣는다.
    재실행은 관리자가 바꾼 pub·active 를 건드리지 않는다.
  - 새로 넣은 것이 있으면 audit 1행(actor system, pool_course.import, detail 여섯 개수)을 남긴다.

실행:
  - 기본은 미리 보기다. 끝까지 돈 뒤 롤백한다. --apply 일 때만 커밋한다.
  - 결과 JSON {"applied", "courses": {"inserted", "unchanged", "differs"}, "advanced": {…}} 은 stdout, 안내는 stderr.
  - 종료 코드 0 끝 · 2 인자 틀림(없는 파일 · JSON 아님 · 형식 틀림, 위치와 사유만 찍고 입력 값은 찍지 않는다) ·
    3 전제 거절(DB 미구성 · 같은 id 를 동시에 넣음).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from classfit.core.config import get_settings
from classfit.core.errors import DomainError
from classfit.database.session import make_engine, make_session_factory
from classfit.schemas.catalog_import import AxCatalogFileIn
from classfit.service.pool.catalog_import import import_ax_catalog


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.import_ax_catalog",
        description="AX 과정·심화 과정 카탈로그 JSON 을 넣는다(기본 미리 보기, 있는 id 는 쓰지 않는다)",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    p.add_argument("path", help="입력 JSON 파일 경로(형식은 아래)")
    p.add_argument(
        "--apply", action="store_true", help="커밋한다(없으면 끝까지 돈 뒤 롤백)"
    )
    return p


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _load(path: str) -> AxCatalogFileIn | None:
    """파일을 읽어 검증한다. 틀리면 위치·사유만 찍고 None(입력 값은 찍지 않는다)."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _err(f"인자 틀림: 입력 파일을 읽을 수 없다({type(exc).__name__})")
        return None
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        _err(f"인자 틀림: JSON 이 아니다(줄 {exc.lineno} 칸 {exc.colno}: {exc.msg})")
        return None
    try:
        return AxCatalogFileIn.model_validate(payload)
    except ValidationError as exc:
        reasons = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or '(파일)'}: {e['msg']}"
            for e in exc.errors()
        )
        _err(f"인자 틀림: {reasons}")
        return None


async def run(
    argv: list[str], session_factory: async_sessionmaker[AsyncSession]
) -> int:
    try:
        args, unknown = _parser().parse_known_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if unknown:
        _err(f"인자 틀림: 모르는 인자 {len(unknown)}개(값은 찍지 않는다)")
        return 2
    data = _load(args.path)
    if data is None:
        return 2
    async with session_factory() as session:
        try:
            result = await import_ax_catalog(session, data, apply=args.apply)
        except DomainError as exc:
            await session.rollback()
            _err(f"전제 거절: {exc.message}. 아무것도 커밋하지 않았다")
            return 3
        if args.apply:
            await session.commit()
        else:
            await session.rollback()
    print(json.dumps(result.as_dict(), ensure_ascii=False))
    if not args.apply:
        _err("미리 보기: 롤백했다. 넣으려면 --apply")
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
