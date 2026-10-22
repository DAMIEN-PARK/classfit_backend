"""강사 화면 읽기 넷(T6 결정 xiii·xxi·xxii): 포털 미리 보기 · 초대코드 · 안내문 · 명단. 읽기만 한다.

- 넷 다 강의를 mine.course_for 로 먼저 판정한다(없으면 404 → 배정된 세션이 없는 강의 403).
- 포털 미리 보기는 T2b build_portal 을 그 강의 수강생 시점 주체(LearnerView)로 부른다 — 수강생 포털과 같은 질의·
  같은 카드 판정이라 "미리 보기 == 수강생 포털" 이 구성으로 서고, 강사 주체는 첨부 목록(crud.attachment._listed)에
  닿지 않는다(결정 xxii ②).
- 초대코드는 산 코드(없으면 404)와 등록 수, 안내문은 관리자 안내문과 같은 글자(codes.notice_text)다. 재발급·정지·
  만료·정원 바꾸기는 강사에게 없다.
- 명단은 최소 노출이다: crud.enrollment.roster_stmt(learner 를 잇지 않는다 — 이메일 없음, 결정 xxi) + 키셋 커서.
  깨진 커서만 InvalidCursor(ValueError)로 바꾼다(끝점이 422 loc ["query","cursor"]) — keyset_page 호출만 감싸
  결정 xxii 가드 같은 다른 ValueError 가 커서 422 로 가려지지 않게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.crud import enrollment as crud_enrollment
from classfit.crud.page import keyset_page
from classfit.crud.scope import Subject
from classfit.models import Course, Enrollment, InviteCode
from classfit.service.courses import codes, mine
from classfit.service.courses.portal import Portal, build_portal


class InvalidCursor(ValueError):
    """깨진 키셋 커서. 끝점은 이 예외만 422 loc ["query","cursor"] 로 바꾼다."""


@dataclass(frozen=True)
class LearnerView:
    """인증 주체가 아니라 build_portal 에 넘기는 범위 인자(crud.scope.Subject 모양). course_for 판정 뒤에만 만든다."""

    course_id: int
    type: str = "learner"
    id: int = 0


async def portal_preview(
    session: AsyncSession, subject: Subject, *, course_id: int
) -> Portal:
    await mine.course_for(session, subject, course_id)
    return await build_portal(
        session, LearnerView(course_id=course_id), course_id=course_id
    )


async def my_invite_code(
    session: AsyncSession, subject: Subject, *, course_id: int
) -> tuple[Course, InviteCode, int]:
    """(강의, 산 코드, 등록 수)."""
    course = await mine.course_for(session, subject, course_id)
    code = await codes.live_code(session, course_id)
    return course, code, await crud_enrollment.count_enrollments(session, course_id)


async def my_notice(session: AsyncSession, subject: Subject, *, course_id: int) -> str:
    course = await mine.course_for(session, subject, course_id)
    return codes.notice_text(course, await codes.live_code(session, course_id))


async def my_roster(
    session: AsyncSession,
    subject: Subject,
    *,
    course_id: int,
    cursor: str | None,
    limit: int,
) -> tuple[list[Enrollment], str | None, bool]:
    """(행, next_cursor, has_more). 행에서는 이름·부서·등록일(created_at)만 쓴다. 깨진 커서는 InvalidCursor."""
    await mine.course_for(session, subject, course_id)
    stmt = crud_enrollment.roster_stmt(subject, course_id)
    try:
        return await keyset_page(session, stmt, cursor, limit)
    except ValueError as exc:
        if cursor is None:  # 커서가 없으면 커서 오류가 아니다
            raise
        raise InvalidCursor("깨진 커서입니다") from exc
