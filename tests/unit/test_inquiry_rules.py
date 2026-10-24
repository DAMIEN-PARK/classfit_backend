"""교육 문의 규칙·설정(T9b 결정 iii·iv·v·viii·xxiii·xxiv): 영수증 모양 · honeypot · 창 상수 · 규모 4구간 · 설정 칸. DB 없음."""

import os
import re
from datetime import timedelta
from typing import get_args

import pytest
from pydantic import ValidationError

from classfit.core.config import Settings
from classfit.models import inquiry as models_inquiry
from classfit.service.rules import inquiry as rules_inquiry
from classfit.service.rules.invite import INVITE_ALPHABET
from tests.fixtures.inquiry import RECEIPT_RE


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("CLASSFIT_"):
            monkeypatch.delenv(key)


def test_inquiry_rules_receipt_no_shape() -> None:
    drawn = [rules_inquiry.new_receipt_no() for _ in range(1000)]
    assert len(set(drawn)) == 1000
    for receipt in drawn:
        assert len(receipt) == rules_inquiry.RECEIPT_LENGTH == 10
        assert set(receipt) <= set(INVITE_ALPHABET)
        assert re.fullmatch(RECEIPT_RE, receipt), receipt
    # 혼동 문자 0·O·1·I 는 알파벳에 없다
    assert not set("0O1I") & set(INVITE_ALPHABET)


def test_inquiry_rules_honeypot_and_sizes() -> None:
    for blank in (None, "", "  ", "\t\n"):
        assert rules_inquiry.is_honeypot(blank) is False, repr(blank)
    for filled in ("x", " https://example.com "):
        assert rules_inquiry.is_honeypot(filled) is True, filled
    assert rules_inquiry.DUPLICATE_WINDOW == timedelta(minutes=1)
    assert rules_inquiry.DAILY_WINDOW == timedelta(hours=24)
    assert rules_inquiry.RECEIPT_TRIES == 3

    sizes = models_inquiry.INQUIRY_SIZES
    assert sizes == get_args(models_inquiry.InquirySize)
    assert sizes == ("under_30", "30_99", "100_299", "300_plus")
    assert set(models_inquiry.INQUIRY_SIZE_LABELS) == set(sizes)
    (size_check,) = [
        str(c.sqltext)
        for c in models_inquiry.Inquiry.__table__.constraints
        if c.name == "ck_inquiry_company_size"
    ]
    for size in sizes:
        assert f"'{size}'" in size_check, (size, size_check)


def test_inquiry_settings_notify_to_blank_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for blank in ("", "  "):
        settings = Settings(_env_file=None, inquiry_notify_to=blank)
        assert settings.inquiry_notify_to is None
        assert settings.missing("inquiry_notify_to") == ["CLASSFIT_INQUIRY_NOTIFY_TO"]
    assert Settings(_env_file=None).missing("inquiry_notify_to") == [
        "CLASSFIT_INQUIRY_NOTIFY_TO"
    ]

    ok = Settings(_env_file=None, inquiry_notify_to="ops@example.com")
    assert ok.inquiry_notify_to == "ops@example.com"
    assert ok.missing("inquiry_notify_to") == []
    for bad in ("not-an-email", "ops@example", "a b@example.com", "ops@@example.com"):
        with pytest.raises(ValidationError, match="이메일 모양"):
            Settings(_env_file=None, inquiry_notify_to=bad)

    defaults = Settings(_env_file=None)
    assert defaults.inquiry_body_max_bytes == 65536
    assert defaults.inquiry_daily_max == 20
    for name in ("inquiry_body_max_bytes", "inquiry_daily_max"):
        with pytest.raises(ValidationError, match="1 이상"):
            Settings(_env_file=None, **{name: 0})

    # 환경 변수 이름은 CLASSFIT_ + 필드 이름이다. .env.example 을 그대로 복사한 빈 값도 미구성이다
    monkeypatch.setenv("CLASSFIT_INQUIRY_NOTIFY_TO", "ops@example.com")
    assert Settings(_env_file=None).inquiry_notify_to == "ops@example.com"
    monkeypatch.setenv("CLASSFIT_INQUIRY_NOTIFY_TO", "")
    assert Settings(_env_file=None).inquiry_notify_to is None
