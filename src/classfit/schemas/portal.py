"""포털 응답 모양(T2b 계획 결정 vii). 개인 칸(이름·이메일·부서·learner_id·enrollment_id)이 없다(원칙 10, E-14).

- 섹션 → 세션 카드. state 는 open(열림 ∧ 첨부 ≥ 1) · preparing(준비 중).
- 잠긴 카드는 제목·일차·날짜·시각만 준다. description·keywords 는 null, attachments 는 빈 목록이다.
- start·end 는 일정표와 같은 계산의 "HH:MM" 이고, 못 정하면 null 이다.
- 강사는 이름 칸 하나(instructor_name, 키 name 아님 — T2b 개인 키 시험, T5 결정 xiv). 열린 카드·준비 중 카드 둘 다,
  미배정이면 null. 강사 id·이메일·전화는 없다.
- survey 는 그 강의 현재 설문의 머리(T8 결정 xv — id · 계산 상태 · 열림일 · 닫힘일), 없으면 null 이다. 응답 여부는
  없다(주체를 읽지 않는다 — 미리 보기와 같은 JSON). 참여 완료는 수강생 설문 GET 의 responded 가 준다.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel

from classfit.schemas.attachment import AttachmentOut
from classfit.schemas.survey import SurveyStatus

CourseStatus = Literal["prep", "running", "ended"]


class PortalCourseOut(BaseModel):
    id: int
    title: str
    start_on: dt.date
    end_on: dt.date
    status: CourseStatus
    intro: str | None
    notice: str | None


class PortalSessionOut(BaseModel):
    id: int
    title: str
    day_no: int | None
    date: dt.date | None
    start: str | None
    end: str | None
    state: Literal["open", "preparing"]
    description: str | None = None
    keywords: list[str] | None = None
    attachments: list[AttachmentOut] = []
    instructor_name: str | None = None


class PortalSectionOut(BaseModel):
    id: int
    title: str
    description: str | None
    sessions: list[PortalSessionOut]


class PortalSurveyOut(BaseModel):
    id: int
    status: SurveyStatus
    open_on: dt.date
    close_on: dt.date


class PortalOut(BaseModel):
    course: PortalCourseOut
    sections: list[PortalSectionOut]
    survey: PortalSurveyOut | None
