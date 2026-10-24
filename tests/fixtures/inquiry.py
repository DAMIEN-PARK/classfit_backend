"""T9b 시험 도우미: 문의 본문 · 응답 키 집합 · 설정 · outbox 읽기 · 행 시각 밀기 · 관리자 홈 픽스처(worker-b 계약 시험도 쓴다).

- 이 파일은 T9b 의 service·schemas·app 을 import 하지 않는다(작업 순서 4 — 그 파일이 아직 없다). 문의 접수는 시험이 직접
  부르거나(service) HTTP 로 보낸다(post_inquiry). T1~T9a 픽스처·crud 는 쓴다.
- 이메일은 example.com, 회사는 A사·B사, 담당자는 홍길동, 전화는 010-0000-0000 이다. 담당자 이름은 확인 메일 고정 문구의
  낱말과 겹치지 않는다("제출한 값이 본문에 없음" 단언이 헛돌지 않게 — verifier 델타 NB2).
- age_inquiry: 시험은 바깥 트랜잭션 하나라 now() 가 고정이다. 1분 창 안·밖과 하루 밖은 행의 created_at 을 밀어 만든다.
- home_fixtures: 관리자 홈 셈 여덟의 양성·음성 행을 만들고 주체별 기대값을 돌려준다(T9b 결정 xiv·xv·xvi·xvii). today 는
  평일이어야 한다(강의 A·B 는 today 에 시작해 평일 2일이다). today + LATER_DAYS 에는 A·B 가 끝나고 준비 강의는 그대로다.
  설문은 부작용 없는 crud.survey.insert_survey, 진단은 T9a make_company + insert_round(crud 전용), 사진은 crud.photo
  (file_id 없음 — 셈은 seen_at 만 본다), 세션 배정은 crud.schedule.insert_session 의 instructor_id 칸이다(audit·outbox 없음).
  audit 은 at 을 명시한 12행(서로 다른 시각 10 + 같은 시각 둘)이다 — 트랜잭션 안 now() 가 고정이라 기본값으로는 순서가 안
  갈린다. 시각은 now() 뒤라 다른 픽스처가 남긴 audit 보다 늘 위다.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from classfit.core.config import Settings
from classfit.crud import course as crud_course
from classfit.crud import photo as crud_photo
from classfit.crud import record as crud_record
from classfit.crud import schedule as crud_schedule
from classfit.crud import survey as crud_survey
from classfit.models import AuditLog, Course, MailOutbox
from classfit.service.rules.inquiry import InquiryFields
from tests.fixtures.assign import approved, course_with_section
from tests.fixtures.diagnosis import insert_round, make_company
from tests.fixtures.instructors import make_instructor
from tests.fixtures.pool import make_curriculum, make_pool_course, set_flags

PATH = "/v1/inquiries"
NOTIFY_TO = "ops@example.com"
INQUIRY_BODY: dict[str, Any] = {
    "company_name": "A사",
    "contact_name": "홍길동",
    "email": "Contact.A@example.com",  # 대소문자 섞음 — 정규화 단언용
    "phone": "010-0000-0000",
    "dept_title": "경영지원팀 과장",
    "company_size": "30_99",
    "message": "교육 문의 본문입니다.\n대상 20명",
    "privacy_agreed": True,
}
NORMALIZED_EMAIL = "contact.a@example.com"

# 응답 키 집합 — 계약 시험이 == 로 잰다(T9b 결정 i·xiii·xxvii)
RECEIPT_KEYS = frozenset({"receipt_no", "received_at"})
RECEIPT_RE = r"^[A-HJ-NP-Z2-9]{10}$"
HOME_KEYS = frozenset({"counts", "recent_audit"})
COUNT_KEYS = (
    "pending_instructors",
    "running_courses",
    "unassigned_sessions",
    "unreviewed_registrations",
    "open_surveys",
    "diagnoses_in_review",
    "records_missing",
    "new_photos",
)
AUDIT_ITEM_KEYS = frozenset({"id", "at", "actor", "action", "target_type", "target_id"})
DIAG_LIST_ITEM_KEYS = frozenset(
    {
        "id",
        "company_id",
        "company_name",
        "round_no",
        "phase",
        "mode",
        "status",
        "diagnosed_on",
        "respondent_name",
        "submitted_at",
        "total",
        "level",
    }
)
ZERO_COUNTS: dict[str, int] = dict.fromkeys(COUNT_KEYS, 0)

HOME_TODAY = dt.date(2026, 11, 3)  # 화요일
LATER_DAYS = 17  # today + 17일: A·B 종료 · 설문 닫힘(close_on = today + 14) · 준비 강의(today + 30)는 그대로
AUDIT_DISTINCT = 10
AUDIT_TOTAL = 12  # 서로 다른 시각 10 + 가장 최근 같은 시각 둘
HOME_AUDIT_SHOWN = 10


def configured(app: FastAPI, **over: Any) -> Settings:
    """앱 설정을 문의 수신 주소가 있는 것으로 바꾼다(over 로 상한 칸 등을 덮는다)."""
    settings = Settings(**{"inquiry_notify_to": NOTIFY_TO, **over})
    app.state.settings = settings
    return settings


def inquiry_body(*, drop: Iterable[str] = (), **over: Any) -> dict[str, Any]:
    """INQUIRY_BODY 에 over 를 덮고 drop 의 키를 뺀 본문."""
    body = {**INQUIRY_BODY, **over}
    for key in drop:
        body.pop(key, None)
    return body


async def post_inquiry(
    client: httpx.AsyncClient,
    *,
    drop: Iterable[str] = (),
    headers: dict[str, str] | None = None,
    **over: Any,
) -> httpx.Response:
    return await client.post(
        PATH, json=inquiry_body(drop=drop, **over), headers=headers
    )


def fields(**over: Any) -> InquiryFields:
    """service 를 바로 부르는 시험의 접수 칸 — 스키마가 다듬은 값(이메일 소문자)을 흉내 낸다."""
    values: dict[str, Any] = {
        k: v for k, v in INQUIRY_BODY.items() if k not in ("privacy_agreed",)
    }
    values["email"] = NORMALIZED_EMAIL
    values.update(over)
    return InquiryFields(**values)


def submitted_values(body: dict[str, Any]) -> list[str]:
    """제출한 글자(회사명 · 담당자 · 연락처 · 부서직함 · 내용과 그 줄) — 확인 메일 본문에 없어야 한다."""
    out = [
        str(body[k])
        for k in ("company_name", "contact_name", "phone", "dept_title", "message")
        if body.get(k)
    ]
    message = body.get("message") or ""
    out += [line for line in message.splitlines() if line.strip()]
    return out


async def outbox_rows(
    session: AsyncSession,
) -> list[tuple[str, dict[str, Any], str, dt.datetime | None]]:
    """outbox 전부 (kind, params, to, sent_at), id 순."""
    rows = await session.execute(
        select(
            MailOutbox.kind, MailOutbox.params, MailOutbox.to, MailOutbox.sent_at
        ).order_by(MailOutbox.id)
    )
    return [tuple(r) for r in rows]  # type: ignore[misc]


async def age_inquiry(session: AsyncSession, inquiry_id: int, *, seconds: int) -> None:
    """그 문의의 접수 시각을 seconds 초 앞으로 민다(창 안·밖을 만든다)."""
    await session.execute(
        text(
            "UPDATE inquiry SET created_at = created_at - make_interval(secs => :s)"
            " WHERE id = :id"
        ),
        {"s": seconds, "id": inquiry_id},
    )


# ── 관리자 홈(T9b 결정 xiv)


@dataclass(frozen=True)
class Expected:
    """home_fixtures 의 기대값. counts 는 COUNT_KEYS → 수. audit_ids 는 최근 이력의 기대 순서(앞 10)."""

    admin: dict[str, int]
    instructor: dict[str, int]  # 강의 A 에 배정된 강사 X
    learner: dict[str, int]  # 강의 A 의 수강생
    admin_later: dict[str, int]  # 오늘 + LATER_DAYS 의 관리자 셈
    instructor_id: int
    learner_course_id: int
    audit_ids: list[int]


def _counts(**values: int) -> dict[str, int]:
    unknown = set(values) - set(COUNT_KEYS)
    assert not unknown, unknown
    return {**ZERO_COUNTS, **values}


async def _course(
    session: AsyncSession, start_on: dt.date, *, title: str, client: str = "A사"
) -> tuple[Course, int]:
    """평일 2일 강의와 섹션 하나 — (강의, 섹션 id)."""
    course, section = await course_with_section(
        session, start_on=start_on, title=title, client_name=client
    )
    return course, section.id


async def _session(
    session: AsyncSession, section_id: int, *, day_no: int, instructor_id: int | None
) -> int:
    row = await crud_schedule.insert_session(
        session,
        section_id,
        title="교육",
        day_no=day_no,
        slot=1,
        is_open=True,
        keywords=[],
        instructor_id=instructor_id,
    )
    return row.id


async def seed_audit(session: AsyncSession) -> list[int]:
    """at 을 명시한 audit 12행. 돌려주는 것은 최근 이력의 기대 순서 앞 10 — (at, id) 내림차순."""
    rows: list[tuple[int, AuditLog]] = []
    for minutes in [
        *range(1, AUDIT_DISTINCT + 1),
        AUDIT_DISTINCT + 1,
        AUDIT_DISTINCT + 1,
    ]:
        row = AuditLog(
            at=func.now() + dt.timedelta(minutes=minutes),
            actor="admin:1",
            action="home.seed",
            target_type="course",
            target_id=str(minutes),
            detail={"reason": "가명 사유"},
        )
        session.add(row)
        await session.flush()
        rows.append((minutes, row))
    ordered = sorted(rows, key=lambda mr: (mr[0], mr[1].id), reverse=True)
    return [row.id for _, row in ordered[:HOME_AUDIT_SHOWN]]


async def home_fixtures(
    session: AsyncSession, settings: Settings, *, today: dt.date
) -> Expected:
    """관리자 홈 셈 여덟의 양성·음성 행. 기대: 관리자 pending 2 · running 2 · unassigned 3 · unreviewed 2 · open_surveys 1 ·
    diagnoses_in_review 1 · records_missing 1 · new_photos 2 · 이력 10."""
    assert today.weekday() < 5, (
        "today 는 평일이어야 한다(강의 A·B 가 today 에 시작한다)"
    )
    days = dt.timedelta(days=1)
    # 강사: 대기 둘(셈 1) · 승인 X(강의 A 배정) · 승인 Y(고유 과정·커리큘럼 소유 · 강의 B 의 기록된 세션)
    for n in (1, 2):
        await make_instructor(session, settings, email=f"home-wait-{n}@example.com")
    x_id, _ = await approved(session, settings, email="home-x@example.com")
    y_id, _ = await approved(session, settings, email="home-y@example.com")

    # 진행 강의 A: X 세션(1일차 = 오늘, 기록 없음 → 미기록 1 · 사진 셋 중 하나 확인 → 새 사진 2) + 미배정 2일차(예정)
    course_a, sec_a = await _course(session, today, title="홈 강의 A")
    x_session = await _session(session, sec_a, day_no=1, instructor_id=x_id)
    await _session(session, sec_a, day_no=2, instructor_id=None)
    photos = [
        await crud_photo.insert_photo(
            session,
            course_id=course_a.id,
            session_id=x_session,
            by_kind="instructor",
            by_id=x_id,
            caption=None,
            taken_on=today,
        )
        for _ in range(3)
    ]
    assert await crud_photo.mark_seen(session, [photos[0].id]) == 1
    # 진행 강의 B(X 범위 밖): 미배정 2일차(예정 — 미기록 아님) + Y 의 1일차(기록 있음 — 미기록 아님)
    course_b, sec_b = await _course(session, today, title="홈 강의 B", client="B사")
    await _session(session, sec_b, day_no=2, instructor_id=None)
    y_session = await _session(session, sec_b, day_no=1, instructor_id=y_id)
    await crud_record.insert_record(
        session,
        session_id=y_session,
        status="done",
        values={"held_on": today, "content": "실제 진행"},
        by_kind="instructor",
        by_id=y_id,
        confirmed_by_id=None,
    )
    # 준비 강의(미배정 1) · 종료 강의(미배정 1 · 지난 일차 미기록 1) · 보관한 진행 강의(미배정 1 · 오늘 일차 미기록 1)
    _, sec_prep = await _course(session, today + 30 * days, title="홈 준비 강의")
    await _session(session, sec_prep, day_no=1, instructor_id=None)
    _, sec_end = await _course(session, today - 30 * days, title="홈 종료 강의")
    await _session(session, sec_end, day_no=1, instructor_id=None)
    archived, sec_arch = await _course(session, today, title="홈 보관 강의")
    await _session(session, sec_arch, day_no=1, instructor_id=None)
    await crud_course.update_course(
        session, archived, archived_at=dt.datetime.now(dt.UTC)
    )

    # 미검토 등록: Y 의 고유 과정(미검토 활성 1 · 미검토 비활성 1 · 검토됨 1) · 커리큘럼(미검토 활성 1 · 미검토 비활성 1) · AX 미검토 1
    own_open = await make_pool_course(
        session, owner_instructor_id=y_id, title="홈 과정 가"
    )
    own_off = await make_pool_course(
        session, owner_instructor_id=y_id, title="홈 과정 나"
    )
    await set_flags(session, own_off, active=False)
    own_done = await make_pool_course(
        session, owner_instructor_id=y_id, title="홈 과정 다"
    )
    await set_flags(session, own_done, reviewed=True)
    assert not own_open.reviewed and own_open.active
    await make_curriculum(session, instructor_id=y_id, title="홈 커리큘럼 가")
    cur_off = await make_curriculum(session, instructor_id=y_id, title="홈 커리큘럼 나")
    await set_flags(session, cur_off, active=False)
    ax = await make_pool_course(session, source="ax", title="홈 AX 과정")
    await set_flags(session, ax, reviewed=False)

    # 설문: A 는 열림(셈 1) · B 는 예정(내일 열림 — 셈 아님)
    for course_id, open_on in ((course_a.id, today), (course_b.id, today + days)):
        await crud_survey.insert_survey(
            session,
            course_id=course_id,
            template_id=None,
            template_name="홈 양식",
            questions=[],
            open_on=open_on,
            close_on=today + 14 * days,
        )
    # 진단: review 1(셈 1) · 음성 draft·final
    company = await make_company(session)
    for round_no, status in ((1, "review"), (2, "draft"), (3, "final")):
        await insert_round(session, company.id, round_no=round_no, status=status)

    audit_ids = await seed_audit(session)
    return Expected(
        admin=_counts(
            pending_instructors=2,
            running_courses=2,
            unassigned_sessions=3,
            unreviewed_registrations=2,
            open_surveys=1,
            diagnoses_in_review=1,
            records_missing=1,
            new_photos=2,
        ),
        instructor=_counts(
            running_courses=1,
            unassigned_sessions=1,
            open_surveys=1,
            records_missing=1,
            new_photos=2,
        ),
        learner=_counts(
            running_courses=1,
            unassigned_sessions=1,
            open_surveys=1,
            records_missing=1,
            new_photos=2,
        ),
        admin_later=_counts(
            pending_instructors=2,
            unassigned_sessions=1,
            unreviewed_registrations=2,
            diagnoses_in_review=1,
            new_photos=2,
        ),
        instructor_id=x_id,
        learner_course_id=course_a.id,
        audit_ids=audit_ids,
    )
