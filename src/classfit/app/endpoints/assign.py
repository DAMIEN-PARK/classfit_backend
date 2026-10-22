"""관리자 배정 끝점(AdminCaller, T5 계획 결정 i·ii·vi·vii·x·xv·xvi·xx).

- POST /v1/admin/courses/{course_id}/sections/{section_id}/sessions:from-pool 본문 {pool_ids, day?}: 고른 순서대로
  세션을 만든다(제목 = 과정 제목 · 설명 = 목표 · pool_course_id · 미배정 · 닫힘). day 가 있으면 그 일차부터 그 섹션의
  빈 교시에 차례로 넣고, 일차가 모자라면 일차 미정이다(그 수가 spilled). 판정은 없는 섹션·남의 강의 섹션 404 →
  없는 과정 404 + missing → 비활성 과정 409 + inactive → 그 강의에 없는 일차 409 순이다. 201 {items, spilled}.
  기본 강의안은 여기서 붙지 않고 배정할 때 붙는다. audit 은 없다(일정 편집, T2a 결정 viii).
- POST /v1/admin/courses/{course_id}/sections/{section_id}:assign 본문 {instructor_id}: 그 섹션의 세션 전부를 한
  강사에게(이미 그 강사인 세션은 건너뛴다). 승인 강사만이다 — 아니면 409 + instructor_status, 없는 강사 404.
  200 {section_id, instructor_id, changed, materials, skipped_missing}. 새로 맡은 세션 중 풀 과정을 가리키고 첨부가
  0개인 세션에 그 강사의 기본 강의안 사본이 붙는다. 바뀐 세션이 있으면 audit session.assign 1행 + outbox
  session_assigned 1행이다(service.courses.assign).
- GET /v1/admin/courses/{course_id}/assignee-candidates?pool_id=: 승인 강사만, 추천(그 과정의 역량 강사 ∨ 고유 과정
  소유자) 먼저 · 이름 · id 순. 한 쪽 500, 커서 없음(next_cursor 항상 null). 없는 강의·과정 404 이고, 모양 밖 pool_id 는
  DB 를 치지 않고 같은 404 다. 비활성 과정이어도 목록은 준다(이미 있는 세션의 배정).
"""

from __future__ import annotations

from fastapi import APIRouter

from classfit.app.deps import AdminCaller, DbSession
from classfit.app.endpoints.pool import id_or_404
from classfit.crud.pool import LIST_LIMIT
from classfit.schemas.assign import (
    CandidateOut,
    FromPoolIn,
    FromPoolOut,
    SectionAssignIn,
    SectionAssignOut,
)
from classfit.schemas.course import SessionOut
from classfit.schemas.page import Page
from classfit.service.courses import assign, pool_sessions

router = APIRouter(prefix="/v1/admin", tags=["assign"])

_SECTION = "/courses/{course_id}/sections/{section_id}"


@router.post(
    _SECTION + "/sessions:from-pool",
    response_model=FromPoolOut,
    status_code=201,
    responses={
        404: {"description": "섹션이 없음(다른 강의의 섹션 포함) · 없는 과정(missing)"},
        409: {"description": "비활성 과정(inactive) · 그 강의에 없는 일차"},
    },
)
async def add_sessions_from_pool(
    course_id: int,
    section_id: int,
    body: FromPoolIn,
    session: DbSession,
    _: AdminCaller,
) -> FromPoolOut:
    result = await pool_sessions.add_from_pool(
        session,
        course_id=course_id,
        section_id=section_id,
        pool_ids=body.pool_ids,
        day=body.day,
    )
    return FromPoolOut(
        items=[SessionOut.model_validate(r) for r in result.rows],
        spilled=result.spilled,
    )


@router.post(
    _SECTION + ":assign",
    response_model=SectionAssignOut,
    responses={
        404: {"description": "섹션이 없음(다른 강의의 섹션 포함) · 강사가 없음"},
        409: {"description": "승인 상태가 아닌 강사(instructor_status)"},
    },
)
async def assign_whole_section(
    course_id: int,
    section_id: int,
    body: SectionAssignIn,
    session: DbSession,
    caller: AdminCaller,
) -> SectionAssignOut:
    result = await assign.assign_section(
        session,
        course_id=course_id,
        section_id=section_id,
        instructor_id=body.instructor_id,
        actor=f"admin:{caller.id}",
    )
    return SectionAssignOut(
        section_id=section_id,
        instructor_id=body.instructor_id,
        changed=list(result.changed),
        materials=result.materials,
        skipped_missing=result.skipped_missing,
    )


@router.get(
    "/courses/{course_id}/assignee-candidates",
    response_model=Page[CandidateOut],
    responses={404: {"description": "강의가 없음 · 과정이 없음"}},
)
async def list_assignee_candidates(
    course_id: int,
    session: DbSession,
    caller: AdminCaller,
    pool_id: str | None = None,
) -> Page[CandidateOut]:
    rows, has_more = await assign.candidates(
        session,
        caller,
        course_id=course_id,
        pool_id=None if pool_id is None else id_or_404(pool_id, "과정이 없습니다"),
        limit=LIST_LIMIT,
    )
    return Page[CandidateOut](
        items=[
            CandidateOut(
                instructor_id=r.instructor_id,
                name=r.name,
                org=r.org,
                recommended=r.recommended,
                assigned_sessions=r.assigned_sessions,
            )
            for r in rows
        ],
        next_cursor=None,
        has_more=has_more,
    )
