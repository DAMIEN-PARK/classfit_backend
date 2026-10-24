"""만족도 설문의 상태 · 열림·닫힘 날짜 · 문항 판 해시 · 문항 교차 규칙 · 답 검사(T8 결정 iii·v·vi·ix). 순수 함수다 —
DB·crud·models 를 부르지 않는다(tests/unit/test_import_rules.py). 오늘은 인자로 받는다(Design 5절 15).

- 상태는 저장하지 않는다: closed_at(관리자가 닫았거나 밀려난 시각)이 있으면 closed → 오늘 < 열림일 scheduled →
  오늘 ≤ 닫힘일 open → 그 밖 closed. 닫힘일 당일까지 열려 있다. SQL 판은 crud.survey.survey_status_sql 이고 경계가 같다.
- 열기 모드 now(오늘) · course_end(강의 종료일, 지났으면 오늘) · date(지정일, 오늘 이상). 닫기 모드 end_plus_14
  (종료일 + close_days, 열림일보다 앞이면 열림일 + REOPEN_DAYS) · open_plus_7(열림일 + REOPEN_DAYS) · date(지정일, 열림일
  이상). 어긋나면 DatesRejected(reason) — 부르는 쪽(service.surveys.deploy)이 강의 id 를 채운다.
- 문항은 아홉 키(key · type · text · area · required · star · is_overall · options · custom)가 늘 있는 dict 다(schemas 가
  정규화한다). 모양(키·타입·길이)은 schemas 몫이고 여기는 교차 규칙만 잰다(question_errors).
- 답은 {문항 key: 값}. scale 1..5 정수 · single 선택지 글자(custom 이면 선택지 밖 한 줄 글자도) · multi 중복 없는 선택지
  목록(custom 이면 선택지 밖 한 값까지) · text 2000자까지(줄바꿈·탭 말고 제어 문자 금지, 빈 값은 빠진 것) · info 는
  값이 없어야 한다. None 은 답하지 않은 것이다.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

SurveyStatus = Literal["scheduled", "open", "closed"]
# 시안 관리자.html:2058 "다시 열기 (7일)" · :2071 "열림 + 7". 다시 열기 · open_plus_7 · end_plus_14 의 되물림에 쓴다
REOPEN_DAYS = 7
SCALE_MIN, SCALE_MAX = 1, 5
CHOICE_TYPES = ("single", "multi")
TEXT_MAX = 2000
CUSTOM_MAX = 100  # 「직접 입력」 글자 상한(선택지 글자 상한과 같다)
HASH_LENGTH = 16
_LINE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")  # 한 줄 글자(선택지 밖 직접 입력)
_TEXT_CONTROL = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)  # 주관식 — 줄바꿈·탭은 받는다


class DatesRejected(ValueError):
    """풀린 열림·닫힘일이 규칙에 어긋난다(끝점이 422 로). course_id 는 service 가 채운다.

    reason: open_before_today · close_before_open · date_required · open_mode · close_mode(배포 모드 풀기) ·
    close_before_today(배포 설문 PATCH 의 닫힘일이 오늘보다 앞 — service.surveys.close.patch_survey).
    """

    def __init__(self, reason: str, course_id: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.course_id = course_id


@dataclass(frozen=True)
class QuestionIssue:
    """문항 교차 규칙 위반 하나. index 는 문항 차례(0부터, 목록 전체면 None), field 는 칸 이름."""

    index: int | None
    field: str
    reason: str


def status_at(
    *, open_on: date, close_on: date, closed_at: datetime | None, today: date
) -> SurveyStatus:
    if closed_at is not None:
        return "closed"
    if today < open_on:
        return "scheduled"
    if today <= close_on:
        return "open"
    return "closed"


def default_close_on(*, open_on: date, end_on: date, close_days: int) -> date:
    """end_plus_14 모드의 닫힘일: 종료일 + close_days. 그 날이 열림일보다 앞이면 열림일 + REOPEN_DAYS."""
    close_on = end_on + timedelta(days=close_days)
    if close_on < open_on:
        return open_on + timedelta(days=REOPEN_DAYS)
    return close_on


def _given_date(spec: Mapping[str, Any]) -> date:
    given = spec.get("date")
    if not isinstance(given, date):
        raise DatesRejected("date_required")
    return given


def resolve_dates(
    open: Mapping[str, Any],
    close: Mapping[str, Any],
    *,
    today: date,
    end_on: date,
    close_days: int,
) -> tuple[date, date]:
    """(열림일, 닫힘일). 모드 둘을 그 강의의 종료일과 오늘로 푼다(결정 vi)."""
    mode = open.get("mode")
    if mode == "now":
        open_on = today
    elif mode == "course_end":
        open_on = max(end_on, today)
    elif mode == "date":
        open_on = _given_date(open)
        if open_on < today:
            raise DatesRejected("open_before_today")
    else:
        raise DatesRejected("open_mode")
    mode = close.get("mode")
    if mode == "end_plus_14":
        close_on = default_close_on(
            open_on=open_on, end_on=end_on, close_days=close_days
        )
    elif mode == "open_plus_7":
        close_on = open_on + timedelta(days=REOPEN_DAYS)
    elif mode == "date":
        close_on = _given_date(close)
        if close_on < open_on:
            raise DatesRejected("close_before_open")
    else:
        raise DatesRejected("close_mode")
    return open_on, close_on


def questions_hash(questions: Sequence[Mapping[str, Any]]) -> str:
    """문항 판 해시: 정규화 JSON(키 정렬 · 공백 없음)의 sha256 앞 16자. 키 순서가 달라도 같고 글자 하나면 다르다."""
    raw = json.dumps(
        list(questions), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:HASH_LENGTH]


def question_errors(questions: Sequence[Mapping[str, Any]]) -> list[QuestionIssue]:
    """교차 규칙 위반(없으면 빈 목록): key 유일 · star·is_overall 은 scale 만 · is_overall 은 많아야 하나 · options 는
    선택형만(선택형은 있어야) · custom 은 선택형만 · info 는 필수 아님 · 답을 받는 문항(info 아님)이 하나 이상."""
    issues: list[QuestionIssue] = []
    seen: set[str] = set()
    overall = 0
    for i, q in enumerate(questions):
        key, kind = str(q.get("key")), q.get("type")
        if key in seen:
            issues.append(QuestionIssue(i, "key", "duplicate"))
        seen.add(key)
        if q.get("star") and kind != "scale":
            issues.append(QuestionIssue(i, "star", "scale_only"))
        if q.get("is_overall"):
            overall += 1
            if kind != "scale":
                issues.append(QuestionIssue(i, "is_overall", "scale_only"))
            elif overall > 1:
                issues.append(QuestionIssue(i, "is_overall", "many"))
        if kind in CHOICE_TYPES and not q.get("options"):
            issues.append(QuestionIssue(i, "options", "required"))
        if kind not in CHOICE_TYPES and q.get("options") is not None:
            issues.append(QuestionIssue(i, "options", "choice_only"))
        if q.get("custom") and kind not in CHOICE_TYPES:
            issues.append(QuestionIssue(i, "custom", "choice_only"))
        if kind == "info" and q.get("required"):
            issues.append(QuestionIssue(i, "required", "info"))
    if not any(q.get("type") != "info" for q in questions):
        issues.append(QuestionIssue(None, "questions", "no_answer_question"))
    return issues


def _custom_ok(value: str) -> bool:
    """선택지 밖 직접 입력 한 값: 앞뒤 공백 뺀 1..CUSTOM_MAX 자 · 제어 문자 없음."""
    text = value.strip()
    return 0 < len(text) <= CUSTOM_MAX and not _LINE_CONTROL.search(value)


def _blank(kind: str, value: Any) -> bool:
    """답하지 않은 것으로 볼 값: None · 빈 multi 목록 · 공백뿐인 주관식."""
    if value is None:
        return True
    if kind == "multi":
        return isinstance(value, list) and not value
    if kind == "text":
        return isinstance(value, str) and not value.strip()
    return False


def _valid(q: Mapping[str, Any], value: Any) -> bool:
    kind = q.get("type")
    options = q.get("options") or []
    if kind == "scale":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and SCALE_MIN <= value <= SCALE_MAX
        )
    if kind == "single":
        if not isinstance(value, str):
            return False
        return value.strip() in options or (bool(q.get("custom")) and _custom_ok(value))
    if kind == "multi":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return False
        picked = [v.strip() for v in value]
        if len(set(picked)) != len(picked):
            return False
        outside = [v for v in value if v.strip() not in options]
        if not outside:
            return True
        return bool(q.get("custom")) and len(outside) == 1 and _custom_ok(outside[0])
    if kind == "text":
        return (
            isinstance(value, str)
            and len(value.strip()) <= TEXT_MAX
            and not _TEXT_CONTROL.search(value)
        )
    return False  # info 는 값을 받지 않는다


def answer_errors(
    questions: Sequence[Mapping[str, Any]], answers: Mapping[str, Any]
) -> list[tuple[str, str]]:
    """(문항 key, 까닭) 목록 — missing(필수 누락) · unknown(모르는 key) · invalid(모양). 문항 순서, 모르는 key 는 뒤."""
    by_key = {q["key"]: q for q in questions}
    errors: list[tuple[str, str]] = []
    for q in questions:
        key, kind = q["key"], q["type"]
        value = answers.get(key)
        if kind == "info":
            if value is not None:
                errors.append((key, "invalid"))
            continue
        if _blank(kind, value):
            if q.get("required"):
                errors.append((key, "missing"))
            continue
        if not _valid(q, value):
            errors.append((key, "invalid"))
    errors += [(key, "unknown") for key in answers if key not in by_key]
    return errors


def normalize_answers(
    questions: Sequence[Mapping[str, Any]], answers: Mapping[str, Any]
) -> dict[str, Any]:
    """저장할 답(answer_errors 가 빈 뒤에 부른다): 문항 순서 · 답하지 않은 칸은 뺀다 · 글자는 앞뒤 공백을 빼고 주관식
    줄바꿈은 \\n 하나로."""
    normalized: dict[str, Any] = {}
    for q in questions:
        key, kind = q["key"], q["type"]
        value = answers.get(key)
        if kind == "info" or _blank(kind, value):
            continue
        if kind == "single":
            value = value.strip()
        elif kind == "multi":
            value = [v.strip() for v in value]
        elif kind == "text":
            value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized[key] = value
    return normalized
