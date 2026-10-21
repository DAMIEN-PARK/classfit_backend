"""재노출 껍데기(facade)를 monkeypatch 하면 시험을 죽인다 — 거짓 초록 방지.

classfit.models 같은 정면 모듈은 이름을 다른 모듈에서 가져와 다시 내보낸다. 거기를 patch 하면
실제 호출 지점(원래 모듈을 import 한 쪽)은 그대로라 patch 가 껍데기만 때린다.
새 정면을 만들면 FACADES 에 더한다 (예: classfit.service.<x>).
unittest.mock.patch 는 여기서 못 본다 — scripts/gate.sh 4번이 grep 으로 막는다.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterator
from typing import Any

import pytest

FACADES = frozenset({"classfit.models"})


def _resolve(target: Any, name: Any) -> tuple[str | None, str | None]:
    if isinstance(target, str):
        module, _, attr = target.rpartition(".")
        return module, attr
    if inspect.ismodule(target) and isinstance(name, str):
        return target.__name__, name
    return None, None


def _check(module: str | None, attr: str | None) -> None:
    if module not in FACADES or not attr:
        return
    try:
        loaded = importlib.import_module(module)  # 아직 import 전이어도 확실히 적재한 뒤 본다
    except ImportError:
        return
    obj = getattr(loaded, attr, None)
    origin = getattr(obj, "__module__", None)
    if origin and origin != module:
        pytest.fail(
            f"stale patch: {module}.{attr} 은 {origin} 에서 온 재노출입니다. "
            f"{origin}.{attr} 을 patch 하세요 (껍데기를 때리면 초록이 거짓말이 됩니다)",
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _stale_patch_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    original = monkeypatch.setattr

    def guarded(*args: Any, **kwargs: Any) -> None:
        target = args[0] if args else kwargs.get("target")
        name = args[1] if len(args) > 1 else kwargs.get("name")
        _check(*_resolve(target, name))
        original(*args, **kwargs)

    monkeypatch.setattr = guarded  # type: ignore[method-assign]
    try:
        yield
    finally:
        del monkeypatch.setattr
