"""강의 삭제(T2b 계획 결정 v·ix·xi, T2a 결정 vii). flush 까지만.

순서: 강의 행 잠금(lock_course) → enrollment 가 있으면 409 → 그 강의의 auth_session 행 → 첨부·파일 행 → 사진·파일 행(T7)
→ 설문 행 id 순 잠금(T8 — CASCADE 가 지우는 survey 행의 순서를 양식 삭제와 맞춘다) → course(CASCADE).
- 잠금이 맨 앞이라, 입장이 강의 행을 잠근 채 등록하는 사이 enrollment 0 을 믿고 지우는 일이 없다(23503 → 500 방지).
- 409 조건은 enrollment 만 센다. 수강생 없는 강의에 남은 세션 행(만료·폐기, probe 잔여)은 지운다.
  auth_session.course_id 는 NO ACTION 이라 남기면 23503 이고, 1차에는 그 행을 지울 API 가 없다.
- session_attachment.session_id · photo 의 course·session FK(T7)도 NO ACTION 이고 stored_file 은 다형 참조라 FK 가 없어,
  셋 다 먼저 지운다. 바이트는 gc 몫이다. 교육 기록(T7)은 세션 FK CASCADE 로 같이 지워진다.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.errors import Conflict, NotFound
from classfit.crud import attachment as crud_attachment
from classfit.crud import auth as crud_auth
from classfit.crud import course as crud_course
from classfit.crud import enrollment as crud_enrollment
from classfit.crud import photo as crud_photo
from classfit.crud import survey as crud_survey


async def remove_course(session: AsyncSession, course_id: int) -> None:
    """없으면 404, 수강생이 있으면 409."""
    if await crud_course.lock_course(session, course_id) is None:
        raise NotFound("강의가 없습니다")
    if await crud_enrollment.has_enrollments(session, course_id):
        raise Conflict("수강생이 있는 강의는 지울 수 없습니다")
    await crud_auth.delete_course_sessions(session, course_id)
    await crud_attachment.delete_attachments_under(session, course_id=course_id)
    await crud_photo.delete_photos_under(session, course_id=course_id)
    await crud_survey.lock_in_id_order(session, course_id=course_id)
    await crud_course.delete_course(session, course_id)
