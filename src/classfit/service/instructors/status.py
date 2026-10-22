"""강사 상태 전이(기획안 A2 4행, T3 결정 vi). flush 까지만.

- 전이는 먼저 강사 행을 FOR UPDATE 로 잠근다(crud.instructor.lock_instructor). 동시 approve·reject 가 둘 다 표를
  통과해 audit 2행·메일 2통이 되지 않게, 로그인과 정지가 엇갈려 정지 뒤 산 세션이 남지 않게 한다(Design 5절 6).
- 표는 service.rules.instructor.TRANSITIONS 한 곳이다. 표 밖이면 Conflict(409, current_status 칸).
- 전이마다 audit 1행: actor 는 부른 쪽 표기(admin:<id> · instructor:<id>), action instructor.<동작>, target instructor·id.
  반려만 detail {reason} 이다(불변 스냅샷 — 재신청이 행의 사유를 비워도 메일 본문은 여기서 읽는다).
- 정지는 그 강사의 산 세션을 전부 폐기한다(옛 토큰 401, 결정 v). 매 요청 상태 조회는 없다.
- 승인·반려만 outbox 1행: kind instructor_approved·instructor_rejected, params {instructor_id, audit_id}, to 강사 이메일.
  본문 글자(이름·사유)는 params 에 넣지 않는다(models.outbox). scripts.outbox_preview 가 행에서 읽는다.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import auth as crud_auth
from classfit.crud import instructor as crud_instructor
from classfit.crud.audit import insert_audit
from classfit.crud.outbox import enqueue
from classfit.models import Instructor
from classfit.service.rules.instructor import InstructorAction, next_status

TARGET_TYPE = "instructor"
MAIL_KINDS: dict[str, str] = {
    "approve": "instructor_approved",
    "reject": "instructor_rejected",
}


async def apply_transition(
    session: AsyncSession,
    row: Instructor,
    *,
    action: InstructorAction,
    actor: str,
    reason: str | None = None,
) -> Instructor:
    """이미 잠근 행에 전이를 적용한다(transition·profile.reapply 가 잠근 뒤 부른다). 표 밖이면 Conflict."""
    target = next_status(row.status, action)
    if target is None:
        raise Conflict(
            f"지금 상태({row.status})에서는 할 수 없는 동작입니다",
            current_status=row.status,
        )
    if (action == "reject") != (reason is not None):
        raise ValueError("반려만 사유를 받고, 반려는 사유가 있어야 한다")
    await crud_instructor.set_status(session, row, target, reject_reason=reason)
    if action == "suspend":
        await crud_auth.revoke_principal_sessions(session, "instructor", row.id)
    audit = await insert_audit(
        session,
        actor=actor,
        action=f"instructor.{action}",
        target_type=TARGET_TYPE,
        target_id=str(row.id),
        detail={"reason": reason} if action == "reject" else None,
    )
    kind = MAIL_KINDS.get(action)
    if kind is not None:
        await enqueue(
            session,
            kind=kind,
            params={"instructor_id": row.id, "audit_id": audit.id},
            to=row.email,
        )
    return row


async def transition(
    session: AsyncSession,
    *,
    instructor_id: int,
    action: InstructorAction,
    actor: str,
    reason: str | None = None,
) -> Instructor:
    """관리자 전이(approve·reject·suspend·unsuspend). 강사가 없으면 NotFound(404), 표 밖이면 Conflict(409)."""
    row = await crud_instructor.lock_instructor(session, instructor_id)
    if row is None:
        raise NotFound("강사가 없습니다")
    return await apply_transition(
        session, row, action=action, actor=actor, reason=reason
    )
