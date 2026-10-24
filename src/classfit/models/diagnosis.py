"""AX 진단 표: company(회사) · diagnosis(진단 회차) · diag_link(자가진단 링크). 0010(T9a).

- 회사 삭제는 회차·링크 CASCADE 다(파일이 없다). 활성(archived_at IS NULL) 연결 강의가 있으면 service 가 409 로 막고,
  보관 강의의 연결은 course.company_id SET NULL 로 풀린다 — 그 UPDATE 가 강의 행 잠금을 기다린다(company → course 순).
- 회차 번호는 회사 안에서 유일하다(uq_diagnosis_company_id_round_no). 중간 번호는 당기지 않고, 마지막 번호를 지우면 다음
  회차가 최대 + 1 로 그 번호를 다시 받는다. 확정(final) 회차만 finalized_at·finalized_by_id 가 있다(CHECK 두 방향).
- 답 칸 answers 는 시안 답 키 "영역-지표"(ANSWER_KEYS) → 1..5, evidence 는 키 → [bool, bool], field 는 현장 활용 현황,
  matrix 는 직군 역량 "직군-역량" → 1..5, reco 는 권장 교육 구성(저장한 것 ∨ 확정 때 스냅샷). 응답자 respondent 는
  링크 회차에만 있다.
- 링크 토큰은 평문 유일이다(관리자 화면이 다시 복사한다 — T2a 초대코드 전례). open 링크는 회사당 하나다(부분 유일
  uq_diag_link_company_open). 만료는 저장하지 않고 계산한다(open ∧ expires_on < 오늘). 제출한 링크는 만든 회차를
  diagnosis_id 로 가리키고(FK NO ACTION 유일), 그 회차를 지우면 crud 가 먼저 링크를 revoked 로 바꾸고 diagnosis_id 를
  푼다 — submitted_at 은 이력으로 남는다.
- 기록자 칸(created_by · finalized_by_id)은 FK 없는 주체 표기다(audit_log.actor 꼴 — admin:<id> · link).
- stored_file owner_kind diagnosis_pdf 는 등록만 했다. 1차에 그 행을 만드는 경로는 없다(PDF 501).
- 상수는 schemas 가 모양 검사에 쓴다(schemas → models 는 아래 방향).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin

PHASES = ("pre", "post")
MODES = ("visit", "link")
DIAG_STATUSES = ("draft", "review", "final")
LINK_STATUSES = ("open", "submitted", "revoked")  # expired 는 계산 상태다(칸이 아니다)
COMPANY_SIZES = ("lt10", "s10_49", "s50_99", "s100_299", "ge300")  # 시안 SIZE_ALL 5구간
AREA_SIZES = (5, 4, 4, 4)  # 영역마다 지표 수(service.rules.diagnosis 와 같다)
ANSWER_KEYS = tuple(f"{a}-{i}" for a, n in enumerate(AREA_SIZES) for i in range(n))
MATRIX_KEYS = tuple(f"{r}-{c}" for r in range(3) for c in range(4))  # 직군 3 × 역량 4
DEPTS_MAX = 20  # 회사 부서 수 상한 = 트랙 상한(DB CHECK 와 같다)
TRACKS_MAX = 20
TRACK_COURSES_MAX = 20
CANDIDATES_MAX = 3  # 트랙마다 대표 과정 후보(service.rules.reco 와 같다)
GROUP_KEYS = ("eng", "cs", "buy", "prod", "qa", "vis", "film", "mgt")
TOKEN_LENGTH = 32

# (이름, 식) — 0010 의 같은 이름 튜플과 같은 글자
COMPANY_CHECKS = (
    # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다 — btrim 은 스페이스만 지운다
    ("name", "name ~ '[^[:space:]]'"),
    ("contact", "contact ~ '[^[:space:]]'"),
    ("size", "size IN ('lt10', 's10_49', 's50_99', 's100_299', 'ge300')"),
    ("depts", "coalesce(array_length(depts, 1), 0) <= 20"),
)
DIAGNOSIS_CHECKS = (
    ("round_no", "round_no >= 1"),
    ("phase", "phase IN ('pre', 'post')"),
    ("mode", "mode IN ('visit', 'link')"),
    ("status", "status IN ('draft', 'review', 'final')"),
    ("respondent", "mode = 'link' OR respondent IS NULL"),
    ("finalized_status", "(status = 'final') = (finalized_at IS NOT NULL)"),
    ("finalized_pair", "(finalized_at IS NULL) = (finalized_by_id IS NULL)"),
)
LINK_CHECKS = (
    ("token", "token ~ '^[A-Za-z0-9_-]{32}$'"),
    ("phase", "phase IN ('pre', 'post')"),
    ("period", "issued_on <= expires_on"),
    ("status", "status IN ('open', 'submitted', 'revoked')"),
    ("submitted_at", "status <> 'submitted' OR submitted_at IS NOT NULL"),
    ("revoked_at", "status <> 'revoked' OR revoked_at IS NOT NULL"),
    ("submitted_history", "submitted_at IS NULL OR status IN ('submitted', 'revoked')"),
    ("diagnosis_submitted", "diagnosis_id IS NULL OR status = 'submitted'"),
)


class Company(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "company"
    __table_args__ = tuple(CheckConstraint(sql, name=n) for n, sql in COMPANY_CHECKS)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str] = mapped_column(Text, nullable=False)  # 담당자
    phone: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(
        Text
    )  # 시안 IND_ALL + 기타 직접 입력이라 자유 글자
    size: Mapped[str | None] = mapped_column(Text)  # COMPANY_SIZES 코드
    depts: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    memo: Mapped[str | None] = mapped_column(Text)


class Diagnosis(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "diagnosis"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "round_no", name="uq_diagnosis_company_id_round_no"
        ),
        *(CheckConstraint(sql, name=n) for n, sql in DIAGNOSIS_CHECKS),
    )

    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("company.id", ondelete="CASCADE"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosed_on: Mapped[dt.date] = mapped_column(Date, nullable=False)  # 링크면 제출일
    created_by: Mapped[str] = mapped_column(Text, nullable=False)  # admin:<id> · link
    # NULL 허용 JSONB 는 none_as_null — 기본값이면 None 이 JSON null 로 들어가 IS NULL CHECK 를 어긴다
    respondent: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    field: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    matrix: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    reco: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    finalized_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by_id: Mapped[int | None] = mapped_column(BigInteger)


class DiagLink(BigIdMixin, TimestampMixin, Base):
    __tablename__ = "diag_link"
    __table_args__ = (
        *(CheckConstraint(sql, name=n) for n, sql in LINK_CHECKS),
        Index(
            "uq_diag_link_company_open",
            "company_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str | None] = mapped_column(Text)  # 받는 분(비면 회사 담당자)
    issued_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    expires_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    diagnosis_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("diagnosis.id"), unique=True
    )
