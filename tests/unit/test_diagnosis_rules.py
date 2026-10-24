"""진단 규칙(service/rules/diagnosis.py · reco.py) ↔ 시안 golden(tests/fixtures/golden.json 의 score). DB 없음.

golden score 는 scripts/golden/extract.mjs 가 시안 calc 를 합성 사례로 돌린 값이다(T9a 결정 xv). 시안에서 다시 뽑아
대조하는 일은 scripts/golden/check.sh(pre-push)가 한다. 문항 글자는 golden 에 없다 — 구조·순서만 여기서 잰다.
"""

import json
import re
import typing
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import StringConstraints

from classfit.models import diagnosis as models_diagnosis
from classfit.models.pool import JOB_GROUPS
from classfit.schemas import course as schemas_course
from classfit.schemas import diagnosis as schemas_diagnosis
from classfit.service.rules import reco
from classfit.service.rules.diagnosis import (
    ANSWER_KEYS,
    AREA_SIZES,
    AREAS,
    can_edit,
    delta,
    expiry_window,
    frozen_fields,
    is_complete,
    item_points,
    level_of,
    link_state,
    missing_keys,
    public_areas,
    round_half_up,
    score,
    shown_level,
)
from classfit.service.rules.diagnosis_items import AREAS_12
from classfit.service.rules.diagnosis_items_34 import AREAS_34
from tests.fixtures.diagnosis import (
    ANSWERS_9,
    ANSWERS_ALL_1,
    ANSWERS_ALL_5,
    ANSWERS_MIXED,
    DEPTS_20,
    FIELD_SAMPLE,
    MATRIX_SAMPLE,
    RECO_SAMPLE,
)
from tests.fixtures.enter import json_keys

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
# 결정 viii 표 — (key, 시안 이름, 시안 kw, T4 job_groups 태그)
GROUP_TABLE = [
    (
        "eng",
        "엔지니어링 (설계·제어·개발)",
        ("설계", "제어", "개발", "기술", "연구", "엔지니어", "SF", "전산"),
        ("연구개발·설계",),
    ),
    (
        "cs",
        "고객 접점 · 수주 (영업·CS)",
        ("영업", "CS", "고객", "수주", "기술영업"),
        ("영업·마케팅", "고객응대(CS)"),
    ),
    (
        "buy",
        "구매 · 협력사 관리",
        ("구매", "자재", "조달", "협력"),
        ("구매·자재·물류",),
    ),
    (
        "prod",
        "생산기술 · 제조",
        ("생산", "제조", "공정", "제작", "현장", "운영"),
        ("생산·제조",),
    ),
    ("qa", "품질보증 · 품질관리", ("품질", "QA", "QC", "검사"), ("품질·안전",)),
    ("vis", "SW 개발 · 비전", ("비전", "SW", "소프트웨어"), ("IT·개발·데이터",)),
    ("film", "기술영업 · 제조 (소재)", ("필름", "코팅", "소재"), ("생산·제조",)),
    (
        "mgt",
        "경영지원 (인사·총무·회계)",
        ("경영", "인사", "총무", "회계", "관리", "지원", "기획"),
        ("경영·관리", "사무·행정", "기획·전략", "인사·총무·회계"),
    ),
]


def _out(lv: dict[str, int]) -> dict[str, object]:
    s = score(lv)
    return {
        "areas": [{"pts": a.pts, "done": a.done, "n": a.n} for a in s.areas],
        "total": s.total,
        "answered": s.answered,
        "level": s.level,
    }


def test_golden_score_calc() -> None:
    cases = GOLDEN["score"]
    assert len(cases) >= 7, "golden score 사례가 7개보다 적다"
    for case in cases:
        assert _out(case["in"]["lv"]) == case["out"], case["id"]
    # 시험 상수가 golden 사례와 같은 답이다(계약·통합 시험이 이 상수를 쓴다)
    by_id = {c["id"]: c for c in cases}
    assert by_id["dg-all-1"]["in"]["lv"] == ANSWERS_ALL_1
    assert by_id["dg-all-5"]["in"]["lv"] == ANSWERS_ALL_5
    assert by_id["dg-mixed-450-l3"]["in"]["lv"] == ANSWERS_MIXED
    assert by_id["dg-partial-9"]["in"]["lv"] == ANSWERS_9


