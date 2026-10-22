"""강의·초대코드 상태 판정(service/rules/status.py). DB 없음.

경계는 T2a 계획 결정 iii: 종료일 당일은 running, 다음 날부터 ended. 코드는 만료일 당일까지 유효.
"""

from datetime import date, timedelta

from classfit.service.rules.status import code_state_at, course_status_at

START = date(2026, 11, 2)
END = date(2026, 11, 5)
DAY = timedelta(days=1)


def _course(today: date, *, status: str = "prep", manual: bool = False) -> str:
    return course_status_at(
        start_on=START, end_on=END, status=status, status_manual=manual, today=today
    )


def _code(
    *, code_status: str = "active", expires_on: date, course_status: str, today: date
) -> str:
    return code_state_at(
        code_status=code_status,
        expires_on=expires_on,
        course_status=course_status,
        today=today,
    )


def test_course_status_dates_prep_running_ended() -> None:
    assert _course(START - DAY) == "prep"
    assert _course(START) == "running"
    assert _course(END) == "running"  # 종료일 당일은 running
    assert _course(END + DAY) == "ended"
    one_day = course_status_at(
        start_on=START, end_on=START, status="prep", status_manual=False, today=START
    )
    assert one_day == "running"


def test_course_status_manual_wins() -> None:
    for today in (START - DAY, START, END, END + DAY):
        for status in ("prep", "running", "ended"):
            assert _course(today, status=status, manual=True) == status
    # 수동이 아니면 저장된 status 는 날짜 규칙에 진다
    assert _course(START - DAY, status="ended") == "prep"
    assert _course(END + DAY, status="running") == "ended"


def test_code_state_stopped_when_course_ended() -> None:
    expires_on = END + 30 * DAY
    for code_status in ("active", "paused"):
        state = _code(
            code_status=code_status,
            expires_on=expires_on,
            course_status="ended",
            today=END + DAY,
        )
        assert state == "stopped"
    # 계산값으로 잇는다: 종료일 당일은 active, 다음 날 stopped
    for today, want in ((END, "active"), (END + DAY, "stopped")):
        assert (
            _code(expires_on=expires_on, course_status=_course(today), today=today)
            == want
        )


def test_code_state_order() -> None:
    today = END + 40 * DAY
    past, future = today - DAY, today + DAY
    # replaced → stopped → paused → expired → active, 먼저 맞는 것
    assert (
        _code(
            code_status="replaced", expires_on=past, course_status="ended", today=today
        )
        == "replaced"
    )
    assert (
        _code(code_status="paused", expires_on=past, course_status="ended", today=today)
        == "stopped"
    )
    assert (
        _code(
            code_status="paused", expires_on=past, course_status="running", today=today
        )
        == "paused"
    )
    assert _code(expires_on=past, course_status="running", today=today) == "expired"
    assert _code(expires_on=future, course_status="running", today=today) == "active"
    assert _code(expires_on=future, course_status="prep", today=today) == "active"


def test_code_state_valid_through_expires_on() -> None:
    expires_on = date(2026, 12, 5)
    for today, want in (
        (expires_on - DAY, "active"),
        (expires_on, "active"),
        (expires_on + DAY, "expired"),
    ):
        assert (
            _code(expires_on=expires_on, course_status="running", today=today) == want
        )
