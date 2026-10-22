"""강사 규칙(T3): 상태 전이표 5쌍 · 태그 이름 정규화 · 인증 코드 만료 경계. DB 없음."""

from datetime import UTC, datetime, timedelta

from classfit.crud.tag import normalize_tag_name
from classfit.service.rules.instructor import (
    INSTRUCTOR_ACTIONS,
    INSTRUCTOR_STATUSES,
    TRANSITIONS,
    code_expired,
    next_status,
)


def test_instructor_status_transition_table_rows() -> None:
    expected = {
        ("pending", "approve"): "approved",
        ("pending", "reject"): "rejected",
        ("rejected", "reapply"): "pending",
        ("approved", "suspend"): "suspended",
        ("suspended", "unsuspend"): "approved",
    }
    assert TRANSITIONS == expected
    outside = []
    for status in INSTRUCTOR_STATUSES:
        for action in INSTRUCTOR_ACTIONS:
            got = next_status(status, action)
            assert got == expected.get((status, action)), (status, action, got)
            if got is None:
                outside.append((status, action))
    # 4상태 × 5동작 = 20 중 표 안 5, 밖 15(같은 상태 재요청 · 반려에서 바로 승인 · 대기에서 정지 …)
    assert len(outside) == 15
    assert next_status("rejected", "approve") is None
    assert next_status("pending", "suspend") is None
    assert next_status("approved", "approve") is None


def test_tag_name_normalization() -> None:
    assert normalize_tag_name("  프롬프트  ") == "프롬프트"
    assert normalize_tag_name("업무   자동화") == "업무 자동화"
    assert normalize_tag_name("\t생성형\n AI ") == "생성형 AI"
    assert normalize_tag_name("ChatGPT") == "ChatGPT"  # 대소문자는 그대로
    assert normalize_tag_name("   ") == ""


def test_email_code_expiry_boundary() -> None:
    issued = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    minutes = 10

    assert not code_expired(issued, issued, minutes)
    assert not code_expired(issued, issued + timedelta(minutes=minutes), minutes)
    assert code_expired(issued, issued + timedelta(minutes=minutes, seconds=1), minutes)
    assert not code_expired(issued, issued - timedelta(seconds=1), minutes)