def test_golden_score_levels() -> None:
    for case in GOLDEN["score"]:
        out = case["out"]
        assert level_of(out["total"]) == out["level"], case["id"]
        expected = out["level"] if out["answered"] == len(ANSWER_KEYS) else None
        assert shown_level(score(case["in"]["lv"])) == expected, case["id"]
    by_id = {c["id"]: c["out"] for c in GOLDEN["score"]}
    # DEC-003: 전부 1 이면 160 → L2(L1 은 나오지 않는다 — 산식을 바꾸지 않는다)
    assert by_id["dg-all-1"]["total"] == 160 and by_id["dg-all-1"]["level"] == 2
    assert by_id["dg-none"]["level"] == 1 and shown_level(score({})) is None
    edges = {0: 1, 159: 1, 160: 2, 319: 2, 320: 3, 479: 3, 480: 4, 639: 4, 640: 5}
    for total, level in (edges | {800: 5}).items():
        assert level_of(total) == level, total


def test_golden_score_items_shape() -> None:
    assert len(AREAS) == 4
    sizes = tuple(len(a.items) for a in AREAS)
    assert sizes == AREA_SIZES == models_diagnosis.AREA_SIZES == (5, 4, 4, 4)
    for case in GOLDEN["score"]:
        assert tuple(a["n"] for a in case["out"]["areas"]) == sizes, case["id"]
    keys = [item.key for area in AREAS for item in area.items]
    expected = [f"{a}-{i}" for a, n in enumerate((5, 4, 4, 4)) for i in range(n)]
    assert keys == expected == list(ANSWER_KEYS) == list(models_diagnosis.ANSWER_KEYS)
    assert len(keys) == 17
    for area in AREAS:
        for item in area.items:
            assert len(item.levels) == 5 and all(item.levels), item.key
            assert len(item.evidence) == 2 and all(item.evidence), item.key
            assert item.name and item.question, item.key
    # 두 데이터 파일의 영역 순서
    assert [a.no for a in AREAS_12] == ["01", "02"]
    assert [a.no for a in AREAS_34] == ["03", "04"]
    assert AREAS == (*AREAS_12, *AREAS_34)
    # 공개 화면 모양에는 증빙 문구가 없다(기획안 :835)
    shown = public_areas()
    assert "evidence" not in json_keys(shown)
    assert [len(a["items"]) for a in shown] == list(sizes)
    assert set(shown[0]) == {"no", "name", "desc", "items"}
    assert set(shown[0]["items"][0]) == {"key", "name", "question", "levels"}


def test_diagnosis_rules_round_half_up() -> None:
    assert round_half_up(2.5) == 3
    assert round_half_up(3.5) == 4
    assert round_half_up(2.4999) == 2
    assert round_half_up(0.5) == 1
    # 기록: Python round() 는 짝수 반올림이라 2.5 → 2 다(그래서 쓰지 않는다). 실입력 영역 점수는 .5 가 나오지 않는다
    assert round(2.5) == 2


def test_diagnosis_rules_missing_and_edit() -> None:
    assert missing_keys({}) == list(ANSWER_KEYS)
    assert len(missing_keys(ANSWERS_9)) == 8
    assert missing_keys(ANSWERS_MIXED) == [] and is_complete(ANSWERS_MIXED)
    assert not is_complete(ANSWERS_9)
    for bad in ({"4-0": 1}, {"0-5": 1}, {"0-0": 6}, {"0-0": 0}, {"0-0": True}):
        with pytest.raises(ValueError):
            missing_keys(bad)
        with pytest.raises(ValueError):
            score(bad)
    assert can_edit("draft") and can_edit("review") and not can_edit("final")
    assert frozen_fields("link") == {"diagnosed_on"}
    assert frozen_fields("visit") == frozenset()
    day = date(2026, 11, 3)
    assert link_state("open", day, day) == "open"  # 만료일 당일은 유효
    assert link_state("open", day, day + timedelta(days=1)) == "expired"
    assert link_state("revoked", day, day + timedelta(days=9)) == "revoked"
    assert link_state("submitted", day, day + timedelta(days=9)) == "submitted"
    # 만료일 범위 — 날짜 끝(9999-12-31) 근처는 OverflowError 대신 그 날로 멈춘다
    window = {"default_days": 14, "max_days": 365}
    assert expiry_window(day, **window) == (
        day + timedelta(days=14),
        day + timedelta(days=365),
    )
    end = date.max
    assert expiry_window(end - timedelta(days=20), **window) == (
        end - timedelta(days=6),
        end,
    )
    assert expiry_window(end, **window) == (end, end)
    total, areas = delta(score(ANSWERS_ALL_5), score(ANSWERS_ALL_1))
    assert total == 640 and areas == [160, 160, 160, 160]
    total, areas = delta(score(ANSWERS_9), score(ANSWERS_MIXED))
    assert total == 220 - 450 and areas == [0, 0, -110, -120]
    points = item_points(ANSWERS_ALL_5)
    assert set(points) == set(ANSWER_KEYS)
    assert points["0-0"] == 40 and points["1-0"] == 50 and points["3-3"] == 50
    assert item_points({"0-0": 3, "1-1": 1}) == {"0-0": 24, "1-1": 10}


