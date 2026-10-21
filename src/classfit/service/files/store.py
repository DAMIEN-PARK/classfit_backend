"""파일 바이트 저장(ADR-003 결정 2·4 · Design 5절 9·10).

- 디스크 배치: `<root>/<sha256 앞 2자>/<sha256>`. 같은 바이트는 한 번만 쓰고, 이미 있으면 mtime 만 갱신한다
  (gc 유예가 다시 시작되어, 행이 커밋되기 전에 gc 가 지우지 못한다).
- 이 모듈은 디스크만 다룬다. `stored_file` 행은 호출자가 같은 요청 트랜잭션에 넣는다.
- 디스크 경로는 행의 sha256(64자 소문자 hex)로만 만든다. key 는 경로에 쓰지 않는다(루트를 벗어나지 않게).
- 디스크 I/O 는 블로킹이다. async 끝점은 `asyncio.to_thread` 로 부른다.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

_SHA256 = re.compile(r"[0-9a-f]{64}")
HREF_PREFIX = "/v1/files/"


def path_for(root: Path, sha256: str) -> Path:
    """sha256 의 디스크 경로. 64자 소문자 hex 가 아니면 ValueError."""
    if not _SHA256.fullmatch(sha256):
        raise ValueError("sha256 은 64자 소문자 hex 여야 합니다")
    return root / sha256[:2] / sha256


def href_for(key: str) -> str:
    """응답의 파일 칸 값. 서명 URL 로 바꿔도 칸 이름과 타입은 같다(ADR-003 결정 2)."""
    return HREF_PREFIX + quote(key, safe="")


def store_bytes(root: Path, data: bytes) -> str:
    """바이트를 내용 주소로 두고 sha256 을 돌려준다. 없으면 임시 파일에 쓴 뒤 바꿔 넣고, 있으면 mtime 만 갱신한다."""
    sha256 = hashlib.sha256(data).hexdigest()
    path = path_for(root, sha256)
    if path.is_file():
        os.utime(path)
        return sha256
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)  # 같은 바이트를 동시에 올려도 결과는 같다
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return sha256


def gc_candidates(root: Path, referenced: set[str], grace: timedelta) -> list[Path]:
    """지울 바이트: 배치 규칙에 맞고 ∧ 참조 행 0 ∧ mtime 이 grace 보다 오래된 것. 고르기만 하고 지우지 않는다."""
    cutoff = time.time() - grace.total_seconds()
    found: list[Path] = []
    if not root.is_dir():
        return found
    for prefix in sorted(root.iterdir()):
        if not prefix.is_dir() or len(prefix.name) != 2:
            continue
        for path in sorted(prefix.iterdir()):
            name = path.name
            if (
                not _SHA256.fullmatch(name)
                or name[:2] != prefix.name
                or not path.is_file()
            ):
                continue
            if name in referenced or path.stat().st_mtime > cutoff:
                continue
            found.append(path)
    return found
