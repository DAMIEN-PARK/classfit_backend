"""정면 재노출을 patch 하면 실패, 원래 모듈을 patch 하면 통과."""

import pytest


def test_patching_facade_reexport_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(pytest.fail.Exception, match="stale patch"):
        monkeypatch.setattr("classfit.models.AuditLog", object())


def test_patching_origin_module_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    import classfit.models.audit as origin

    sentinel = object()
    monkeypatch.setattr("classfit.models.audit.AuditLog", sentinel)
    assert origin.AuditLog is sentinel
