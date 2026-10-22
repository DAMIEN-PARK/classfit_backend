"""파일 바이트 저장(ADR-003 결정 2·4 · Design 5절 9·10).

- 디스크 배치: `<root>/<sha256 앞 2자>/<sha256>`. 같은 바이트는 한 번만 쓰고, 이미 있으면 mtime 만 갱신한다
  (gc 유예가 다시 시작되어, 행이 커밋되기 전에 gc 가 지우지 못한다). 있는 줄 알았는데 mtime 갱신 직전에 gc 가
  옮겼으면(FileNotFoundError) 새로 쓴다.
- gc 의 지우기 한 건(remove_stale)은 "확인 → 지우기" 가 아니라 옮기고 나서 확인한다: 제자리를 같은 폴더의 무덤
  `.gc-<uuid hex>-<sha256>` 으로 os.rename → 무덤 mtime 이 유예 안이면(옮기기 전에 같은 바이트가 다시 올라왔다)
  os.replace 로 되돌린다 → 아니면 무덤을 지우고, 그 사이 같은 바이트가 제자리에 다시 쓰였으면 지우지 않은 것으로
  본다. 확인과 지우기 사이에 끼는 재업로드는 제자리에 바이트가 없으니 새로 쓴다 — 지운 것은 무덤뿐이다.
- 무덤 이름은 `.gc-` 로 시작해 _SHA256 fullmatch 에 걸리지 않으므로 gc_candidates 가 고르지 않는다. gc 가 옮긴 채
  죽으면 restore_leftovers 가 다음 gc 에서 되살린다(제자리가 비었으면 되돌리고, 있으면 같은 내용이라 무덤만 지운다).
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
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

_SHA256 = re.compile(r"[0-9a-f]{64}")
TOMB_PREFIX = ".gc-"
_TOMB = re.compile(r"\.gc-[0-9a-f]{32}-([0-9a-f]{64})")
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
    """바이트를 내용 주소로 두고 sha256 을 돌려준다. 없으면 임시 파일에 쓴 뒤 바꿔 넣고, 있으면 mtime 만 갱신한다.

    있는 것을 본 뒤 mtime 을 갱신하기 전에 gc 가 무덤으로 옮겼으면(FileNotFoundError) 새로 쓴다.
    """
    sha256 = hashlib.sha256(data).hexdigest()
    path = path_for(root, sha256)
    if path.is_file():
        try:
            os.utime(path)
            return sha256
        except FileNotFoundError:
            pass  # 그 사이 gc 가 옮겼다 — 아래에서 새로 쓴다
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


def remove_stale(path: Path, cutoff: float) -> bool:
    """gc 의 지우기 한 건. 옮기고(무덤) → 무덤 mtime 이 cutoff 뒤면 되돌리고 → 아니면 무덤을 지운다. 지웠으면 True.

    False: 이미 없음 · 옮기기 전에 같은 바이트가 다시 올라와 되돌림 · 무덤을 지우는 사이 같은 바이트가 제자리에 다시
    쓰임 · 무덤 단계에서 다른 gc 가 되돌림(FileNotFoundError). 되돌릴 때 그 사이 새로 쓴 제자리를 덮어도 같은 내용이다.
    """
    tomb = path.with_name(f"{TOMB_PREFIX}{uuid.uuid4().hex}-{path.name}")
    try:
        os.rename(path, tomb)
    except FileNotFoundError:
        return False
    try:
        if tomb.stat().st_mtime > cutoff:
            os.replace(tomb, path)
            return False
    except FileNotFoundError:
        return False
    tomb.unlink(missing_ok=True)
    return not path.exists()


def restore_leftovers(root: Path) -> list[str]:
    """gc 가 옮긴 채 남은 무덤을 되살린다. 되돌린 sha256 목록.

    두 글자 접두 폴더 안의 `.gc-<32자 hex>-<sha256>` 중 sha256 이 그 폴더의 것인 무덤만 본다(그 밖의 파일은 건드리지
    않는다). 제자리가 비었으면 os.replace 로 되돌리고, 있으면 같은 내용이라 무덤만 지운다.
    """
    restored: list[str] = []
    if not root.is_dir():
        return restored
    for prefix in sorted(root.iterdir()):
        if not prefix.is_dir() or len(prefix.name) != 2:
            continue
        for tomb in sorted(prefix.glob(f"{TOMB_PREFIX}*")):
            found = _TOMB.fullmatch(tomb.name)
            if found is None or found[1][:2] != prefix.name:
                continue
            place = prefix / found[1]
            try:
                if place.exists():
                    tomb.unlink()
                else:
                    os.replace(tomb, place)
                    restored.append(found[1])
            except FileNotFoundError:
                continue  # 다른 gc 가 먼저 처리했다
    return restored
