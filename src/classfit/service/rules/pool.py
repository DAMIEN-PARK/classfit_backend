"""과정 풀 규칙(T4 결정 iii·xiii·xv). 순수 함수다 — DB·crud·models 를 부르지 않는다(tests/unit/test_import_rules.py).

- slots_per_day 는 시안 강사.html:670 scSlots 식이다. 커리큘럼에는 점심이 없다. golden 대상이 아니다
  (시안 두 판이 다르다: 관리자.html:678 은 점심을 뺀다).
- content_fingerprint 는 내용 칸 dict 의 지문이다: 키 정렬 JSON 의 sha256. 글자는 앞뒤 공백을 깎고 튜플은 목록으로 본다.
  import 의 unchanged·differs 판정이 쓴다(결정 iii).
- pool_id 는 관리자·강사가 만드는 id 의 글자 모양이다: ax-custom-<n> · adv-<n> · own-<강사 id>-<n> · cur-<강사 id>-<n>(결정 xiii).
- slot_grid_errors 는 차시표의 격자 밖·중복을 (차시 index, 사유) 로 돌려준다(결정 xv).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

GridReason = Literal["day", "slot", "duplicate"]
INSTRUCTOR_PREFIXES = ("own", "cur")
PLAIN_PREFIXES = ("ax-custom", "adv")


def _hm(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def slots_per_day(start: dt.time, end: dt.time, slot_min: int, break_min: int) -> int:
    """하루 교시 수 = max(1, ⌊(끝 − 시작 + 휴식) / (교시 + 휴식)⌋)(시안 scSlots)."""
    return max(1, (_hm(end) - _hm(start) + break_min) // (slot_min + break_min))


def _normal(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list | tuple):
        return [_normal(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _normal(v) for k, v in value.items()}
    if isinstance(value, dt.time | dt.date):
        return value.isoformat()
    return value


def content_fingerprint(fields: Mapping[str, Any]) -> str:
    """내용 칸의 sha256 hex. 키 순서·글자 앞뒤 공백·튜플/목록 차이는 지문을 바꾸지 않는다."""
    text = json.dumps(
        _normal(fields), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(text.encode()).hexdigest()


def pool_id(prefix: str, n: int, instructor_id: int | None = None) -> str:
    """새 id 글자. own·cur 는 강사 id 가 있어야 하고 ax-custom·adv 는 없어야 한다(아니면 ValueError)."""
    if prefix in INSTRUCTOR_PREFIXES:
        if instructor_id is None:
            raise ValueError(f"{prefix} id 에는 강사 id 가 있어야 한다")
        return f"{prefix}-{instructor_id}-{n}"
    if prefix in PLAIN_PREFIXES:
        if instructor_id is not None:
            raise ValueError(f"{prefix} id 에는 강사 id 를 넣지 않는다")
        return f"{prefix}-{n}"
    raise ValueError(f"모르는 id 접두: {prefix}")


def slot_grid_errors(
    days: int, per_day: int, slots: Sequence[Mapping[str, Any]]
) -> list[tuple[int, GridReason]]:
    """차시표 검사. 일이 1..days 밖이면 day, 교시가 1..per_day 밖이면 slot, 앞 차시와 (일, 교시)가 같으면 duplicate.

    빈 목록은 오류 0 이다. 한 차시에 사유가 둘이면 둘 다 낸다(격자 밖은 중복을 따로 보지 않는다).
    """
    errors: list[tuple[int, GridReason]] = []
    seen: set[tuple[int, int]] = set()
    for index, item in enumerate(slots):
        day, slot = item["day"], item["slot"]
        outside = False
        if not 1 <= day <= days:
            errors.append((index, "day"))
            outside = True
        if not 1 <= slot <= per_day:
            errors.append((index, "slot"))
            outside = True
        if outside:
            continue
        if (day, slot) in seen:
            errors.append((index, "duplicate"))
        seen.add((day, slot))
    return errors
