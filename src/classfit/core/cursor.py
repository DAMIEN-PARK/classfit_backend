"""목록 커서: base64url(JSON {"t": 시각, "i": id}), 덧붙임(=) 없음(백엔드 안내서 §3.1).

키셋은 (created_at, id) 다. 깨진 커서는 ValueError 다. 422 로 바꾸는 일은 목록 끝점이 한다.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime

_ALPHABET = re.compile(r"[A-Za-z0-9_-]+")
_MAX_ID = 2**63  # BIGINT 상한. 넘으면 DB 가 오류를 내서 422 대신 500 이 된다


def encode_cursor(t: datetime, i: int) -> str:
    raw = json.dumps({"t": t.isoformat(), "i": i}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(s: str) -> tuple[datetime, int]:
    """(시각, id). 알파벳 밖 글자·JSON 아님·칸 빠짐·시간대 없는 시각·0 < id < 2**63 밖은 ValueError."""
    # b64decode 는 기본값이 알파벳 밖 글자를 버리고 지나간다. 그래서 먼저 막는다
    if not _ALPHABET.fullmatch(s):
        raise ValueError("깨진 커서")
    try:
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        data = json.loads(raw)
        t = datetime.fromisoformat(data["t"])
        i = data["i"]
    except (ValueError, TypeError, KeyError, binascii.Error) as exc:
        raise ValueError("깨진 커서") from exc
    if t.tzinfo is None or type(i) is not int or not 0 < i < _MAX_ID:
        raise ValueError("깨진 커서")
    return t, i
