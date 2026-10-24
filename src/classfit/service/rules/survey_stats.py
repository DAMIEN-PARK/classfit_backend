"""만족도 집계 산식 한 곳(T8 결정 x · Design 5절 16). 순수 함수다 — DB·crud·models 를 부르지 않는다.

- 척도(scale) 문항: n(1..5 정수 응답 수) · avg(산술 평균, 소수 둘째 자리 ROUND_HALF_UP) · hundred(100점 환산 = 평균 × 20,
  정수 ROUND_HALF_UP) · positive_pct(4·5점 수 ÷ n × 100, 정수 ROUND_HALF_UP — 시안의 보정값은 쓰지 않는다) ·
  distribution(1~5 각 수). 응답 0건이면 avg·hundred·positive_pct 는 None 이다(0점처럼 보이지 않게).
- 영역: 그 영역 척도 문항 응답 전체를 모은 지표(문항 평균의 평균이 아니라 응답 가중 — 결측은 분모에서 빠진다).
  순서는 양식에 처음 나온 순서. 영역이 없는(None) 척도 문항은 어느 영역에도 들지 않는다.
- 종합: is_overall 인 척도 문항의 지표. 그 문항이 없거나 응답이 0건이면 None. 영역 이름으로 추론하지 않는다.
- 선택형(single·multi): 값마다 수(직접 입력 글자도 각자 한 값), 수 내림차순 → 글자 순. n 은 답한 응답 수.
- 주관식(text): 빈 값을 뺀 글자 목록을 글자 순으로(제출 순서가 남지 않게, 결정 xi). 안내문(info)은 집계하지 않는다.
- Decimal 로 센다. float 로 바꾸는 것은 응답을 만드는 쪽 몫이다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

SCALE_POINTS = (1, 2, 3, 4, 5)
POSITIVE_POINTS = (4, 5)
HUNDRED_FACTOR = 20  # 5점 → 100점(결정 x 기본, 강사 시안 svXls ×20)
_CENT = Decimal("0.01")
_ONE = Decimal(1)


@dataclass(frozen=True)
class ScaleStat:
    n: int
    avg: Decimal | None
    hundred: int | None
    positive_pct: int | None
    distribution: dict[int, int]


@dataclass(frozen=True)
class ChoiceStat:
    n: int
    values: list[tuple[str, int]]


@dataclass(frozen=True)
class AreaStat:
    area: str
    n: int
    avg: Decimal | None
    hundred: int | None
    positive_pct: int | None
    questions: list[str]  # 그 영역 척도 문항 key(양식 순서)


@dataclass(frozen=True)
class Aggregate:
    overall: ScaleStat | None
    areas: list[AreaStat]
    questions: dict[
        str, ScaleStat | ChoiceStat | None
    ]  # 문항 key → 지표(주관식·안내문은 None)
    texts: dict[str, list[str]]  # 주관식 key → 글자 순 목록


def _half_up(value: Decimal, unit: Decimal = _ONE) -> Decimal:
    return value.quantize(unit, rounding=ROUND_HALF_UP)


def to_hundred(avg: Decimal) -> int:
    """평균(5점 척도) → 100점 환산. avg × 20 을 정수로 ROUND_HALF_UP(4.5 → 90 · 4.25 → 85)."""
    return int(_half_up(avg * HUNDRED_FACTOR))


def percent(part: int, whole: int) -> int | None:
    """part ÷ whole × 100 을 정수로 ROUND_HALF_UP. whole 이 0 이면 None(응답률 분모 0)."""
    if whole == 0:
        return None
    return int(_half_up(Decimal(part) * 100 / Decimal(whole)))


def positive_pct(counts: Mapping[int, int]) -> int | None:
    """4·5점 응답 비율(%). 응답이 없으면 None."""
    n = sum(counts.get(p, 0) for p in SCALE_POINTS)
    return percent(sum(counts.get(p, 0) for p in POSITIVE_POINTS), n)


def _scale(counts: Mapping[int, int]) -> ScaleStat:
    n = sum(counts.get(p, 0) for p in SCALE_POINTS)
    distribution = {p: counts.get(p, 0) for p in SCALE_POINTS}
    if n == 0:
        return ScaleStat(0, None, None, None, distribution)
    exact = Decimal(sum(p * c for p, c in distribution.items())) / Decimal(n)
    return ScaleStat(
        n=n,
        avg=_half_up(exact, _CENT),
        hundred=to_hundred(exact),
        positive_pct=positive_pct(distribution),
        distribution=distribution,
    )


def _is_point(value: Any) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and value in SCALE_POINTS
    )


def _choice(values: Sequence[Any]) -> ChoiceStat:
    """values 는 응답마다 그 문항의 답(single 은 글자, multi 는 글자 목록). 답하지 않은 응답은 빠져 있다."""
    counter: Counter[str] = Counter()
    for value in values:
        picked = value if isinstance(value, list) else [value]
        counter.update(v for v in picked if isinstance(v, str))
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return ChoiceStat(n=len(values), values=ordered)


def aggregate(
    questions: Sequence[Mapping[str, Any]], answers_list: Sequence[Mapping[str, Any]]
) -> Aggregate:
    """문항(배포 복제본)과 응답들의 answers 로 지표를 만든다. 응답에 사람·시각 칸은 들어오지 않는다."""
    scale_counts: dict[str, Counter[int]] = {}
    per_question: dict[str, ScaleStat | ChoiceStat | None] = {}
    texts: dict[str, list[str]] = {}
    for q in questions:
        key, kind = q["key"], q["type"]
        given = [a[key] for a in answers_list if a.get(key) is not None]
        if kind == "scale":
            scale_counts[key] = Counter(v for v in given if _is_point(v))
            per_question[key] = _scale(scale_counts[key])
        elif kind in ("single", "multi"):
            per_question[key] = _choice(given)
        else:
            per_question[key] = None
            if kind == "text":
                texts[key] = sorted(
                    v.strip() for v in given if isinstance(v, str) and v.strip()
                )
    areas: dict[str, list[str]] = {}
    for q in questions:
        if q["type"] == "scale" and q.get("area"):
            areas.setdefault(q["area"], []).append(q["key"])
    area_stats = []
    for area, keys in areas.items():
        merged: Counter[int] = Counter()
        for key in keys:
            merged.update(scale_counts[key])
        stat = _scale(merged)
        area_stats.append(
            AreaStat(area, stat.n, stat.avg, stat.hundred, stat.positive_pct, keys)
        )
    overall = None
    for q in questions:
        if q["type"] == "scale" and q.get("is_overall"):
            found = per_question[q["key"]]
            overall = found if isinstance(found, ScaleStat) and found.n > 0 else None
            break
    return Aggregate(
        overall=overall, areas=area_stats, questions=per_question, texts=texts
    )
