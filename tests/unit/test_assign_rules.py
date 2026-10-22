"""배정 규칙(service.rules.schedule.place_in_free_slots): 풀에서 고른 세션을 빈 교시에 차례로 놓기. DB 없음.

시안 관리자.html:1840-1842 pmgo 가 scNextSlot(:667)을 고른 수만큼 도는 화면 처리기라 golden 이 아니라 여기서 잰다(T5 결정 xix).
"""

import pytest

from classfit.service.rules.schedule import place_in_free_slots


def test_assign_rules_place_in_free_slots() -> None:
    capacity = {1: 4, 2: 4}
    used = {1: {1, 3}}
    assert place_in_free_slots(capacity, used, 1, 5) == [
        (1, 2),
        (1, 4),
        (2, 1),
        (2, 2),
        (2, 3),
    ]
    assert place_in_free_slots(capacity, used, 1, 0) == []
    # 넘치면 끝에 None(일차 미정) — 고른 순서는 그대로다
    got = place_in_free_slots(capacity, used, 2, 6)
    assert got == [(2, 1), (2, 2), (2, 3), (2, 4), None, None]
    # 시작 일차보다 앞의 빈 교시는 쓰지 않는다
    assert place_in_free_slots(capacity, {}, 2, 1) == [(2, 1)]
    # 일차 번호가 이어지지 않아도 오름차순으로 넘어간다(DELETE 된 일차)
    assert place_in_free_slots({1: 1, 3: 2}, {}, 1, 3) == [(1, 1), (3, 1), (3, 2)]
    # 용량 밖의 쓴 교시는 셈에 들지 않는다
    assert place_in_free_slots({1: 2}, {1: {5}}, 1, 3) == [(1, 1), (1, 2), None]
    # 넘겨준 used 는 바꾸지 않는다
    assert used == {1: {1, 3}}


def test_assign_rules_place_without_day_is_undated() -> None:
    assert place_in_free_slots({1: 4}, {}, None, 3) == [None, None, None]
    assert place_in_free_slots({}, {}, None, 2) == [None, None]
    with pytest.raises(ValueError):
        place_in_free_slots({1: 4, 2: 4}, {}, 3, 1)
