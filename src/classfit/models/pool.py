"""과정 풀 표: pool_course(AX·고유 과정) · pool_course_file · capability(강사 역량) · capability_file. 0006(T4).

- pool_course.id 는 Text 다: AX 는 파일 값(`ax-…`) 또는 관리자 추가 `ax-custom-<n>`, 고유 과정은 `own-<강사 id>-<n>`
  (기획안 7절 :898, T4 결정 xiii). 번호는 시퀀스 pool_id_seq 에서 받는다(crud.pool.next_id).
- source 는 ax·own 이고, 소유 강사는 own 일 때만 있다(CHECK owner 두 방향).
- 상태는 불리언 셋 reviewed·pub·active 다(T4 결정 v). pub ⇒ reviewed 는 CHECK 가 아니라 service 규칙이다 —
  검토 뒤 강사가 고치면 reviewed 만 false 로 돌아가고 pub·active 는 남는다(결정 vi). reviewed_at 은 그때도 남는다.
- 직무군은 ARRAY(Text) + CHECK cardinality ≥ 1, 값 집합 JOB_GROUPS 는 schemas·service 가 본다(결정 xiv).
- 파일 표 셋(pool_course_file · capability_file · curriculum_file)은 칸이 같다(_PoolFileCols). kind 는 T2b 첨부와 같은
  5종 CHECK 와 대상 CHECK target 이고, 넣기는 파일 행 → stored_file(owner_id = 파일 행 id) → file_id 채움 순서다.
- FK 는 전부 기본 NO ACTION 이다. 역량을 지우는 crud 가 파일 행과 stored_file 행을 먼저 지운다(결정 x).
  고유 과정·커리큘럼은 지우지 않고 active=false 로 둔다(결정 xi).
- server_default 글자는 0006 과 같다(alembic check 가 비교한다).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from classfit.models.base import Base, BigIdMixin, TimestampMixin

# 대상 직무군 13 = 공통(전 직원) + 공통 직무 12(시안 관리자.html:929 DEPT_NAMES = 강사.html:644 DEPTS)
JOB_GROUPS = (
    "공통(전 직원)",
    "경영·관리",
    "사무·행정",
    "기획·전략",
    "인사·총무·회계",
    "영업·마케팅",
    "고객응대(CS)",
    "구매·자재·물류",
    "생산·제조",
    "품질·안전",
    "연구개발·설계",
    "IT·개발·데이터",
    "디자인·콘텐츠",
)
DIFFICULTIES = ("하", "중", "상")
POOL_SOURCES = ("ax", "own")
MINUTES_RANGE = (10, 600)  # 과정 분(API·import 공통, 결정 ii)
POOL_FILES_MAX = 20  # 소유자(역량·고유 과정·커리큘럼 1건)당 파일 행 상한(결정 viii)
ID_TRIES = 100  # next_id 의 존재 검사 횟수 상한(결정 xiii)
POOL_FLAGS = ("reviewed", "pub", "active")
# 입력 글자·목록 상한 한 벌(API 스키마 · import 공통, 리뷰 Nit 3). 넘는 import 행은 exit 2 로 멈춘다
POOL_ID_MAX = 80  # 글자 id(ax-… · own-<n>-<n> · cur-<n>-<n> · adv-<n>)
POOL_TITLE_MAX = 200  # 제목(표 CHECK 와 같다)
POOL_TEXT_MAX = 2000  # 목표·산출물·실습 자료 같은 긴 글
POOL_ITEM_MAX = 500  # 이론·실습 한 줄 · 진행표 내용 칸
POOL_ITEMS_MAX = 30  # 이론·실습 줄 수
POOL_SCHEDULE_MAX = 50  # 진행표 줄 수
POOL_SCHEDULE_CELL_MAX = 20  # 진행표 시각·종류 칸
# 내용 칸. 강사가 이 중 하나를 바꾸면 reviewed=false(결정 vi), 관리자는 고유 과정의 이 칸을 못 고친다(결정 xviii),
# import 는 이 칸으로 내용 지문을 만든다(결정 iii)
POOL_CONTENT_FIELDS = (
    "title",
    "job_groups",
    "difficulty",
    "minutes",
    "goal",
    "output",
    "material",
    "theory",
    "practice",
    "schedule",
)

_TITLE_CHECK = "length(btrim(title)) BETWEEN 1 AND 200"
_DIFFICULTY_CHECK = "difficulty IN ('하', '중', '상')"
_JOB_GROUPS_CHECK = "cardinality(job_groups) >= 1"


def _file_checks() -> tuple[CheckConstraint, CheckConstraint]:
    """파일 표의 CHECK 둘(T2b session_attachment 와 같은 글자). 표마다 새 객체여야 이름이 그 표로 붙는다."""
    return (
        CheckConstraint(
            "kind IN ('pdf', 'office', 'html', 'link', 'image')", name="kind"
        ),
        CheckConstraint(
            "((kind = 'link') = (url IS NOT NULL))"
            " AND (kind <> 'link' OR file_id IS NULL)",
            name="target",
        ),
    )


class _PoolFileCols:
    """파일 표 셋의 공통 칸. owner_fk 는 소유 행을 가리키는 칸 이름이다(crud.pool_file 이 쓴다)."""

    owner_fk: ClassVar[str]

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stored_file.id"), unique=True
    )
    url: Mapped[str | None] = mapped_column(Text)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class PoolCourse(TimestampMixin, Base):
    __tablename__ = "pool_course"
    __table_args__ = (
        CheckConstraint("source IN ('ax', 'own')", name="source"),
        CheckConstraint(
            "(source = 'own') = (owner_instructor_id IS NOT NULL)", name="owner"
        ),
        CheckConstraint(_TITLE_CHECK, name="title"),
        CheckConstraint(_JOB_GROUPS_CHECK, name="job_groups"),
        CheckConstraint(_DIFFICULTY_CHECK, name="difficulty"),
        CheckConstraint("minutes > 0", name="minutes"),
        Index("ix_pool_course_source_active", "source", "active"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    owner_instructor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("instructor.id"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    job_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    difficulty: Mapped[str] = mapped_column(Text, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    theory: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    practice: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    # 진행표 [[시간, 종류, 내용], …](시안 관리자.html:866 AX_DETAIL.schedule)
    schedule: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    pub: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column()


class PoolCourseFile(_PoolFileCols, BigIdMixin, Base):
    __tablename__ = "pool_course_file"
    __table_args__ = (
        *_file_checks(),
        Index(
            "ix_pool_course_file_pool_course_id_sort_id", "pool_course_id", "sort", "id"
        ),
    )
    owner_fk: ClassVar[str] = "pool_course_id"

    pool_course_id: Mapped[str] = mapped_column(
        Text, ForeignKey("pool_course.id"), nullable=False
    )


class Capability(BigIdMixin, TimestampMixin, Base):
    """강사 역량(가능 표시) 하나. 강사 × 풀 과정마다 한 행이다(T4 결정 x)."""

    __tablename__ = "capability"
    __table_args__ = (
        UniqueConstraint(
            "instructor_id",
            "pool_course_id",
            name="uq_capability_instructor_id_pool_course_id",
        ),
        Index("ix_capability_pool_course_id", "pool_course_id"),
    )

    instructor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instructor.id"), nullable=False
    )
    pool_course_id: Mapped[str] = mapped_column(
        Text, ForeignKey("pool_course.id"), nullable=False
    )
    memo: Mapped[str | None] = mapped_column(Text)


class CapabilityFile(_PoolFileCols, BigIdMixin, Base):
    __tablename__ = "capability_file"
    __table_args__ = (
        *_file_checks(),
        Index(
            "ix_capability_file_capability_id_sort_id", "capability_id", "sort", "id"
        ),
    )
    owner_fk: ClassVar[str] = "capability_id"

    capability_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("capability.id"), nullable=False
    )
