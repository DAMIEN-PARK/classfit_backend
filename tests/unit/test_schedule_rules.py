"""일정 규칙(service/rules/schedule.py) ↔ 시안 golden(tests/fixtures/golden.json). DB 없음.

golden.json 은 scripts/golden/extract.mjs 가 시안 함수를 합성 사례로 돌린 값이다.
시안에서 다시 뽑아 대조하는 일은 scripts/golden/check.sh(pre-push)가 한다.
"""

import json
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace

from classfit.service.rules.schedule import (
    make_days,
    session_time,
    slot_count,
    slot_times,
)

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _t(s: str | None) -> time | None:
    return None if s is None else time.fromisoformat(s)


def _hm(t: time) -> str:
    return t.strftime("%H:%M")


def test_golden_schedule_make_days() -> None:
    cases = GOLDEN["make_days"]
    assert cases, "golden make_days 사례가 0개다"
    for case in cases:
        i = case["in"]
        days = make_days(
            date.fromisoformat(i["start"]),
            i["n"],
            time.fromisoformat(i["start_time"]),
            time.fromisoformat(i["end_time"]),
        )
        got = [
            {
                "no": d.no,
                "date": d.date.isoformat(),
                "start": _hm(d.start_time),
                "end": _hm(d.end_time),
            }
            for d in days
        ]
        assert got == case["out"], case["id"]


def test_golden_schedule_session_time() -> None:
    cases = GOLDEN["session_time"]
    assert cases, "golden session_time 사례가 0개다"
    for case in cases:
        i = case["in"]
        days = {
            d["no"]: SimpleNamespace(
                start_time=_t(d["start"]),
                end_time=_t(d["end"]),
                lunch_start=_t(d["lunch_start"]),
                lunch_end=_t(d["lunch_end"]),
            )
            for d in i["days"]
        }
        sessions = [
            SimpleNamespace(
                id=s["id"],
                section=s["section"],
                day_no=s["day_no"],
                slot=s["slot"],
                minutes=s["minutes"],
                time_start=_t(s["time_start"]),
                time_end=_t(s["time_end"]),
            )
            for s in i["sessions"]
        ]
        got = []
        for s in sessions:
            # 섹션의 세션을 통째로 넘긴다(일차는 session_time 이 거른다)
            section = [x for x in sessions if x.section == s.section]
            t = session_time(
                days.get(s.day_no), i["slot_min"], i["break_min"], section, s
            )
            got.append(
                {
                    "id": s.id,
                    "time": None if t is None else {"start": t[0], "end": t[1]},
                }
            )
        assert got == case["out"], case["id"]


def test_golden_schedule_slot_count() -> None:
    cases = GOLDEN["slot_count"]
    assert cases, "golden slot_count 사례가 0개다"
    for case in cases:
        i = case["in"]
        d = i["day"]
        day = SimpleNamespace(
            start_time=_t(d["start"]),
            end_time=_t(d["end"]),
            lunch_start=_t(d["lunch_start"]),
            lunch_end=_t(d["lunch_end"]),
        )
        times = [
            {"start": a, "end": b}
            for a, b in slot_times(day, i["slot_min"], i["break_min"])
        ]
        assert times == case["out"]["times"], case["id"]
        assert slot_count(day, i["slot_min"], i["break_min"]) == case["out"]["count"], (
            case["id"]
        )
