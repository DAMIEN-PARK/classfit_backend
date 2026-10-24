"""AX 진단의 문항 조립·산식·상태 판정(T9a 결정 iv·v·xv). 순수 함수 — DB·시계를 모른다.

- 문항 원본은 diagnosis_items.py(영역 01·02)·diagnosis_items_34.py(03·04) 두 데이터 파일이고 여기서만 조립한다.
- 산식은 시안 관리자.html:1037 calc 와 같은 값이다(golden — scripts/golden/extract.mjs 의 score 사례). 지표 점수
  l / 5 * (200 / n) 을 영역 안에서 같은 차례로 더하고 영역마다 0.5 올림(Math.round — Python round() 는 짝수 반올림이라
  쓰지 않는다)한 뒤 네 영역을 더한다. 레벨은 160·320·480·640 경계(요구정의서 6.4). 미응답 지표는 0점이다.
- 모든 지표 1 이면 160 → L2 다(DEC-003 — 산식을 바꾸지 않는다). 응답 모양의 level 은 17지표 전부 답하기 전엔 None
  (shown_level). score() 는 golden 과 같이 늘 level 을 계산한다.
- 답 키는 시안 `ai-ii`("0-0"~"3-3"), 값은 1..5. 키·값이 밖이면 ValueError(끝점은 스키마가 먼저 422 로 막는다).
- 상태: 회차 draft·review 는 고칠 수 있고 final 은 못 고친다. 링크 회차는 제출일(diagnosed_on)이 잠긴다.
  링크 만료는 저장하지 않고 계산한다(open ∧ expires_on < today, 만료일 당일은 유효).
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from classfit.service.rules.diagnosis_items import AREAS_12, Area
from classfit.service.rules.diagnosis_items_34 import AREAS_34

AREAS: tuple[Area, ...] = (*AREAS_12, *AREAS_34)
# 영역마다 지표 수(models.diagnosis.AREA_SIZES 와 같다 — 단위 시험이 잰다)
AREA_SIZES = (5, 4, 4, 4)
ANSWER_KEYS = tuple(f"{a}-{i}" for a, n in enumerate(AREA_SIZES) for i in range(n))
AREA_POINTS = 200  # 영역 배점(총 800)
LEVEL_BOUNDS = (160, 320, 480, 640)
LEVEL_RANGE = (1, 5)
EDITABLE_STATUSES = ("draft", "review")
LINK_FROZEN = frozenset({"diagnosed_on"})  # 링크 회차의 잠긴 칸(제출일, 기획안 :832)
# 현장 활용 현황의 선택지(시안 :1032 FIELD · :1916-1921 select). 빈 선택("선택")은 값이 아니라 뺐다
FIELD_OPTIONS: dict[str, tuple[str, ...]] = {
    "ratio": ("10% 미만", "10~30%", "30~50%", "50~70%", "70% 이상"),
    "freq": ("월 1~2회", "주 1회", "주 2~3회", "거의 매일"),
    "tools": ("ChatGPT", "Claude", "Gemini", "Copilot", "사내 도입 도구", "기타"),
    "uses": (
        "문서·보고서 작성",
        "번역",
        "자료 검색·요약",
        "데이터 분석",
        "코드·수식",
        "이미지·디자인",
        "고객 응대·이메일",
    ),
    "works": (
        "기술지원·고객응대",
        "문서·매뉴얼 검색",
        "보고서·품의서 작성",
        "데이터 입력·정리",
        "품질 검사·불량 분석",
        "생산·재고 계획",
        "영업·견적·제안",
        "인사·총무·회계",
        "설계·연구개발",
    ),
    "wfreq": ("매일", "주 몇 번", "월 몇 번", "분기"),
}
ROLES = ("경영진", "기술직", "운영직")  # 직군별 역량 행(시안 :1033)
COMPETENCIES = (
    "AI 기초 이해도",
    "AX 업무 적용도",
    "AX 추진 의지",
    "직무 특화 역량",
)  # 열
LEVEL_NAMES = {
    1: "L1 · 인식",
    2: "L2 · 준비",
    3: "L3 · 적용",
    4: "L4 · 확산",
    5: "L5 · 최적화",
}


@dataclass(frozen=True)
class AreaScore:
    pts: int
    done: int  # 그 영역에서 답한 지표 수
    n: int  # 그 영역의 지표 수


@dataclass(frozen=True)
class Score:
    areas: tuple[AreaScore, ...]
    total: int
    answered: int
    level: int  # 늘 계산한다(응답 모양은 shown_level)


def round_half_up(x: float) -> int:
    """0.5 올림(시안 Math.round). 점수는 음수가 없다."""
    return math.floor(x + 0.5)


def _checked(answers: Mapping[str, Any]) -> Mapping[str, int]:
    known = set(ANSWER_KEYS)
    for key, value in answers.items():
        if key not in known:
            raise ValueError(f"답 키가 문항 밖이다: {key!r}")
        # bool 은 int 의 하위형이라 type 으로 가른다(True 가 1 로 통과하지 않게)
        if type(value) is not int or not LEVEL_RANGE[0] <= value <= LEVEL_RANGE[1]:
            raise ValueError(f"답 값은 정수 1..5 다: {key}={value!r}")
    return answers


def level_of(total: int) -> int:
    """총점 → 레벨 1..5(경계값은 위 레벨 — 160 은 L2)."""
    first, second, third, fourth = LEVEL_BOUNDS
    if total < first:
        return 1
    if total < second:
        return 2
    if total < third:
        return 3
    if total < fourth:
        return 4
    return 5


def score(answers: Mapping[str, Any]) -> Score:
    """시안 calc(D) 와 같은 값. answers 는 키 → 1..5, 없는 키는 미응답(0점)."""
    lv = _checked(answers)
    areas = []
    for ai, area in enumerate(AREAS):
        n = len(area.items)
        pts = 0.0
        done = 0
        for ii in range(n):
            level = lv.get(f"{ai}-{ii}")
            if level:
                done += 1
                pts += level / 5 * (AREA_POINTS / n)
        areas.append(AreaScore(pts=round_half_up(pts), done=done, n=n))
    total = sum(a.pts for a in areas)
    answered = sum(a.done for a in areas)
    return Score(
        areas=tuple(areas), total=total, answered=answered, level=level_of(total)
    )


def shown_level(result: Score) -> int | None:
    """응답에 싣는 레벨 — 17지표 전부 답했을 때만(시안 roundLevel :1848 · DEC-003 "완성된 진단")."""
    return result.level if result.answered == len(ANSWER_KEYS) else None


def missing_keys(answers: Mapping[str, Any]) -> list[str]:
    """아직 답하지 않은 지표 키(문항 순서)."""
    lv = _checked(answers)
    return [key for key in ANSWER_KEYS if key not in lv]


def is_complete(answers: Mapping[str, Any]) -> bool:
    return not missing_keys(answers)


def item_points(answers: Mapping[str, Any]) -> dict[str, int]:
    """답한 지표마다 점수 — round_half_up(l / 5 * (200 / n))(시안 리포트 지표 행 :1975)."""
    lv = _checked(answers)
    points: dict[str, int] = {}
    for area in AREAS:
        n = len(area.items)
        for item in area.items:
            level = lv.get(item.key)
            if level:
                points[item.key] = round_half_up(level / 5 * (AREA_POINTS / n))
    return points


def delta(cur: Score, prev: Score) -> tuple[int, list[int]]:
    """(총점 증감, 영역별 증감) — 이번 회차 − 비교 대상."""
    return cur.total - prev.total, [
        c.pts - p.pts for c, p in zip(cur.areas, prev.areas, strict=True)
    ]


def can_edit(status: str) -> bool:
    """draft·review 는 관리자가 고친다(자가 응답 검토 — 기획안 :832). final 은 못 고친다(DIA-007)."""
    return status in EDITABLE_STATUSES


def frozen_fields(mode: str) -> frozenset[str]:
    """그 회차에서 바꿀 수 없는 칸. 링크 회차는 제출일(diagnosed_on)이 잠긴다(결정 iv D2)."""
    return LINK_FROZEN if mode == "link" else frozenset()


def link_state(status: str, expires_on: dt.date, today: dt.date) -> str:
    """링크의 보이는 상태 open·expired·submitted·revoked. 만료는 open ∧ expires_on < today(당일은 유효)."""
    if status == "open" and expires_on < today:
        return "expired"
    return status


def public_areas() -> list[dict[str, Any]]:
    """공개 응답 화면의 문항 — 증빙 문구는 빼고(기획안 :835) 영역·지표·단계 설명만."""
    return [
        {
            "no": area.no,
            "name": area.name,
            "desc": area.desc,
            "items": [
                {
                    "key": item.key,
                    "name": item.name,
                    "question": item.question,
                    "levels": list(item.levels),
                }
                for item in area.items
            ],
        }
        for area in AREAS
    ]
