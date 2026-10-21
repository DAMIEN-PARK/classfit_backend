#!/usr/bin/env bash
# 결정론 검사. 실패를 모아 마지막에 exit 1. make verify · .githooks/pre-push · CI 가 같은 이 스크립트를 부른다.
# 금지 import(asyncpg·openai·langchain·알려진 langchain_* 통합 패키지·동기 세션/엔진)는 ruff TID251
# (pyproject [tool.ruff.lint.flake8-tidy-imports.banned-api])이 AST 로 잡는다 — grep 은 여러 줄 import 를 놓친다.
# 여기는 grep 으로 충분한 것만 둔다(모듈 이름은 import 줄 머리에 항상 있다). 회귀 시험: scripts/test_gate.sh
set -u
cd "$(dirname "$0")/.." || exit 2
PKG=classfit
SRC="src/$PKG"
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
fail=0
note() { echo "GATE FAIL: $*"; fail=1; }

# 1. requirements 행 — 금지 패키지. pip 는 이름의 대소문자와 `-_.` 를 같게 본다(PEP 503) → 소문자 + `[-_.]+` → `-` 로 정규화한 뒤 대조.
#    langchain-core(langgraph 이행 의존성)만 허용. 주석·옵션 행(-r·-e·--…)은 이름이 아니라 건너뛴다.
req_files=""
for f in requirements.in requirements.txt requirements-dev.in requirements-dev.txt; do
  [ -f "$f" ] && req_files="$req_files $f"
done
if [ -n "$req_files" ]; then
  # shellcheck disable=SC2086  # 파일 이름에 공백 없음(위 고정 목록)
  req_hits=$(awk '
    { line = $0; sub(/^[ \t]+/, "", line) }
    line ~ /^[A-Za-z0-9]/ {
      match(line, /^[A-Za-z0-9][A-Za-z0-9._-]*/)
      name = tolower(substr(line, 1, RLENGTH))
      gsub(/[-_.]+/, "-", name)
      if (name != "langchain-core" && name ~ /^(asyncpg|openai|psycopg2|psycopg2-binary|langchain|langchain-[a-z0-9-]+)$/)
        print FILENAME ":" FNR ": " name
    }' $req_files)
  if [ -n "$req_hits" ]; then
    echo "$req_hits"; note "금지 패키지가 requirements 에 있음"
  fi
fi

# 2. langchain_* import 접두 — ruff 목록 밖의 통합 패키지까지. langchain_core 만 예외.
lc_hits=$(grep -rnE '^[[:space:]]*(from|import)[[:space:]]+langchain_[a-z0-9_]+' src tests alembic scripts \
            --include='*.py' 2>/dev/null \
          | grep -vE '^[^:]+:[0-9]+:[[:space:]]*(from|import)[[:space:]]+langchain_core([.,[:space:]]|$)')
if [ -n "$lc_hits" ]; then
  echo "$lc_hits"; note "langchain_* import (langchain_core 만 허용)"
fi

# 3. IP 리터럴 — 값 단위로 뽑아 허용 목록(192.0.2.0/24 시험 자료 · 127.x 루프백 · 0.0.0.0)과 대조. OID 같은 긴 점 숫자는 제외.
ips=$(grep -rnoE '(^|[^0-9.])([0-9]{1,3}\.){3}[0-9]{1,3}([^0-9.]|$)' "$SRC" tests alembic scripts \
        --include='*.py' --include='*.sh' --include='*.sql' 2>/dev/null \
      | grep -v '^scripts/gate.sh:' \
      | sed -E 's/^([^:]+:[0-9]+):[^0-9]*(([0-9]{1,3}\.){3}[0-9]{1,3}).*$/\1 \2/' \
      | awk '$2 !~ /^(192\.0\.2\.[0-9]+|127\.[0-9]+\.[0-9]+\.[0-9]+|0\.0\.0\.0)$/')
if [ -n "$ips" ]; then
  echo "$ips"; note "IP 리터럴 (시험 자료는 192.0.2.0/24 만)"
fi

# 4. 실고객사명·도메인 (scripts/forbidden_terms.txt, 한 줄 하나, # 주석)
#    pre-push·CI 는 CLASSFIT_FORBIDDEN_TERMS_REQUIRED=1 — 목록 파일이 없으면(gitignore 뒤 주입 누락) 실패. 목록 행 0개는 통과.
#    맞으면 file:line 만 찍는다. 맞은 줄 내용은 찍지 않는다(CI 로그로 실명이 새지 않게).
terms_file=scripts/forbidden_terms.txt
if [ -f "$terms_file" ]; then
  terms=$(grep -vE '^[[:space:]]*(#|$)' "$terms_file" | paste -sd'|' -)
  if [ -n "$terms" ]; then
    hits=$(grep -rnoiE "$terms" src tests alembic scripts docs ./*.md \
             --include='*.py' --include='*.json' --include='*.sql' --include='*.sh' --include='*.md' \
             --exclude='forbidden_terms.txt' 2>/dev/null \
           | cut -d: -f1,2 | uniq)
    if [ -n "$hits" ]; then
      echo "$hits"; note "금지 용어 (실고객사명·도메인) — 위치만 표시"
    fi
  fi
elif [ "${CLASSFIT_FORBIDDEN_TERMS_REQUIRED:-}" = "1" ]; then
  note "금지 용어 목록이 필요한데 없음 ($terms_file)"
fi

# 5. 정면(facade) 재노출을 unittest.mock.patch 로 때리는 시험 — stale_patch_guard 는 monkeypatch 만 감시한다
if grep -rnE "\bpatch(\.object)?\([[:space:]]*[\"']classfit\.models\." tests --include='*.py'; then
  note "classfit.models(정면) 을 mock.patch — 원래 모듈(classfit.models.<파일>) 을 patch 하라"
fi

# 6. 파일 크기
"$PY" scripts/check_file_size.py || note "파일 크기 상한"

# 7. 비밀
bash scripts/check_secrets.sh || note "비밀"

# 8. 패키징 — 비-.py 패키지 자료(JSON 스키마 등)가 생기면 check_packaging.py 를 더한다 (글롭이 0장이어도 조용하다)

if [ "$fail" -eq 0 ]; then echo "gate: OK"; fi
exit "$fail"
