"""파일 크기 상한. src/classfit/** 만 본다.

models·schemas 는 면제, app/endpoints/ 500줄, 나머지 300줄.
넘기려면 앞 30줄 안에 줄 머리 `# oversize: <상한> <사유 10자 이상>` 한 줄을 적는다. 올릴 수 있는 상한은 기본 한도의 2배까지.
숫자는 알람이고, 쪼갤 자리는 "고치는 이유가 둘인가"로 정한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PKG = "classfit"
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / PKG
EXEMPT = ("models", "schemas")
LIMITS = {"app/endpoints": 500}
DEFAULT = 300
MAX_FACTOR = 2
OVERSIZE = re.compile(r"^[ \t]*#[ \t]*oversize:[ \t]*(\d+)[ \t]+(\S.{9,})$", re.MULTILINE)


def limit_for(rel: Path) -> int | None:
    if rel.parts[0] in EXEMPT:
        return None
    posix = rel.as_posix()
    for prefix, limit in LIMITS.items():
        if posix.startswith(prefix + "/"):
            return limit
    return DEFAULT


def main() -> int:
    failures: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        limit = limit_for(rel)
        if limit is None:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        declared = OVERSIZE.search("\n".join(lines[:30]))
        if declared:
            wanted = int(declared.group(1))
            cap = limit * MAX_FACTOR
            if wanted > cap:
                failures.append(f"{rel}: oversize 선언 {wanted}줄 > 허용 최대 {cap}줄 — 쪼갠다")
                continue
            limit = wanted
        if len(lines) > limit:
            failures.append(f"{rel}: {len(lines)}줄 > {limit}줄")
    for item in failures:
        print("FILE SIZE:", item)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
