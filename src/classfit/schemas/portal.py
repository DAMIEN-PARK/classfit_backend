"""포털 응답 모양(T2b 계획 결정 vii). 개인 칸(이름·이메일·부서·learner_id·enrollment_id)이 없다(원칙 10, E-14).

- 섹션 → 세션 카드. state 는 open(열림 ∧ 첨부 ≥ 1) · preparing(준비 중).
- 잠긴 카드는 제목·일차·날짜·시각만 준다. description·keywords 는 null, attachments 는 빈 목록이다.
- start·end 는 일정표와 같은 계산의 "HH:MM" 이고, 못 정하면 null 이다.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel

from classfit.schemas.attachment import AttachmentOut

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


class PortalSectionOut(BaseModel):
    id: int
    title: str
    description: str | None
    sessions: list[PortalSessionOut]


class PortalOut(BaseModel):
    course: PortalCourseOut
    sections: list[PortalSectionOut]
