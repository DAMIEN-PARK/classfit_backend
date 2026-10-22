"""관리자 수강생 명단 모양(관리자 전용). 이름·부서는 이 강의 등록의 값이고 이메일은 learner 의 값이다."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class EnrollmentOut(BaseModel):
    id: int
    name: str
    dept: str | None
    email: str
    enrolled_at: dt.datetime  # enrollment.created_at(등록일)
