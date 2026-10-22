"""배정·풀에서 고르기·배정 후보 입출력 모양(T5 계획 결정 vi·vii·x·xx).

- 풀 과정 id 는 T4 글자 id 꼴이다(schemas.course.TextId — 1~POOL_ID_MAX 자, 소문자·숫자를 하이픈으로 잇는다). 모양 밖은 422.
- 풀에서 고르기는 1~POOL_PICK_MAX 개, 같은 id 를 두 번 주면 422 loc ["body", "pool_ids"]. day 가 null 이면 전부
  일차 미정이다. 응답 spilled 는 day 를 줬는데 그 섹션의 빈 교시가 모자라 일차 미정이 된 세션 수다.
- 섹션 일괄 배정은 승인 강사 한 명이다(해제는 세션 PATCH 의 instructor_id null). 응답 changed 는 새로 그 강사가 된
  세션 id, materials 는 붙인 기본 강의안 사본 수, skipped_missing 은 잠그려는 순간 사라져 건너뛴 원본 파일 수다.
- 배정 후보에는 이메일·전화가 없다. recommended 는 그 과정의 역량 강사 ∨ 고유 과정 소유자다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from classfit.schemas.course import DayNo, SessionOut, TextId

POOL_PICK_MAX = 20


class FromPoolIn(BaseModel):
    pool_ids: list[TextId] = Field(min_length=1, max_length=POOL_PICK_MAX)
    day: DayNo | None = None

    @field_validator("pool_ids")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("같은 과정을 두 번 고를 수 없습니다")
        return value


class FromPoolOut(BaseModel):
    items: list[SessionOut]
    spilled: int


class SectionAssignIn(BaseModel):
    instructor_id: int = Field(ge=1)


class SectionAssignOut(BaseModel):
    section_id: int
    instructor_id: int
    changed: list[int]
    materials: int
    skipped_missing: int


class CandidateOut(BaseModel):
    instructor_id: int
    name: str
    org: str | None
    recommended: bool
    assigned_sessions: int  # 이 강의에서 이미 맡은 세션 수
