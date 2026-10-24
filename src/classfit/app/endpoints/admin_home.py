"""관리자 홈(AdminCaller, T9b 계획 결정 xiii·xiv·xviii). 읽기만 한다 — audit 없음(T4 결정 ix 꼴).

- GET /v1/admin/home: 셈 여덟(승인 대기 강사 · 진행 중 강의 · 미배정 세션 · 미검토 강사 등록 · 열린 설문 · 진단 검토 대기 ·
  교육 기록 미기록 · 새 사진)과 최근 처리 이력 10건이다. 셈마다 이동한 상세 목록과 같은 조건이고(COM-004 — 조건표는
  crud/home_admin.py) 오늘은 Today(Asia/Seoul)다. 홈 service 호출당 문장 둘(셈 한 문장 + 이력 한 문장)이다.
- 이력 항목은 {id, at, actor, action, target_type, target_id} 여섯 칸이다(detail 없음). 진행 중 강의 표 · 곧 시작 ·
  진단 요약 · 사진 미리 보기는 각 상세 목록 끝점이 준다(화면 단위 조립은 셈과 이력까지 — intent :88).
"""

from __future__ import annotations

from fastapi import APIRouter

from classfit.app.deps import AdminCaller, DbSession, Today
from classfit.schemas.admin_home import AdminHomeOut
from classfit.service.home import admin as home_admin

router = APIRouter(prefix="/v1/admin", tags=["admin-home"])


@router.get("/home", response_model=AdminHomeOut)
async def admin_home(
    session: DbSession, caller: AdminCaller, today: Today
) -> AdminHomeOut:
    view = await home_admin.admin_home(session, caller, today=today)
    return AdminHomeOut.model_validate(view, from_attributes=True)
