"""만족도 설문: survey_template(기본 양식 시드 1행) · survey · survey_response

- survey_template 은 이름(공백류뿐 금지 · 100자까지) · 비고 · 기본 표시 · 문항 JSONB 배열. 기본 양식은 부분 유일 색인
  uq_survey_template_default WHERE is_default 로 많아야 하나다.
- survey 는 강의(FK CASCADE — 파일이 없다) · 양식(FK SET NULL) · 양식 이름·문항 스냅샷 · 열림일 ≤ 닫힘일(날짜) ·
  닫은 시각 · 다시 연 시각 · 현재 표시. 상태 칸은 없다(오늘로 계산, T8 결정 iii). 강의당 현재 설문은 부분 유일 색인
  uq_survey_course_id_current WHERE current 로 하나, 밀려난 행은 닫혀 있다(CHECK current OR closed_at IS NOT NULL).
  색인은 course_id · (created_at, id)(관리자 목록 키셋).
- survey_response 는 설문(FK CASCADE) · 등록(FK NO ACTION) · 답 JSONB 객체 · 제출 시각(어떤 응답 API 에도 싣지 않는다).
  (설문, 등록) 유일 — 1인 1회.
- 기본 양식 시드: DEFAULT_QUESTIONS(24문항 — 안내 1 · 응답자 정보 4 · 교육 평가 척도 12 · 주관식 3 · 종합 1 · 후속 수요 3,
  T8 결정 v · 시안 관리자.html mkTpl)가 그 글자의 유일한 자리다. downgrade 는 표와 함께 지운다.
- 기존 표를 바꾸지 않으므로 행 가드가 없다. lock_timeout 만 둔다(0008 꼴).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-24
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# (이름, 식) — models/survey.py 의 CheckConstraint 와 같은 글자
TEMPLATE_CHECKS = (
    # 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다 — btrim 은 스페이스만 지운다
    ("name", "name ~ '[^[:space:]]'"),
    ("name_length", "length(name) <= 100"),
    ("questions", "jsonb_typeof(questions) = 'array'"),
)
SURVEY_CHECKS = (
    ("period", "open_on <= close_on"),
    ("current_closed", "current OR closed_at IS NOT NULL"),
)
RESPONSE_ANSWERS_CHECK = "jsonb_typeof(answers) = 'object'"
SURVEY_INDEXES = (("course_id",), ("created_at", "id"))

DEPT_OPTIONS = [
    "경영지원",
    "인사·총무",
    "재무·회계",
    "기획·전략",
    "영업",
    "마케팅",
    "고객지원(CS)",
    "구매·자재",
    "생산·제조",
    "품질",
    "연구개발(R&D)",
    "설계·기술",
    "IT·정보시스템",
    "물류·유통",
    "디자인",
    "법무·감사",
]
JOB_OPTIONS = [
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
]
# (key, 영역, 별표, 문구) — 교육 평가 척도 12(대표 문항 1·4·7·10·11 에 별표)
EVALUATION = [
    ("b01", "교육 내용", True, "교육 내용이 업무에 필요한 수준으로 구성되었다"),
    ("b02", "교육 내용", False, "교육 자료(교안·실습 파일)가 이해하기 쉬웠다"),
    ("b03", "교육 내용", False, "교육 시간 배분(이론·실습)이 적절했다"),
    ("b04", "강사·운영", True, "강사가 내용을 명확하게 전달했다"),
    ("b05", "강사·운영", False, "강사가 질문과 실습 문제에 충분히 대응했다"),
    ("b06", "강사·운영", False, "교육 운영(일정·장소·안내)이 원활했다"),
    ("b07", "직무 활용", True, "교육에서 배운 내용을 내 업무에 바로 적용할 수 있다"),
    ("b08", "직무 활용", False, "실습 결과물이 실제 업무 산출물과 연결된다"),
    ("b09", "직무 활용", False, "부서 동료에게 배운 내용을 전달할 수 있다"),
    ("b10", "정보보안", True, "AI 사용 시 지켜야 할 보안 기준을 이해했다"),
    ("b11", "향후 활용", True, "추가 심화 교육에 참여할 의향이 있다"),
    ("b12", "향후 활용", False, "AI 도구를 업무에 계속 활용할 계획이다"),
]
OVERALL_AREA = "종합"


def _q(
    key: str,
    kind: str,
    text: str,
    *,
    area: str | None = None,
    required: bool = False,
    star: bool = False,
    is_overall: bool = False,
    options: list[str] | None = None,
    custom: bool = False,
) -> dict[str, Any]:
    """문항 하나 — 아홉 키가 늘 있다(T8 결정 v)."""
    return {
        "key": key,
        "type": kind,
        "text": text,
        "area": area,
        "required": required,
        "star": star,
        "is_overall": is_overall,
        "options": options,
        "custom": custom,
    }


DEFAULT_QUESTIONS = [
    _q("info", "info", "응답자 정보는 통계 목적에만 쓰이며 개인이 식별되지 않습니다."),
    _q("dept", "single", "소속 부서", required=True, options=DEPT_OPTIONS, custom=True),
    _q("job", "single", "담당 직무", required=True, options=JOB_OPTIONS, custom=True),
    _q(
        "exp",
        "single",
        "교육 전 생성형 AI 사용 경험",
        required=True,
        options=["거의 없음", "가끔 사용", "주 1회 이상", "거의 매일"],
    ),
    _q(
        "part", "single", "참여 형태", required=True, options=["전체 참여", "일부 참여"]
    ),
    *(
        _q(key, "scale", text, area=area, required=True, star=star)
        for key, area, star, text in EVALUATION
    ),
    _q("c1", "text", "가장 도움이 된 내용"),
    _q("c2", "text", "개선할 점"),
    _q("c3", "text", "추가로 배우고 싶은 것"),
    _q(
        "overall",
        "scale",
        "이번 교육에 전반적으로 만족한다",
        area=OVERALL_AREA,
        required=True,
        star=True,
        is_overall=True,
    ),
    _q(
        "next_type",
        "multi",
        "이어서 듣고 싶은 교육 유형",
        area=OVERALL_AREA,
        options=["심화 실습", "부서 맞춤 과정", "리더십 세션", "PoC 컨설팅"],
    ),
    _q(
        "next_when",
        "single",
        "희망 시기",
        area=OVERALL_AREA,
        options=["1개월 이내", "3개월 이내", "6개월 이내", "미정"],
    ),
    _q(
        "next_how",
        "single",
        "희망 방식",
        area=OVERALL_AREA,
        options=["집체", "온라인(ZOOM)", "혼합"],
    ),
]
DEFAULT_TEMPLATE = {
    "name": "기본 양식",
    "note": "현행 만족도 조사지 구조",
    "is_default": True,
    "questions": DEFAULT_QUESTIONS,
}


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _jsonb(name: str) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=False)


def _template() -> sa.Table:
    table = op.create_table(
        "survey_template",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        _jsonb("questions"),
        _now("created_at"),
        _now("updated_at"),
        *(
            sa.CheckConstraint(sql, name=op.f(f"ck_survey_template_{name}"))
            for name, sql in TEMPLATE_CHECKS
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_survey_template")),
    )
    op.create_index(
        "uq_survey_template_default",
        "survey_template",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    assert table is not None
    return table


def _survey() -> None:
    op.create_table(
        "survey",
        _id(),
        sa.Column("course_id", sa.BigInteger(), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=True),
        sa.Column("template_name", sa.Text(), nullable=False),
        _jsonb("questions"),
        sa.Column("open_on", sa.Date(), nullable=False),
        sa.Column("close_on", sa.Date(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "current", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        _now("created_at"),
        _now("updated_at"),
        *(
            sa.CheckConstraint(sql, name=op.f(f"ck_survey_{name}"))
            for name, sql in SURVEY_CHECKS
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["course.id"],
            name=op.f("fk_survey_course_id_course"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["survey_template.id"],
            name=op.f("fk_survey_template_id_survey_template"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_survey")),
    )
    for columns in SURVEY_INDEXES:
        op.create_index(op.f("ix_survey_" + "_".join(columns)), "survey", list(columns))
    op.create_index(
        "uq_survey_course_id_current",
        "survey",
        ["course_id"],
        unique=True,
        postgresql_where=sa.text("current"),
    )


def _response() -> None:
    op.create_table(
        "survey_response",
        _id(),
        sa.Column("survey_id", sa.BigInteger(), nullable=False),
        sa.Column("enrollment_id", sa.BigInteger(), nullable=False),
        _jsonb("answers"),
        _now("submitted_at"),
        sa.CheckConstraint(
            RESPONSE_ANSWERS_CHECK, name=op.f("ck_survey_response_answers")
        ),
        sa.ForeignKeyConstraint(
            ["survey_id"],
            ["survey.id"],
            name=op.f("fk_survey_response_survey_id_survey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["enrollment.id"],
            name=op.f("fk_survey_response_enrollment_id_enrollment"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_survey_response")),
        sa.UniqueConstraint(
            "survey_id",
            "enrollment_id",
            name="uq_survey_response_survey_id_enrollment_id",
        ),
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    template = _template()
    _survey()
    _response()
    op.bulk_insert(template, [DEFAULT_TEMPLATE])


def downgrade() -> None:
    op.drop_table("survey_response")
    op.drop_index("uq_survey_course_id_current", table_name="survey")
    for columns in reversed(SURVEY_INDEXES):
        op.drop_index(op.f("ix_survey_" + "_".join(columns)), table_name="survey")
    op.drop_table("survey")
    op.drop_index("uq_survey_template_default", table_name="survey_template")
    op.drop_table("survey_template")
