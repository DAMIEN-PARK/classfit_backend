"""만족도 설문 규칙(T8 결정 iii·v·vi·ix·x): 상태 · 기본 닫힘일 · 열기·닫기 모드 · 문항 판 해시 · 문항 교차 규칙 · 답 검사 ·
집계 · 반올림. 순수 함수만(DB 없음).

문항은 아홉 키 dict 다(schemas 가 정규화해 저장하는 꼴). 집계 표본은 합성 응답 7건이고 기대값은 손으로 셌다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from classfit.service.rules.survey import (
    REOPEN_DAYS,
    DatesRejected,
    QuestionIssue,
    answer_errors,
    default_close_on,
    normalize_answers,
    question_errors,
    questions_hash,
    resolve_dates,
    status_at,
)
from classfit.service.rules.survey_stats import (
    ChoiceStat,
    ScaleStat,
    aggregate,
    percent,
    positive_pct,
    to_hundred,
)

TODAY = date(2026, 11, 3)
END = date(2026, 11, 5)  # 시험 강의 종료일(tests/fixtures/courses.py DEFAULTS)
DAY = timedelta(days=1)
CLOSED_AT = datetime(2026, 11, 3, 9, tzinfo=UTC)


def _q(key: str, kind: str, **over: Any) -> dict[str, Any]:
    question = {
        "key": key,
        "type": kind,
        "text": f"{key} 문구",
        "area": None,
        "required": False,
        "star": False,
        "is_overall": False,
        "options": None,
        "custom": False,
    }
    return question | over


QUESTIONS = [
    _q("inf", "info"),
    _q("s1", "scale", area="A", required=True, star=True),
    _q("s2", "scale", area="A"),
    _q("s3", "scale", area="B"),
    _q("ov", "scale", area="종합", required=True, star=True, is_overall=True),
    _q("ch", "single", options=["x", "y", "z"], custom=True),
    _q("fix", "single", options=["예", "아니오"]),
    _q("mu", "multi", options=["p", "q"], custom=True),
    _q("tx", "text"),
]


def test_survey_rules_questions_hash() -> None:
    reordered = [dict(reversed(list(q.items()))) for q in QUESTIONS]
    assert questions_hash(reordered) == questions_hash(QUESTIONS)
    changed = [
        q | ({"text": q["text"] + "!"} if q["key"] == "s2" else {}) for q in QUESTIONS
    ]
    assert questions_hash(changed) != questions_hash(QUESTIONS)
    moved = [QUESTIONS[1], QUESTIONS[0], *QUESTIONS[2:]]  # 문항 순서는 판이 다르다
    assert questions_hash(moved) != questions_hash(QUESTIONS)
    digest = questions_hash(QUESTIONS)
    assert len(digest) == 16 and all(c in "0123456789abcdef" for c in digest)


def test_survey_rules_resolve_dates() -> None:
    def solve(
        open_: dict[str, Any], close: dict[str, Any], end_on: date = END
    ) -> tuple[date, date]:
        return resolve_dates(open_, close, today=TODAY, end_on=end_on, close_days=14)

    later = date(2026, 12, 1)
    # 열기 셋 × 닫기 셋
    assert solve({"mode": "now"}, {"mode": "end_plus_14"}) == (TODAY, END + 14 * DAY)
    assert solve({"mode": "now"}, {"mode": "open_plus_7"}) == (TODAY, TODAY + 7 * DAY)
    assert solve({"mode": "now"}, {"mode": "date", "date": later}) == (TODAY, later)
    assert solve({"mode": "course_end"}, {"mode": "end_plus_14"}) == (
        END,
        END + 14 * DAY,
    )
    assert solve({"mode": "course_end"}, {"mode": "open_plus_7"}) == (
        END,
        END + 7 * DAY,
    )
    assert solve({"mode": "course_end"}, {"mode": "date", "date": END}) == (END, END)
    assert solve({"mode": "date", "date": later}, {"mode": "end_plus_14"}) == (
        later,
        later + REOPEN_DAYS * DAY,  # 종료 + 14 가 열림보다 앞 → 열림 + 7
    )
    assert solve({"mode": "date", "date": later}, {"mode": "open_plus_7"}) == (
        later,
        later + 7 * DAY,
    )
    assert solve({"mode": "date", "date": TODAY}, {"mode": "date", "date": TODAY}) == (
        TODAY,
        TODAY,
    )
    # 지난 종료일이면 열림은 오늘, 닫힘은 그 종료일 + 14(오늘 이상)
    past_end = TODAY - 3 * DAY
    assert solve({"mode": "course_end"}, {"mode": "end_plus_14"}, past_end) == (
        TODAY,
        past_end + 14 * DAY,
    )
    # 종료일 + 14 도 지났으면 열림 + 7
    long_ago = TODAY - 30 * DAY
    assert solve({"mode": "now"}, {"mode": "end_plus_14"}, long_ago) == (
        TODAY,
        TODAY + 7 * DAY,
    )

    bad = [
        (
            {"mode": "date", "date": TODAY - DAY},
            {"mode": "open_plus_7"},
            "open_before_today",
        ),
        ({"mode": "now"}, {"mode": "date", "date": TODAY - DAY}, "close_before_open"),
        ({"mode": "date"}, {"mode": "open_plus_7"}, "date_required"),
        ({"mode": "now"}, {"mode": "date"}, "date_required"),
        ({"mode": "soon"}, {"mode": "open_plus_7"}, "open_mode"),
        ({"mode": "now"}, {"mode": "later"}, "close_mode"),
    ]
    for open_, close, reason in bad:
        with pytest.raises(DatesRejected) as caught:
            solve(open_, close)
        assert (caught.value.reason, caught.value.course_id) == (reason, None), reason


def test_survey_rules_status_at() -> None:
    open_on, close_on = date(2026, 11, 5), date(2026, 11, 19)

    def at(today: date, closed_at: datetime | None = None) -> str:
        return status_at(
            open_on=open_on, close_on=close_on, closed_at=closed_at, today=today
        )

    assert at(open_on - DAY) == "scheduled"
    assert at(open_on) == "open"  # 열림일 당일
    assert at(close_on) == "open"  # 닫힘일 당일까지
    assert at(close_on + DAY) == "closed"
    # 관리자가 닫으면 날짜와 무관하게 closed(예약 중에 닫아도)
    assert at(open_on - DAY, CLOSED_AT) == "closed"
    assert at(open_on + DAY, CLOSED_AT) == "closed"
    # 다시 열기 뒤(closed_at 없음 · 닫힘일 오늘 + 7) 다시 open
    reopened = status_at(
        open_on=open_on,
        close_on=close_on + 7 * DAY,
        closed_at=None,
        today=close_on + DAY,
    )
    assert reopened == "open"


def test_survey_rules_default_close_on() -> None:
    assert default_close_on(open_on=TODAY, end_on=END, close_days=14) == END + 14 * DAY
    # 경계: 종료 + 14 가 열림일과 같은 날이면 그 날
    same = END + 14 * DAY
    assert default_close_on(open_on=same, end_on=END, close_days=14) == same
    # 열림일보다 앞이면 열림 + 7
    after = same + DAY
    assert default_close_on(open_on=after, end_on=END, close_days=14) == after + 7 * DAY
    # 설정 칸이 일수를 바꾼다
    assert default_close_on(open_on=TODAY, end_on=END, close_days=3) == END + 3 * DAY


def test_survey_rules_question_errors() -> None:
    assert question_errors(QUESTIONS) == []
    # is_overall 0개는 통과(결과의 overall 이 null 이 될 뿐)
    no_overall = [q | {"is_overall": False} for q in QUESTIONS]
    assert question_errors(no_overall) == []

    def issues(*questions: dict[str, Any]) -> list[QuestionIssue]:
        return question_errors(list(questions))

    s = _q("s", "scale")
    assert issues(s, _q("s", "text")) == [QuestionIssue(1, "key", "duplicate")]
    assert issues(s, _q("t", "text", star=True)) == [
        QuestionIssue(1, "star", "scale_only")
    ]
    assert issues(s, _q("t", "single", options=["a", "b"], is_overall=True)) == [
        QuestionIssue(1, "is_overall", "scale_only")
    ]
    assert issues(
        _q("a", "scale", is_overall=True), _q("b", "scale", is_overall=True)
    ) == [QuestionIssue(1, "is_overall", "many")]
    assert issues(s, _q("t", "text", options=["a", "b"])) == [
        QuestionIssue(1, "options", "choice_only")
    ]
    assert issues(s, _q("t", "single")) == [QuestionIssue(1, "options", "required")]
    assert issues(s, _q("t", "scale", custom=True)) == [
        QuestionIssue(1, "custom", "choice_only")
    ]
    assert issues(s, _q("t", "info", required=True)) == [
        QuestionIssue(1, "required", "info")
    ]
    assert issues(_q("i", "info")) == [
        QuestionIssue(None, "questions", "no_answer_question")
    ]
    assert question_errors([]) == [
        QuestionIssue(None, "questions", "no_answer_question")
    ]


def test_survey_rules_answer_errors() -> None:
    ok = {
        "s1": 5,
        "ov": 4,
        "ch": "직접 쓴 부서",  # custom — 선택지 밖 한 줄 글자
        "fix": "예",
        "mu": ["p", "기타"],  # custom — 선택지 밖 한 값까지
        "tx": "여러 줄\n소감",
    }
    assert answer_errors(QUESTIONS, ok) == []
    assert answer_errors(QUESTIONS, {"s1": 1, "ov": 5}) == []  # 필수만
    # 답하지 않은 칸(None · 빈 목록 · 공백뿐 주관식)은 필수가 아니면 통과
    assert (
        answer_errors(QUESTIONS, {"s1": 1, "ov": 5, "s2": None, "mu": [], "tx": "  "})
        == []
    )

    def errors(**over: Any) -> list[tuple[str, str]]:
        return answer_errors(QUESTIONS, {"s1": 3, "ov": 3} | over)

    assert answer_errors(QUESTIONS, {"s1": 3}) == [("ov", "missing")]
    assert answer_errors(QUESTIONS, {"ov": 3, "s1": None}) == [("s1", "missing")]
    assert errors(nope=1) == [("nope", "unknown")]
    for bad in (0, 6, "4", 4.0, True):
        assert errors(s2=bad) == [("s2", "invalid")], bad
    assert errors(fix="몰라") == [("fix", "invalid")]  # 선택지 밖(custom 없음)
    assert errors(ch="   ") == [("ch", "invalid")]  # custom 공백뿐
    assert errors(ch="가" * 101) == [("ch", "invalid")]
    assert errors(ch="한 줄\n아님") == [("ch", "invalid")]
    assert errors(ch=["x"]) == [("ch", "invalid")]
    assert errors(mu=["p", "p"]) == [("mu", "invalid")]  # 중복
    assert errors(mu=["기타1", "기타2"]) == [("mu", "invalid")]  # 선택지 밖 둘
    assert errors(mu="p") == [("mu", "invalid")]
    assert errors(mu=[["p"]]) == [("mu", "invalid")]
    assert errors(tx="가" * 2001) == [("tx", "invalid")]
    assert errors(tx="가" * 2000) == []
    assert errors(tx="NUL\x00") == [("tx", "invalid")]
    assert errors(tx={"깊이": [1]}) == [("tx", "invalid")]
    assert errors(inf="값") == [("inf", "invalid")]  # 안내문에 값

    normalized = normalize_answers(
        QUESTIONS,
        {
            "tx": " 첫 줄\r\n둘째 ",
            "ov": 4,
            "ch": "  y ",
            "s1": 2,
            "mu": [" q"],
            "s2": None,
        },
    )
    assert normalized == {"s1": 2, "ov": 4, "ch": "y", "mu": ["q"], "tx": "첫 줄\n둘째"}
    assert list(normalized) == ["s1", "ov", "ch", "mu", "tx"]  # 문항 순서
    assert normalize_answers(QUESTIONS, {"s1": 1, "ov": 1, "tx": " ", "mu": []}) == {
        "s1": 1,
        "ov": 1,
    }


# 합성 응답 7건(값은 손으로 셌다)
ANSWERS: list[dict[str, Any]] = [
    {"s1": 5, "s2": 5, "s3": 3, "ov": 5, "ch": "x", "mu": ["p", "q"], "tx": "좋았다"},
    {"s1": 4, "s2": 4, "s3": 3, "ov": 5, "ch": "y", "mu": ["q"]},
    {
        "s1": 4,
        "s2": 5,
        "s3": 2,
        "ov": 4,
        "ch": "x",
        "mu": ["q", "기타 의견"],
        "tx": "가나다",
    },
    {"s1": 5, "s2": 4, "s3": 1, "ov": 4, "ch": "z", "tx": "나중"},
    {"s1": 3, "s2": 5, "s3": 5, "ov": 4, "ch": "직접 쓴 값", "mu": ["p"], "tx": "abc"},
    {"s1": 5, "s2": 4, "s3": 4, "ov": 3, "ch": "x"},
    {"s1": 4, "ov": 2, "fix": "예"},
]


def test_survey_rules_aggregate() -> None:
    result = aggregate(QUESTIONS, ANSWERS)
    s1, s2, s3 = (result.questions[k] for k in ("s1", "s2", "s3"))
    assert s1 == ScaleStat(7, Decimal("4.29"), 86, 86, {1: 0, 2: 0, 3: 1, 4: 3, 5: 3})
    assert s2 == ScaleStat(
        6, Decimal("4.50"), 90, 100, {1: 0, 2: 0, 3: 0, 4: 3, 5: 3}
    )  # 4.5 → 90
    assert s3 == ScaleStat(6, Decimal("3.00"), 60, 33, {1: 1, 2: 1, 3: 2, 4: 1, 5: 1})
    # 영역 A 는 응답 가중(57/13 = 4.38) — 문항 평균의 평균(4.39)이 아니다
    area_a, area_b, area_overall = result.areas
    assert (area_a.area, area_a.n, area_a.avg, area_a.hundred, area_a.positive_pct) == (
        "A",
        13,
        Decimal("4.38"),
        88,
        92,
    )
    assert area_a.questions == ["s1", "s2"]
    assert (area_b.area, area_b.questions, area_b.avg) == ("B", ["s3"], Decimal("3.00"))
    assert (area_overall.area, area_overall.questions) == ("종합", ["ov"])
    # 종합은 is_overall 문항
    assert result.overall == ScaleStat(
        7, Decimal("3.86"), 77, 71, {1: 0, 2: 1, 3: 1, 4: 3, 5: 2}
    )
    # 선택형: 수 내림차순 → 글자 순, 직접 입력 값도 각자
    assert result.questions["ch"] == ChoiceStat(
        6, [("x", 3), ("y", 1), ("z", 1), ("직접 쓴 값", 1)]
    )
    assert result.questions["mu"] == ChoiceStat(
        4, [("q", 3), ("p", 2), ("기타 의견", 1)]
    )
    assert result.questions["fix"] == ChoiceStat(1, [("예", 1)])
    assert result.questions["tx"] is None and result.questions["inf"] is None
    # 주관식: 빈 값 빼고 글자 순(제출 순서가 남지 않는다)
    assert result.texts == {"tx": ["abc", "가나다", "나중", "좋았다"]}
    assert "inf" not in result.texts

    # is_overall 문항이 없으면 종합 null(영역 "종합" 이름으로 추론하지 않는다)
    no_overall = [q | {"is_overall": False} for q in QUESTIONS]
    assert aggregate(no_overall, ANSWERS).overall is None

    # 응답 0건: 척도 지표 null · 종합 null · 분포 0 · 선택형 빈 · 주관식 빈
    empty = aggregate(QUESTIONS, [])
    assert empty.overall is None
    assert empty.questions["s1"] == ScaleStat(
        0, None, None, None, dict.fromkeys(range(1, 6), 0)
    )
    assert [(a.area, a.n, a.avg, a.hundred, a.positive_pct) for a in empty.areas] == [
        ("A", 0, None, None, None),
        ("B", 0, None, None, None),
        ("종합", 0, None, None, None),
    ]
    assert empty.questions["ch"] == ChoiceStat(0, [])
    assert empty.texts == {"tx": []}


def test_survey_rules_rounding_half_up() -> None:
    assert to_hundred(Decimal("4.25")) == 85
    assert to_hundred(Decimal("4.5")) == 90
    assert to_hundred(Decimal("4.125")) == 83  # 82.5 → 83(은행가 반올림이면 82)
    assert positive_pct({4: 1, 5: 1, 1: 1}) == 67  # 2/3
    assert positive_pct({}) is None
    assert percent(1, 3) == 33
    assert percent(2, 3) == 67
    assert percent(1, 8) == 13  # 12.5 → 13
    assert percent(0, 0) is None
    # 평균 소수 둘째 자리도 HALF_UP: 33/8 = 4.125 → 4.13 · 100점 83
    scale = [_q("s", "scale")]
    stat = aggregate(scale, [{"s": v} for v in (5, 5, 5, 4, 4, 4, 3, 3)]).questions["s"]
    assert stat == ScaleStat(8, Decimal("4.13"), 83, 75, {1: 0, 2: 0, 3: 2, 4: 3, 5: 3})
