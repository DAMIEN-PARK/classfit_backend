"""교육 기록 상태 전이표(T7 결정 iii R1~R14)·계획 값·바뀐 칸·내려받기 이름. 순수 함수만(DB 없음).

R9~R14(계획대로·일괄 확인)의 "기록 있는 세션은 대상에서 빠진다"·"none 은 일괄 확인에서 빠진다"는 대상 고르기라
service(record_days)가 하고, 계약·행동 시험이 HTTP·두 트랜잭션으로 잰다. 여기서는 대상이 된 행의 다음 상태만 본다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time

import pytest

from classfit.service.rules.photo import download_name
from classfit.service.rules.record import (
    RecordFields,
    RecordRejected,
    after_confirm,
    after_save,
    changed_fields,
    is_past,
    plan_fields,
)

DAY = date(2026, 11, 2)

# (행, 지금, 누가, 바뀐 칸 있음, 다음) — after_save
SAVE_TABLE = [
    ("R1", "none", "instructor", True, "done"),
    ("R2", "done", "instructor", True, "done"),
    ("R3", "ok", "instructor", True, "done"),
    ("R4", "done", "instructor", False, "done"),
    ("R4", "ok", "instructor", False, "ok"),
    ("R5", "none", "admin", True, "ok"),
    ("R5", "done", "admin", True, "ok"),
    ("R5", "done", "admin", False, "ok"),
    ("R5", "ok", "admin", True, "ok"),
    ("R5", "ok", "admin", False, "ok"),
    # 계획대로 기록은 기록 없는 세션에만 저장한다(none → 강사 done · 관리자 ok)
    ("R9", "none", "instructor", True, "done"),
    ("R11", "none", "admin", True, "ok"),
]
# (행, 지금, 다음) — after_confirm. R13 일괄 확인은 done 행에 같은 판정을 쓴다
CONFIRM_TABLE = [
    ("R6", "done", "ok"),
    ("R7", "ok", "ok"),
    ("R13", "done", "ok"),
    ("R14", "ok", "ok"),
]


def test_record_rules_transition_table() -> None:
    for row, current, by, changed, expected in SAVE_TABLE:
        assert after_save(current, by, changed) == expected, row
    for row, current, expected in CONFIRM_TABLE:
        assert after_confirm(current) == expected, row
    with pytest.raises(RecordRejected) as caught:  # R8
        after_confirm("none")
    assert caught.value.reason == "no_record"
    # 지난 일차(R9·R11 의 조건, R17 은 그 반대): 일차 날짜 ≤ 오늘. 일차 없음은 지난 일차가 아니다
    assert is_past(DAY, DAY) is True
    assert is_past(DAY, date(2026, 11, 3)) is True
    assert is_past(date(2026, 11, 3), DAY) is False
    assert is_past(None, DAY) is False


def test_record_rules_plan_fields() -> None:
    for description, content in [
        ("  설명 그대로  ", "설명 그대로"),
        ("   \n ", "교육"),
        (None, "교육"),
    ]:
        r = plan_fields(
            day_date=DAY,
            times=("13:00", "13:50"),
            title="교육",
            description=description,
            enrolled=3,
        )
        assert r == RecordFields(
            held_on=DAY,
            start_time=time(13),
            end_time=time(13, 50),
            attendees=3,
            content=content,
            note=None,
        ), description
    # 시각을 못 정하면 둘 다 None: 일정표 없음 · 하루 끝에서 잘려 시작 ≥ 끝 · 시작이 24시를 넘음
    for times in [None, ("17:00", "17:00"), ("18:00", "17:00"), ("24:10", "17:00")]:
        r = plan_fields(
            day_date=DAY, times=times, title="교육", description=None, enrolled=0
        )
        assert (r.held_on, r.start_time, r.end_time, r.attendees) == (
            DAY,
            None,
            None,
            0,
        ), times


def test_record_rules_changed_fields() -> None:
    r = RecordFields(DAY, time(13), time(14), 1, "진행", None)
    assert changed_fields(r, r) == []
    assert changed_fields(r, replace(r)) == []
    changes = {
        "held_on": date(2026, 11, 3),
        "start_time": time(12),
        "end_time": time(15),
        "attendees": 2,
        "content": "수정",
        "note": "비고",
    }
    assert changed_fields(None, r) == list(changes)
    for name, value in changes.items():
        assert changed_fields(r, replace(r, **{name: value})) == [name]
    assert changed_fields(r, replace(r, attendees=None, note="비고")) == [
        "attendees",
        "note",
    ]


def test_photo_rules_download_name() -> None:
    for content_type, ext in [
        ("image/png", "png"),
        ("image/jpeg", "jpg"),
        ("image/webp", "webp"),
    ]:
        assert (
            download_name("A사", DAY, 1, 1, content_type)
            == f"A사_20261102_1일차_01.{ext}"
        )
    assert download_name("A사", date(2026, 10, 20), None, 1, "image/png") == (
        "A사_20261020_01.png"
    )  # 일차를 지운 세션
    assert (
        download_name("B사", DAY, 12, 10, "image/png") == "B사_20261102_12일차_10.png"
    )
    assert download_name("A 사/x:y\t", DAY, 2, 3, "image/jpeg") == (
        "A_사_x_y__20261102_2일차_03.jpg"
    )
