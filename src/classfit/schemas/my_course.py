"""강사의 배정 강의 입출력 모양(T5 계획 결정 xii·xiii).

- 강의 목록 칸은 관리자 목록에서 개설 관리 칸(일정 기본값·소개·보관·수동 상태)을 뺀 꼴 + my_sessions(내가 맡은 세션 수)다.
- 상세는 그 강의의 모든 세션이다(남의 세션도 읽기 전용). 세션마다 강사 id·이름과 첨부 수(attachments)만 주고
  첨부 href 는 주지 않는다 — 강사의 세션 첨부 판정은 T6 몫이다. 이메일·전화는 없다.
- 내 세션 수정 본문은 description·keywords·is_open 셋뿐이다. 그 밖의 키(제목·일차·교시·분·시각·강사·섹션)는
  422 extra_forbidden(loc ["body", <키>]). keywords·is_open 의 null 은 422, description 은 null 로 비운다.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from classfit.schemas.course import CourseStatus, LongText, Word, _not_null, _Patch


class MyCourseOut(BaseModel):
    id: int
    title: str
    client_name: str
    course_type: str | None
    cohort: str | None
    method: str
    start_on: dt.date
    end_on: dt.date
    status: CourseStatus
    my_sessions: int


class MyCourseInfoOut(BaseModel):
    id: int
    title: str
    client_name: str
    course_type: str | None
    cohort: str | None
    method: str
    hours_per_person: int
    start_on: dt.date
    end_on: dt.date
    slot_min: int
    break_min: int
    intro: str | None
    notice: str | None
    status: CourseStatus


class MySessionOut(BaseModel):
    """세션 한 칸. date·start·end 는 일정표와 같은 계산이고 못 정하면 null 이다."""

    id: int
    section_id: int
    title: str
    description: str | None
    keywords: list[str]
    is_open: bool
    day_no: int | None
    slot: int | None
    minutes: int | None
    date: dt.date | None
    start: str | None
    end: str | None
    instructor_id: int | None
    instructor_name: str | None
    attachments: int  # 첨부 수(href 없음)


class MySectionOut(BaseModel):
    id: int
    title: str
    description: str | None
    sessions: list[MySessionOut]


class MyCourseDetailOut(BaseModel):
    course: MyCourseInfoOut
    sections: list[MySectionOut]


class MySessionPatchIn(_Patch):
    model_config = ConfigDict(extra="forbid")

    description: LongText | None = None
    keywords: list[Word] | None = Field(default=None, max_length=20)
    is_open: bool | None = None

    @model_validator(mode="after")
    def _shape(self) -> MySessionPatchIn:
        _not_null(self, "keywords", "is_open")
        return self
