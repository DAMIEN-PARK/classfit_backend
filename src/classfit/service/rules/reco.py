"""권장 교육 구성(reco) 초안과 개설 ③ 의 섹션·세션 제목(T9a 결정 vii·viii). 순수 함수 — DB 를 모른다.

- 모양은 시안 관리자.html:1949-1961 buildReco 의 키 그대로다: leader{target, hours, items} · common{hours, items, focus} ·
  tracks[{key, name, depts, courses, candidates_missing}] · hoursPer · difficulty · capstone · poc{method, items, next} ·
  next. 글자 상수는 시안 그대로다.
- 트랙은 회사 부서를 직무군으로 묶은 것이다(기획안 :844 "회사 부서 → 8직무군 매핑" · :1022). 직무군 표 DEPT_GROUPS 는
  시안 GROUPS(:1060-1069)의 key·name·kw 그대로 + T4 풀 과정 job_groups 태그다. group_of 는 표 순서대로 돌며 부서
  이름에 키워드가 부분 문자열로 든 첫 직무군을 고르고(대소문자 구분), 없으면 mgt 다(시안 groupOf :1070). 그래서
  "SW개발"·"기술영업" 은 eng, "비전검사" 는 qa 다(시안 순서 그대로).
- 트랙마다 대표 과정은 후보(candidates — 직무군 key → 과정 제목, service 가 T4 공개 AX 과정에서 읽어 넘긴다) 앞
  CANDIDATES_MAX 개다. 후보가 없으면 courses [] · candidates_missing True(관리자가 PATCH …/reco 로 채운다).
- 시작 난이도는 직군별 역량 평균의 최댓값 ≥ 3 이면 중 · 심화(시안 :1953). PoC 방식은 데이터 확보 지표(답 "1-0",
  없으면 2) 로 고른다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from classfit.service.rules.diagnosis import AREAS, COMPETENCIES, ROLES, Score

CANDIDATES_MAX = (
    3  # 트랙마다 대표 과정 수(기획안 :844 "3~5" 의 아래 끝, models.diagnosis 와 같다)
)
DEFAULT_GROUP_KEY = "mgt"
TRACK_DEFAULT_DEPT = "경영지원"  # 부서가 없는 회사의 트랙 하나(시안 :1954)
COMMON_SECTION = "공통교육"  # 개설 ③ 의 첫 섹션(시안 :1564)
CAPSTONE_SESSION = "캡스톤 교육 세션"  # 트랙 섹션 끝 세션(시안 :1565)
DIFFICULTY_HIGH = "중 · 심화"
DIFFICULTY_LOW = "하 · 기초"
DATA_ITEM_KEY = "1-0"  # 데이터 확보 및 수집 수준 — PoC 방식의 근거
TRACK_KEYS = frozenset({"key", "name", "depts", "courses", "candidates_missing"})
# 키 집합(schemas 가 같은 모양을 다시 선언한다). 값이 None 이면 잎 칸이다
RECO_SHAPE: dict[str, frozenset[str] | None] = {
    "leader": frozenset({"target", "hours", "items"}),
    "common": frozenset({"hours", "items", "focus"}),
    "tracks": TRACK_KEYS,
    "hoursPer": None,
    "difficulty": None,
    "capstone": None,
    "poc": frozenset({"method", "items", "next"}),
    "next": None,
}


@dataclass(frozen=True)
class DeptGroup:
    key: str
    name: str
    keywords: tuple[str, ...]  # 시안 kw
    job_groups: tuple[
        str, ...
    ]  # T4 pool_course.job_groups 태그(models.pool.JOB_GROUPS 의 글자)


DEPT_GROUPS: tuple[DeptGroup, ...] = (
    DeptGroup(
        "eng",
        "엔지니어링 (설계·제어·개발)",
        ("설계", "제어", "개발", "기술", "연구", "엔지니어", "SF", "전산"),
        ("연구개발·설계",),
    ),
    DeptGroup(
        "cs",
        "고객 접점 · 수주 (영업·CS)",
        ("영업", "CS", "고객", "수주", "기술영업"),
        ("영업·마케팅", "고객응대(CS)"),
    ),
    DeptGroup(
        "buy",
        "구매 · 협력사 관리",
        ("구매", "자재", "조달", "협력"),
        ("구매·자재·물류",),
    ),
    DeptGroup(
        "prod",
        "생산기술 · 제조",
        ("생산", "제조", "공정", "제작", "현장", "운영"),
        ("생산·제조",),
    ),
    DeptGroup(
        "qa", "품질보증 · 품질관리", ("품질", "QA", "QC", "검사"), ("품질·안전",)
    ),
    DeptGroup(
        "vis", "SW 개발 · 비전", ("비전", "SW", "소프트웨어"), ("IT·개발·데이터",)
    ),
    DeptGroup(
        "film", "기술영업 · 제조 (소재)", ("필름", "코팅", "소재"), ("생산·제조",)
    ),
    DeptGroup(
        "mgt",
        "경영지원 (인사·총무·회계)",
        ("경영", "인사", "총무", "회계", "관리", "지원", "기획"),
        ("경영·관리", "사무·행정", "기획·전략", "인사·총무·회계"),
    ),
)
_BY_KEY = {g.key: g for g in DEPT_GROUPS}

LEADER = {
    "target": "임원 · 팀장 · 핵심 리더 8~12명",
    "hours": "4시간 (반일)",
}
LEADER_FIRST = "AX 방향 이해와 타사 적용 방식"
LEADER_LOW = "AI로 바뀌는 업무의 모습 (사례 중심)"  # 레벨 ≤ 2
LEADER_HIGH = "우리 회사 적용 과제 정의"
LEADER_REST = ("우선순위 판단 기준 합의", "전직원 교육 목표와 결과물 합의")
COMMON_HOURS = "6시간"
COMMON_ITEMS = (
    "AI 보안과 보안기술 (KISA·OWASP 준용, 마스킹, 서약)",
    "AI 도구 이해 및 업무활용 (모델 비교·프롬프트 7필드)",
    "부서 소통 세션 (부서별 과제 후보 정리)",
)
HOURS_PER = "직무응용 10시간 (과정당 120분 × 5)"
POC_METHODS = (  # (데이터 확보 단계 하한, 방식) — 위에서부터 첫 일치
    (4, "분석형 (데이터 축적됨)"),
    (3, "규칙 기반 + LLM 해석"),
    (0, "LLM 해석형 (문서·문의 처리)"),
)
POC_EMPTY = "현장 활용 현황을 입력하면 후보 과제가 채워집니다"
POC_NEXT = "과제 정의서 → 데이터 실사 → 규칙·LLM 역할 분리 설계 → 시제품 → 사내 검증"
NEXT_STEPS = (
    "사전 컨설팅 결과 공유 미팅 (2주 이내)",
    "리더십 세션 일정·대상 확정",
    "파일럿 부서 1곳 선정과 교육 일정 협의",
)


def group_of(dept: str) -> DeptGroup:
    """부서 이름에 키워드가 든 첫 직무군(표 순서 · 부분 문자열 · 대소문자 구분), 없으면 mgt."""
    for group in DEPT_GROUPS:
        if any(k in dept for k in group.keywords):
            return group
    return _BY_KEY[DEFAULT_GROUP_KEY]


def tracks_for(
    depts: Sequence[str], candidates: Mapping[str, Sequence[str]]
) -> list[dict[str, Any]]:
    """부서를 직무군으로 묶은 트랙(처음 나온 순서). 부서가 없으면 「경영지원」 하나."""
    tracks: dict[str, dict[str, Any]] = {}
    for dept in depts or [TRACK_DEFAULT_DEPT]:
        group = group_of(dept)
        if group.key in tracks:
            tracks[group.key]["depts"].append(dept)
            continue
        courses = list(candidates.get(group.key, ()))[:CANDIDATES_MAX]
        tracks[group.key] = {
            "key": group.key,
            "name": group.name,
            "depts": [dept],
            "courses": courses,
            "candidates_missing": not courses,
        }
    return list(tracks.values())


def _role_averages(matrix: Mapping[str, Any]) -> list[float]:
    """직군마다 넣은 역량 값의 평균(넣은 것이 없으면 0 — 시안 roleAvg)."""
    averages = []
    for ri in range(len(ROLES)):
        values = [matrix.get(f"{ri}-{ci}") for ci in range(len(COMPETENCIES))]
        given = [v for v in values if v]
        averages.append(sum(given) / len(given) if given else 0)
    return averages


def _poc_items(field: Mapping[str, Any]) -> list[str]:
    items = []
    if field.get("work"):
        freq = field.get("wfreq") or "빈도 미입력"
        hours = field.get("whours") or "시간 미입력"
        items.append(f"{field['work']} 자동화 ({freq} · {hours})")
    for work in list(field.get("works") or [])[:2]:
        items.append(f"{work} 영역의 반복 문서·데이터 정리 보조")
    return items or [POC_EMPTY]


def build_reco(
    *,
    score: Score,
    answers: Mapping[str, Any],
    field: Mapping[str, Any],
    matrix: Mapping[str, Any],
    depts: Sequence[str],
    candidates: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """시안 buildReco 와 같은 모양의 초안. 트랙 과정은 candidates 에서(시안의 GROUPS.courses 대신)."""
    points = [a.pts for a in score.areas]
    lowest = points.index(min(points))
    data_level = answers.get(DATA_ITEM_KEY) or 2
    method = next(name for floor, name in POC_METHODS if data_level >= floor)
    difficulty = DIFFICULTY_HIGH if max(_role_averages(matrix)) >= 3 else DIFFICULTY_LOW
    return {
        "leader": {
            **LEADER,
            "items": [
                LEADER_FIRST,
                LEADER_LOW if score.level <= 2 else LEADER_HIGH,
                *LEADER_REST,
            ],
        },
        "common": {
            "hours": COMMON_HOURS,
            "items": list(COMMON_ITEMS),
            "focus": f"{AREAS[lowest].name} 보강",
        },
        "tracks": tracks_for(depts, candidates),
        "hoursPer": HOURS_PER,
        "difficulty": difficulty,
        "capstone": True,
        "poc": {"method": method, "items": _poc_items(field), "next": POC_NEXT},
        "next": list(NEXT_STEPS),
    }


def reco_sections(reco: Mapping[str, Any]) -> list[tuple[str, list[str]]]:
    """개설 ③ 의 (섹션 제목, 세션 제목들) — 「공통교육」 + 트랙마다(과정 + 캡스톤).

    트랙 섹션 이름은 트랙 이름의 " (" 앞이다(시안 :1565 — "고객 접점 · 수주 (영업·CS)" → "고객 접점 · 수주").
    세션 제목은 reco 글자 그대로다.
    """
    sections = [(COMMON_SECTION, list(reco["common"]["items"]))]
    for track in reco["tracks"]:
        titles = list(track["courses"])
        if reco["capstone"]:
            titles.append(CAPSTONE_SESSION)
        sections.append((track["name"].split(" (")[0], titles))
    return sections
