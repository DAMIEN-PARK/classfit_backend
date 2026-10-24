"""경화: survey.template_id 색인 + 이름·제목 CHECK 여섯을 공백류 꼴로

- survey.template_id(FK → survey_template ON DELETE SET NULL)에 색인 ix_survey_template_id 를 둔다. 양식 삭제 · 배포 수 셈 ·
  양식별 잠금이 설문 표를 훑지 않게 한다(T11 결정 xii).
- 0004~0006 의 CHECK 여섯(enrollment·instructor 의 name, pool_course·curriculum·curriculum_slot·advanced_course 의 title)은
  length(btrim(x)) BETWEEN 1 AND n 이라 스페이스만 지워 탭·줄바꿈만 있는 값을 받았다. 0008 꼴
  x ~ '[^[:space:]]' AND length(btrim(x)) <= n 으로 다시 만든다(이름·n 그대로). 옛 식이 받던 값 중 새 식이 거절하는 것은
  스페이스가 아닌 공백류만 있는 값뿐이고, 새 식이 더 받는 값은 없다.
- 다시 만들기 전에 표마다 새 식을 어기는 행을 세어 있으면 멈추고 그 수를 알린다(0005 GUARD 꼴). lock_timeout 을 먼저 둔다.
- downgrade 는 옛 식으로 되돌리고 색인을 지운다.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-24
"""

from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TEMPLATE_INDEX = "ix_survey_template_id"
# 공백류(스페이스·탭·줄바꿈)가 아닌 글자가 하나는 있다 — btrim 은 스페이스만 지운다
NAME_CHECK = "name ~ '[^[:space:]]' AND length(btrim(name)) <= 50"
TITLE_CHECK = "title ~ '[^[:space:]]' AND length(btrim(title)) <= 200"
OLD_NAME_CHECK = "length(btrim(name)) BETWEEN 1 AND 50"
OLD_TITLE_CHECK = "length(btrim(title)) BETWEEN 1 AND 200"
# (표, 칸 = 제약 이름 끝, 새 식, 옛 식) — 새 식은 models/{learner,instructor,pool}.py 의 CheckConstraint 와 같은 글자
CHECKS = (
    ("enrollment", "name", NAME_CHECK, OLD_NAME_CHECK),
    ("instructor", "name", NAME_CHECK, OLD_NAME_CHECK),
    ("pool_course", "title", TITLE_CHECK, OLD_TITLE_CHECK),
    ("curriculum", "title", TITLE_CHECK, OLD_TITLE_CHECK),
    ("curriculum_slot", "title", TITLE_CHECK, OLD_TITLE_CHECK),
    ("advanced_course", "title", TITLE_CHECK, OLD_TITLE_CHECK),
)

GUARD = """
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM {table} WHERE NOT ({check});
  IF n > 0 THEN
    RAISE EXCEPTION '0012 중단 - {table}.{column} 이 공백류만 있는 행 % 개. 그 행을 고치거나 지운 뒤 다시 돌린다 (T11 결정 xii)', n;
  END IF;
END $$
"""


def _replace(table: str, column: str, sql: str) -> None:
    name = op.f(f"ck_{table}_{column}")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, sql)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table, column, new, _ in CHECKS:
        op.execute(GUARD.format(table=table, column=column, check=new))
    op.create_index(op.f(TEMPLATE_INDEX), "survey", ["template_id"])
    for table, column, new, _ in CHECKS:
        _replace(table, column, new)


def downgrade() -> None:
    for table, column, _, old in CHECKS:
        _replace(table, column, old)
    op.drop_index(op.f(TEMPLATE_INDEX), table_name="survey")
