"""파일 저장소의 gc 지우기 규약(service/files/store.py — T6 codex 구현 리뷰 1차): 옮기고 나서 확인하고 지운다 ·
재업로드는 바이트를 잃지 않는다 · 옮긴 채 남은 무덤을 되살린다. DB 없음, tmp_path 저장소.

차례는 sleep 이 아니라 감싸개로 정한다: Path.unlink 감싸개가 무덤을 지우기 직전에 같은 바이트를 다시 올리고,
os.utime 감싸개가 store_bytes 의 mtime 갱신 직전에 파일을 무덤으로 옮긴다. 이름 접두는 test_file_store_ 다
(-k 'gc_' 셈에 들지 않게).
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

import pytest

from classfit.service.files.store import (
    path_for,
    remove_stale,
    restore_leftovers,
    store_bytes,
)


def _age(path: Path, hours: float) -> None:
    then = time.time() - hours * 3600
    os.utime(path, (then, then))


def _cutoff(hours: float = 24) -> float:
    return time.time() - hours * 3600


def _tombs(root: Path) -> list[str]:
    return sorted(p.name for p in root.rglob(".gc-*"))


def _old(root: Path, data: bytes) -> Path:
    """data 를 두고 48시간으로 늙힌 제자리 경로."""
    path = path_for(root, store_bytes(root, data))
    _age(path, 48)
    return path


def test_file_store_remove_stale_deletes_old_bytes(tmp_path: Path) -> None:
    path = _old(tmp_path, b"t6-store-old")
    assert remove_stale(path, _cutoff()) is True
    assert not path.exists()
    assert _tombs(tmp_path) == []
    assert remove_stale(path, _cutoff()) is False  # 이미 없다


def test_file_store_reupload_before_unlink_keeps_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """무덤을 지우기 직전에 같은 바이트가 다시 올라온다 → 제자리에 새로 써져 남고 False."""
    data = b"t6-store-reupload"
    path = _old(tmp_path, data)
    real = Path.unlink
    calls: list[str] = []

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.endswith(path.name) and not calls:
            calls.append(self.name)
            store_bytes(tmp_path, data)  # 업로드의 바이트 단계가 끼어든다
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    assert remove_stale(path, _cutoff()) is False
    assert len(calls) == 1
    assert path.read_bytes() == data
    assert _tombs(tmp_path) == []


def test_file_store_touched_before_rename_is_restored(tmp_path: Path) -> None:
    """gc 가 후보를 고른 뒤 옮기기 전에 같은 바이트가 다시 올라와 mtime 이 새로워짐 → 되돌려져 남고 False."""
    data = b"t6-store-touched"
    path = _old(tmp_path, data)
    cutoff = _cutoff()  # 후보를 고를 때의 기준
    store_bytes(tmp_path, data)
    assert remove_stale(path, cutoff) is False
    assert path.read_bytes() == data
    assert path.stat().st_mtime > cutoff
    assert _tombs(tmp_path) == []


def test_file_store_store_bytes_rewrites_when_moved_before_touch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """store_bytes 가 있는 것을 본 뒤 mtime 을 갱신하기 직전에 gc 가 옮긴다 → 새로 써서 바이트가 있다."""
    data = b"t6-store-moved"
    sha = store_bytes(tmp_path, data)
    path = path_for(tmp_path, sha)
    real = os.utime
    moved: list[Path] = []

    def utime(target: Any, *args: Any, **kwargs: Any) -> None:
        if Path(target) == path and not moved:
            tomb = path.with_name(f".gc-{'0' * 32}-{path.name}")
            os.rename(path, tomb)
            moved.append(tomb)
        real(target, *args, **kwargs)

    monkeypatch.setattr(os, "utime", utime)
    assert store_bytes(tmp_path, data) == sha
    assert len(moved) == 1
    assert path.read_bytes() == data


def test_file_store_restore_leftovers(tmp_path: Path) -> None:
    a, b = b"t6-left-a", b"t6-left-b"
    # a: 무덤만 남았다(gc 가 옮긴 채 죽음) → 되돌린다
    place_a = path_for(tmp_path, store_bytes(tmp_path, a))
    tomb_a = place_a.with_name(f".gc-{'1' * 32}-{place_a.name}")
    os.rename(place_a, tomb_a)
    # b: 제자리와 무덤이 둘 다 있다 → 무덤만 지운다
    place_b = path_for(tmp_path, store_bytes(tmp_path, b))
    tomb_b = place_b.with_name(f".gc-{'2' * 32}-{place_b.name}")
    tomb_b.write_bytes(b)
    # 규칙 밖: 다른 접두 폴더의 sha 무덤 · 이름 모양이 다른 .gc- · 임시 파일
    n = 0
    while (other := hashlib.sha256(b"t6-left-%d" % n).hexdigest())[
        :2
    ] == place_a.parent.name:
        n += 1
    strays = [
        place_a.parent / f".gc-{'3' * 32}-{other}",
        place_a.parent / ".gc-notes",
        place_a.parent / ".tmp-abc",
    ]
    for stray in strays:
        stray.write_bytes(b"stray")

    assert restore_leftovers(tmp_path) == [place_a.name]
    assert place_a.read_bytes() == a and not tomb_a.exists()
    assert place_b.read_bytes() == b and not tomb_b.exists()
    assert all(stray.read_bytes() == b"stray" for stray in strays)
    assert restore_leftovers(tmp_path) == []  # 두 번째는 할 일이 없다
    assert restore_leftovers(tmp_path / "missing") == []
