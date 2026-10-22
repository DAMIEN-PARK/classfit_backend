"""과정 풀 규칙(service.rules.pool): 하루 교시 수 · 차시표 격자 검사 · id 모양 · 내용 지문. DB 없음."""

import datetime as dt

import pytest

from classfit.service.rules.pool import (
    content_fingerprint,
    pool_id,
    slot_grid_errors,
    slots_per_day,
)


def test_pool_rules_slots_per_day() -> None:
    # 시안 강사.html:670 scSlots = max(1, ⌊(끝 − 시작 + 휴식) / (교시 + 휴식)⌋)
    assert slots_per_day(dt.time(13, 0), dt.time(17, 0), 50, 10) == 4
    assert slots_per_day(dt.time(9, 0), dt.time(18, 0), 50, 10) == 9
    assert slots_per_day(dt.time(9, 0), dt.time(10, 0), 60, 0) == 1
    assert slots_per_day(dt.time(9, 0), dt.time(9, 30), 50, 10) == 1  # 짧아도 1


def test_pool_rules_slot_grid_errors() -> None:
    assert slot_grid_errors(4, 4, []) == []
    ok = [{"day": 1, "slot": 1}, {"day": 4, "slot": 4}, {"day": 2, "slot": 3}]
    assert slot_grid_errors(4, 4, ok) == []
    bad = [
        {"day": 1, "slot": 1},
        {"day": 5, "slot": 1},  # 일 밖
        {"day": 1, "slot": 5},  # 교시 밖
        {"day": 0, "slot": 0},  # 둘 다 밖
        {"day": 1, "slot": 1},  # 0번과 겹침
    ]
    assert slot_grid_errors(4, 4, bad) == [
        (1, "day"),
        (2, "slot"),
        (3, "day"),
        (3, "slot"),
        (4, "duplicate"),
    ]
    # id 모양 세 접두 + 심화
    assert pool_id("own", 12, 3) == "own-3-12"
    assert pool_id("cur", 13, 3) == "cur-3-13"
    assert pool_id("ax-custom", 14) == "ax-custom-14"
    assert pool_id("adv", 15) == "adv-15"
    for prefix, instructor_id in (("own", None), ("adv", 3), ("ax", None)):
        with pytest.raises(ValueError):
            pool_id(prefix, 1, instructor_id)


def test_pool_rules_content_fingerprint() -> None:
    base = {
        "title": "시험 과정 가",
        "job_groups": ["공통(전 직원)"],
        "minutes": 60,
        "goal": None,
        "schedule": [["00:00", "이론", "개요"]],
    }
    reordered = {
        "schedule": [("00:00 ", "이론", " 개요")],
        "minutes": 60,
        "goal": None,
        "job_groups": [" 공통(전 직원)"],
        "title": "  시험 과정 가 ",
    }
    assert content_fingerprint(base) == content_fingerprint(reordered)
    assert len(content_fingerprint(base)) == 64
    assert content_fingerprint(base) != content_fingerprint({**base, "title": "시험 과정 나"})
    assert content_fingerprint(base) != content_fingerprint({**base, "minutes": 61})
    assert content_fingerprint(base) != content_fingerprint({**base, "goal": ""})