def _strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """초안 안의 모든 글자 (경로, 값)."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, inner in value.items():
            yield from _strings(inner, f"{path}.{key}")
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            yield from _strings(inner, f"{path}[{i}]")


def _reco(
    answers: dict[str, int],
    *,
    matrix: dict[str, int] | None = None,
    field: dict[str, object] | None = None,
    depts: list[str] | None = None,
    candidates: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    return reco.build_reco(
        score=score(answers),
        answers=answers,
        field=field or {},
        matrix=matrix or {},
        depts=depts or [],
        candidates=candidates or {},
    )


def test_diagnosis_rules_build_reco() -> None:
    # focus = 최저 영역 이름(첫 최솟값)
    low_area_2 = {**ANSWERS_ALL_5, **{k: 1 for k in ANSWER_KEYS if k.startswith("2-")}}
    assert _reco(low_area_2)["common"]["focus"] == "조직문화 및 인력 역량 보강"
    assert _reco(ANSWERS_ALL_1)["common"]["focus"] == "AI 전환전략 보강"
    # difficulty = 직군 평균의 최댓값 ≥ 3(전체 평균이 아니다)
    values = list(MATRIX_SAMPLE.values())
    assert sum(values) / len(values) < 3
    assert _reco(ANSWERS_ALL_1, matrix=MATRIX_SAMPLE)["difficulty"] == "중 · 심화"
    flat = dict.fromkeys(MATRIX_SAMPLE, 2)
    assert _reco(ANSWERS_ALL_1, matrix=flat)["difficulty"] == "하 · 기초"
    assert _reco(ANSWERS_ALL_1)["difficulty"] == "하 · 기초"  # 역량 없음 → 평균 0
    # poc.method — 데이터 확보 지표 "1-0"(없으면 2)
    methods = {
        lv: _reco({**ANSWERS_ALL_1, "1-0": lv})["poc"]["method"] for lv in (1, 3, 4)
    }
    assert methods == {
        1: "LLM 해석형 (문서·문의 처리)",
        3: "규칙 기반 + LLM 해석",
        4: "분석형 (데이터 축적됨)",
    }
    assert _reco({})["poc"]["method"] == "LLM 해석형 (문서·문의 처리)"
    assert _reco(ANSWERS_ALL_1, field=FIELD_SAMPLE)["poc"]["items"] == [
        "기술문의 응대 자동화 (매일 · 40시간)",
        "문서·매뉴얼 검색 영역의 반복 문서·데이터 정리 보조",
        "보고서·품의서 작성 영역의 반복 문서·데이터 정리 보조",
    ]
    assert _reco(ANSWERS_ALL_1)["poc"]["items"] == [reco.POC_EMPTY]
    # 리더 과정 둘째 줄은 레벨 ≤ 2 면 사례 중심
    assert _reco(ANSWERS_ALL_1)["leader"]["items"][1] == reco.LEADER_LOW
    assert _reco(ANSWERS_ALL_5)["leader"]["items"][1] == reco.LEADER_HIGH

    # 직무군 표 = 결정 viii 표(시안 GROUPS key·name·kw + T4 태그)
    got = [(g.key, g.name, g.keywords, g.job_groups) for g in reco.DEPT_GROUPS]
    assert got == GROUP_TABLE
    assert tuple(g.key for g in reco.DEPT_GROUPS) == models_diagnosis.GROUP_KEYS
    assert all(set(g.job_groups) <= set(JOB_GROUPS) for g in reco.DEPT_GROUPS)
    assert reco.CANDIDATES_MAX == models_diagnosis.CANDIDATES_MAX == 3
    # group_of — 첫 일치 · 부분 문자열 · 대소문자 구분(15건)
    mapping = {
        "설계팀": "eng",
        "영업1팀": "cs",
        "해외CS": "cs",
        "구매": "buy",
        "생산2공장": "prod",
        "품질보증": "qa",
        "비전": "vis",
        "소프트웨어": "vis",
        "코팅": "film",
        "총무": "mgt",
        "알 수 없음": "mgt",  # 기본
        "SW개발": "eng",  # eng 의 '개발' 이 vis 보다 먼저
        "기술영업": "eng",  # cs 의 '기술영업' 이 eng 의 '기술' 에 가려진다(시안 quirk)
        "비전검사": "qa",  # qa 가 vis 보다 앞
        "cs팀": "mgt",  # 'CS' 와 대소문자가 다르다
    }
    assert {d: reco.group_of(d).key for d in mapping} == mapping

    # 트랙 — 직무군으로 묶고 처음 나온 순서, 후보 앞 3개
    candidates = {"cs": ["과정 1", "과정 2", "과정 3", "과정 4"], "prod": []}
    tracks = reco.tracks_for(["영업", "생산", "영업2"], candidates)
    assert [(t["key"], t["depts"]) for t in tracks] == [
        ("cs", ["영업", "영업2"]),
        ("prod", ["생산"]),
    ]
    assert all(set(t) == reco.TRACK_KEYS for t in tracks)
    assert tracks[0]["courses"] == ["과정 1", "과정 2", "과정 3"]
    assert tracks[0]["candidates_missing"] is False
    assert tracks[1]["courses"] == [] and tracks[1]["candidates_missing"] is True
    (only,) = reco.tracks_for([], {})
    assert (only["key"], only["depts"], only["name"]) == (
        "mgt",
        ["경영지원"],
        "경영지원 (인사·총무·회계)",
    )
    twenty = reco.tracks_for(DEPTS_20, {})
    assert [t["key"] for t in twenty] == list(models_diagnosis.GROUP_KEYS)
    assert sorted(d for t in twenty for d in t["depts"]) == sorted(DEPTS_20)

    # 초안 모양 == RECO_SHAPE
    built = _reco(ANSWERS_MIXED, depts=["영업", "생산"], candidates=candidates)
    assert set(built) == set(reco.RECO_SHAPE)
    for key, inner in reco.RECO_SHAPE.items():
        if key == "tracks":
            assert all(set(t) == inner for t in built["tracks"])
        elif inner is not None:
            assert set(built[key]) == inner, key
    assert set(RECO_SAMPLE) == set(reco.RECO_SHAPE)
    assert built["capstone"] is True

    # 개설 ③ 섹션·세션 — 트랙 섹션 이름은 " (" 앞, 세션은 과정 + 캡스톤
    assert reco.reco_sections(RECO_SAMPLE) == [
        ("공통교육", ["AI 보안 기초", "AI 도구 업무활용", "부서 소통 세션"]),
        (
            "고객 접점 · 수주",
            ["견적 자료 구조화", "CS 사례 매뉴얼", "캡스톤 교육 세션"],
        ),
        ("생산기술 · 제조", ["작업표준서 초안", "예방보전 점검표", "캡스톤 교육 세션"]),
    ]
    no_capstone = {**RECO_SAMPLE, "capstone": False}
    assert [len(t) for _, t in reco.reco_sections(no_capstone)] == [3, 2, 2]

    # 초안 글자 한도(리뷰 N4) — 초안을 그대로 PATCH …/reco 로 돌려보내도 RecoIn 한도 안이다:
    # 공통 과정·트랙 과정·트랙 이름(섹션·세션 제목)은 비지 않고 200 자까지, 그 밖 글자는 500 자까지
    assert (reco.RECO_TEXT_MAX, reco.RECO_LINE_MAX) == (500, 200)
    assert reco.clip("가" * 500, 500) == "가" * 500
    assert reco.clip("가" * 501, 500) == "가" * 499 + "…"
    assert reco.clip("  앞뒤 공백  ", 500) == "앞뒤 공백"
    # 자른 끝의 공백은 뗀다
    assert reco.clip("가" * 198 + "  나다", 200) == "가" * 198 + "…"
    long_field = {
        "work": "업" * 200,
        "wfreq": "빈" * 200,
        "whours": "시" * 200,
        "works": ["영" * 50] * 20,
    }  # 현장 활용 칸마다 스키마 상한(글자 200 · 항목 50 · 목록 20)
    # 이어 붙이면 정확히 500
    exact = {"work": "업" * 484, "wfreq": "매일", "whours": "40시간"}
    over = {**exact, "work": "업" * 485}  # 501
    long_titles = {
        "cs": ["가" * 200, "나" * 201, "   ", " 앞뒤 공백 과정 "],
        "prod": ["다" * 500],
    }
    for field, candidates in (
        (long_field, long_titles),
        (exact, {}),
        (over, {}),
    ):
        built = _reco(
            ANSWERS_MIXED,
            field=field,
            depts=DEPTS_20,
            candidates=candidates,
            matrix=MATRIX_SAMPLE,
        )
        line_paths = {"common.items", "tracks.courses", "tracks.name"}
        for path, text in _strings(built):
            # ".tracks[0].courses[1]" → "tracks.courses"
            bare = re.sub(r"\[\d+\]", "", path).lstrip(".")
            limit = reco.RECO_LINE_MAX if bare in line_paths else reco.RECO_TEXT_MAX
            assert len(text) <= limit, (path, len(text))
            if bare in line_paths:
                assert text.strip() == text and text, path
        assert len(built["poc"]["items"]) <= 3
    poc = _reco(ANSWERS_MIXED, field=long_field)["poc"]["items"]
    assert len(poc[0]) == 500 and poc[0].endswith("…")
    assert poc[1:] == ["영" * 50 + " 영역의 반복 문서·데이터 정리 보조"] * 2
    assert _reco(ANSWERS_MIXED, field=exact)["poc"]["items"] == [
        "업" * 484 + " 자동화 (매일 · 40시간)"
    ]
    assert _reco(ANSWERS_MIXED, field=over)["poc"]["items"][0].endswith("…")
    tracks = {
        t["key"]: t
        for t in _reco(ANSWERS_MIXED, depts=["영업", "생산"], candidates=long_titles)[
            "tracks"
        ]
    }
    # 200 자는 그대로 · 201 자는 잘림 · 빈 글자는 빠지고 다음 후보가 들어온다 · 앞뒤 공백은 뗀다
    assert tracks["cs"]["courses"] == ["가" * 200, "나" * 199 + "…", "앞뒤 공백 과정"]
    assert tracks["prod"]["courses"] == ["다" * 199 + "…"]
    assert all(t["candidates_missing"] is False for t in tracks.values())
    blank = reco.tracks_for(["영업"], {"cs": ["  ", ""]})
    assert blank[0]["courses"] == [] and blank[0]["candidates_missing"] is True
    common = _reco(ANSWERS_MIXED)["common"]["items"]
    assert common and all(0 < len(t) <= reco.RECO_LINE_MAX for t in common)


def _max_length(alias: Any) -> int | None:
    """Annotated 별칭의 StringConstraints.max_length."""
    (found,) = [
        m.max_length
        for m in typing.get_args(alias)[1:]
        if isinstance(m, StringConstraints)
    ]
    return found


def test_diagnosis_rules_reco_limits_match_schemas() -> None:
    # rules 는 schemas 를 부를 수 없어(test_import_rules 의 ALLOWED) 같은 수가 두 벌이다 — 여기서 맞춘다(T11 결정 xi)
    assert reco.RECO_TEXT_MAX == schemas_diagnosis.RECO_TEXT_MAX
    assert reco.RECO_TEXT_MAX == _max_length(schemas_diagnosis.RecoText)
    assert reco.RECO_LINE_MAX == _max_length(schemas_course.Line)
