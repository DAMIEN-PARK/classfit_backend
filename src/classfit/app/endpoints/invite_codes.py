"""초대코드 끝점(관리자만, AdminCaller): 조회·수정·재발급·정지·재개·안내문(기획안 5-4, A3 코드 관리).

- 대상은 그 강의의 산 코드(replaced 아님) 하나다. state 는 오늘 기준 계산값(stopped·expired 포함)이다.
- 재개는 강의가 종료(계산값 ended)면 409 다. 정지·재발급은 종료 강의에서도 200 이다(T2a 계획 결정 iii).
- 상태를 바꾸는 요청(수정·재발급·정지·재개)은 audit_log 1행을 같은 트랜잭션에 쓴다(target course·id 글자, 결정 viii).
  멱등 호출(이미 그 상태 · 같은 값 PATCH)은 쓰지 않으므로 audit 도 없다. audit 에 코드 글자는 싣지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter

from classfit.app.deps import AdminCaller, DbSession, Today
from classfit.app.endpoints.courses import audit_course, code_out, course_or_404
from classfit.schemas.invite_code import InviteCodeOut, InviteCodePatchIn, NoticeOut
from classfit.service.courses import codes

router = APIRouter(prefix="/v1/admin", tags=["invite-codes"])

_404 = {404: {"description": "강의나 그 강의의 산 초대코드가 없음"}}


@router.get(
    "/courses/{course_id}/invite-code", response_model=InviteCodeOut, responses=_404
)
async def get_invite_code(
    course_id: int, session: DbSession, _: AdminCaller, today: Today
) -> InviteCodeOut:
    course = await course_or_404(session, course_id)
    return code_out(await codes.live_code(session, course_id), course, today)


@router.patch(
    "/courses/{course_id}/invite-code", response_model=InviteCodeOut, responses=_404
)
async def patch_invite_code(
    course_id: int,
    body: InviteCodePatchIn,
    session: DbSession,
    caller: AdminCaller,
    today: Today,
) -> InviteCodeOut:
    """만료일·정원을 바꾼다. 기간을 바꿔도 만료일은 따라가지 않으므로 여기서 고친다(결정 ii)."""
    course = await course_or_404(session, course_id)
    row, fields = await codes.update_invite_code(session, course_id, body.changes())
    if fields:
        await audit_course(
            session, caller, "invite_code.update", course_id, {"fields": fields}
        )
    return code_out(row, course, today)


@router.post(
    "/courses/{course_id}/invite-code:reissue",
    response_model=InviteCodeOut,
    responses=_404,
)
async def reissue_invite_code(
    course_id: int, session: DbSession, caller: AdminCaller, today: Today
) -> InviteCodeOut:
    """옛 코드는 바로 무효(replaced)가 되고 새 코드가 만료일·정원을 이어받는다."""
    course = await course_or_404(session, course_id)
    row = await codes.reissue_invite_code(session, course_id)
    await audit_course(
        session, caller, "invite_code.reissue", course_id, {"invite_code_id": row.id}
    )
    return code_out(row, course, today)


@router.post(
    "/courses/{course_id}/invite-code:pause",
    response_model=InviteCodeOut,
    responses=_404,
)
async def pause_invite_code(
    course_id: int, session: DbSession, caller: AdminCaller, today: Today
) -> InviteCodeOut:
    course = await course_or_404(session, course_id)
    row, changed = await codes.pause_invite_code(session, course_id)
    if changed:
        await audit_course(
            session, caller, "invite_code.pause", course_id, {"invite_code_id": row.id}
        )
    return code_out(row, course, today)


@router.post(
    "/courses/{course_id}/invite-code:resume",
    response_model=InviteCodeOut,
    responses={**_404, 409: {"description": "종료된 강의의 코드"}},
)
async def resume_invite_code(
    course_id: int, session: DbSession, caller: AdminCaller, today: Today
) -> InviteCodeOut:
    course = await course_or_404(session, course_id)
    row, changed = await codes.resume_invite_code(session, course.id, today=today)
    if changed:
        await audit_course(
            session, caller, "invite_code.resume", course_id, {"invite_code_id": row.id}
        )
    return code_out(row, course, today)


@router.get(
    "/courses/{course_id}/invite-code/notice",
    response_model=NoticeOut,
    responses=_404,
)
async def invite_code_notice(
    course_id: int, session: DbSession, _: AdminCaller
) -> NoticeOut:
    """고객사 담당자에게 보낼 안내문 글자: 강의명·기간·코드·만료일."""
    course = await course_or_404(session, course_id)
    row = await codes.live_code(session, course_id)
    text = "\n".join(
        (
            f"[{course.title}] 수강 안내",
            f"교육 기간: {course.start_on.isoformat()} ~ {course.end_on.isoformat()}",
            f"초대코드: {row.code}",
            f"코드 만료일: {row.expires_on.isoformat()}",
        )
    )
    return NoticeOut(text=text)
