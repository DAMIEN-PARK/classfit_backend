"""커서 왕복과 깨진 커서(core/cursor.py). DB 없음."""

import base64
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from classfit.core.cursor import decode_cursor, encode_cursor


def _b64(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def test_cursor_roundtrip() -> None:
    cases = [
        (datetime(2026, 10, 22, 6, 30, 15, 123456, tzinfo=UTC), 1),
        (datetime(2026, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=9))), 2**53),
    ]
    for t, i in cases:
        s = encode_cursor(t, i)
        # URL 질의에 그대로 싣는다
        assert "=" not in s and "+" not in s and "/" not in s
        assert decode_cursor(s) == (t, i)


@pytest.mark.parametrize(
    "s",
    [
        "",
        "not base64 !",
        encode_cursor(datetime(2026, 10, 22, tzinfo=UTC), 7) + "*",
        _b64(b"not json"),
        _b64(b"\xff\xfe"),
        _b64(json.dumps([1, 2]).encode()),
        _b64(json.dumps({"t": "2026-10-22T00:00:00+00:00"}).encode()),
        _b64(json.dumps({"i": 1}).encode()),
        _b64(json.dumps({"t": "어제", "i": 1}).encode()),
        _b64(json.dumps({"t": "2026-10-22T00:00:00", "i": 1}).encode()),  # 시간대 없음
        _b64(json.dumps({"t": "2026-10-22T00:00:00+00:00", "i": "1"}).encode()),
        _b64(json.dumps({"t": "2026-10-22T00:00:00+00:00", "i": True}).encode()),
        _b64(json.dumps({"t": 1, "i": 1}).encode()),
        # id 는 1 부터, BIGINT(2**63 미만) 안
        _b64(json.dumps({"t": "2026-10-22T01:00:00+00:00", "i": 0}).encode()),
        _b64(json.dumps({"t": "2026-10-22T01:00:00+00:00", "i": 2**63}).encode()),
    ],
)
def test_cursor_tampered_raises(s: str) -> None:
    with pytest.raises(ValueError):
        decode_cursor(s)
