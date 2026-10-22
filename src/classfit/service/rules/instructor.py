"""강사 규칙: 상태 전이표(기획안 A2) · 분야 태그 대분류 · 인증 코드 만료. 순수 함수, 시각은 인자로 받는다.

- 전이는 TRANSITIONS 한 곳이다. 표 밖(같은 상태 재요청 · 반려에서 바로 승인 · 대기에서 정지 …)은 None 이고
  service 가 409 로 바꾼다(T3 결정 vi). 표는 5전이다:
    pending →approve→ approved · pending →reject→ rejected · rejected →reapply→ pending
    approved →suspend→ suspended · suspended →unsuspend→ approved
- 대분류 6값은 시안 TAG_GROUPS 와 같다. 같은 글자가 models.tag 의 CHECK 와 0005 에 있다. 강사가 새로 만든 태그는 "기타".
- 인증 코드는 해시를 저장한 시각(issued_at)부터 minutes 분 동안 유효하다. 정확히 그 시각까지 유효, 넘으면 만료.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

InstructorStatus = Literal["pending", "approved", "rejected", "suspended"]
InstructorAction = Literal["approve", "reject", "reapply", "suspend", "unsuspend"]

INSTRUCTOR_STATUSES: tuple[InstructorStatus, ...] = (
    "pending",
    "approved",
    "rejected",
    "suspended",
)
INSTRUCTOR_ACTIONS: tuple[InstructorAction, ...] = (
    "approve",
    "reject",
    "reapply",
    "suspend",
    "unsuspend",
)
TRANSITIONS: dict[tuple[str, str], InstructorStatus] = {
    ("pending", "approve"): "approved",
    ("pending", "reject"): "rejected",
    ("rejected", "reapply"): "pending",
    ("approved", "suspend"): "suspended",
    ("suspended", "unsuspend"): "approved",
}

TAG_KINDS = ("field", "session", "survey_area")
TAG_GROUPS = (
    "AI 활용·업무자동화",
    "직무별 AX",
    "개발·데이터",
    "콘텐츠·디자인·영상",
    "경영·리더십",
    "기타",
)
DEFAULT_TAG_GROUP = "기타"


def next_status(status: str, action: str) -> InstructorStatus | None:
    """전이표의 다음 상태. 표 밖이면 None."""
    return TRANSITIONS.get((status, action))


def code_expired(issued_at: datetime, now: datetime, minutes: int) -> bool:
    """issued_at + minutes 를 넘었으면 참. 경계 시각 자체는 유효하다."""
    return now > issued_at + timedelta(minutes=minutes)
