"""service.pool 공용: 422 예외 · 강사 주체 · 내용 칸 정리.

- 422 는 DomainError 종류에 없다. PoolViolation(violations=[{loc, msg, type}])을 끝점이 422 problem+json 으로 바꾼다
  (NotEditable 은 관리자가 못 고치는 칸, GridViolation 은 차시표 격자 밖·중복·시각 순서, T4 결정 xv·xviii).
- 쓰기 함수는 subject 가 아니라 instructor_id 를 받는다. 소유 판정은 crud.scope.owned_by 한 곳이라 as_instructor 로
  강사 주체를 만들어 넘긴다(T4 결정 ix).
- 내용 칸은 받은 dict 를 그대로 쓰지 않고 clean_fields 로 정리한다: 모르는 키는 ValueError(부르는 쪽 버그),
  목록 칸의 None 은 빈 목록, 튜플은 목록이다(JSONB·ARRAY 값과 같은 모양이어야 같은 값 PATCH 가 "안 바뀜" 이다).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from classfit.crud.scope import Subject

LIST_FIELDS = frozenset({"job_groups", "theory", "practice", "features"})


@dataclass(frozen=True)
class _InstructorSubject:
    id: int
    type: str = "instructor"
    course_id: int | None = None


def as_instructor(instructor_id: int) -> Subject:
    return _InstructorSubject(instructor_id)


def instructor_actor(instructor_id: int) -> str:
    """audit 주체 표기(models.audit)."""
    return f"instructor:{instructor_id}"


class PoolViolation(ValueError):
    """끝점이 422 problem+json 으로 바꾼다. violations 는 [{loc, msg, type}](app/errors.py 의 422 모양)."""

    def __init__(self, detail: str, violations: list[dict[str, Any]]) -> None:
        super().__init__(detail)
        self.detail = detail
        self.violations = violations


class NotEditable(PoolViolation):
    """이 행에서는 고칠 수 없는 칸(관리자의 고유 과정 내용 · AX 의 reviewed, T4 결정 xviii)."""


class GridViolation(PoolViolation):
    """차시표가 격자 밖·중복이거나, 수정이 기존 차시를 격자 밖으로 민다(T4 결정 xv)."""


def violation(loc: Iterable[Any], msg: str, type_: str) -> dict[str, Any]:
    return {"loc": list(loc), "msg": msg, "type": type_}


def not_editable(keys: Iterable[str], msg: str) -> NotEditable:
    return NotEditable(
        "이 항목에서는 고칠 수 없는 칸입니다",
        [violation(("body", k), msg, "not_editable") for k in sorted(keys)],
    )


def clean_fields(fields: Mapping[str, Any], allowed: Iterable[str]) -> dict[str, Any]:
    """allowed 밖 키는 ValueError. 목록 칸의 None → [], 튜플 → 목록, 진행표 줄은 목록의 목록."""
    allowed = frozenset(allowed)
    if unknown := set(fields) - allowed:
        raise ValueError(f"받지 않는 칸: {sorted(unknown)}")
    out: dict[str, Any] = {}
    for name, value in fields.items():
        if name == "schedule":
            value = [] if value is None else [list(row) for row in value]
        elif name in LIST_FIELDS:
            value = [] if value is None else list(value)
        out[name] = value
    return out
