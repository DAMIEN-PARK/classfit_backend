"""관리자 홈 응답 모양(T9b 계획 결정 xiii·xiv). 셈 여덟과 최근 처리 이력 10건이다.

카드(시안 관리자.html) ↔ 칸 — 셈마다 이동한 상세 목록과 같은 조건이다(요구정의서 COM-004, 조건은 crud/home_admin.py):
  1 승인 대기 강사 pending_instructors · 2 진행 중 강의 running_courses · 3 미배정 세션 unassigned_sessions ·
  4 미검토 강사 등록 unreviewed_registrations(고유 과정 + 커리큘럼) · 5 열린 설문 open_surveys ·
  6 진단 검토 대기 diagnoses_in_review(GET /v1/admin/diagnoses?status=review 와 같은 문장) · 7 교육 기록 미기록
  records_missing · 8 새 사진 new_photos · 9 최근 처리 이력 recent_audit((at, id) 내림차순 10건).
이력 항목은 여섯 칸이다 — detail(반려 사유 · 강의 제목 같은 자유 글)은 싣지 않는다. 화면은 target_type·target_id 로 상세에 간다.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class AdminHomeCountsOut(BaseModel):
    pending_instructors: int
    running_courses: int
    unassigned_sessions: int
    unreviewed_registrations: int
    open_surveys: int
    diagnoses_in_review: int
    records_missing: int
    new_photos: int


class AdminHomeAuditOut(BaseModel):
    id: int
    at: dt.datetime
    actor: str
    action: str
    target_type: str
    target_id: str | None


class AdminHomeOut(BaseModel):
    counts: AdminHomeCountsOut
    recent_audit: list[AdminHomeAuditOut]
