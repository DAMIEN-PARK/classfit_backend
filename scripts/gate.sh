#!/usr/bin/env bash
# 결정론 검사. 실패를 모아 마지막에 exit 1. make verify · .githooks/pre-push · CI 가 같은 이 스크립트를 부른다.
# 금지 import(asyncpg·openai·langchain·동기 세션/엔진)는 ruff TID251(pyproject [tool.ruff.lint.flake8-tidy-imports.banned-api])이
# AST 로 잡는다 — grep 은 여러 줄 import 를 놓친다. 여기는 grep 으로 충분한 것만 둔다.
set -u
cd "$(dirname "$0")/.." || exit 2
PKG=classfit
SRC="src/$PKG"
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY=python3
fail=0
note() { echo "GATE FAIL: $*"; fail=1; }

# 1. requirements 행 — 금지 패키지. langchain-core(langgraph 이행 의존성)는 허용하므로 이름 바로 뒤가 버전 기호·공백·줄끝일 때만 잡는다.
if grep -niE '^(asyncpg|langchain|openai|psycopg2|psycopg2-binary)(\[[^]]*\])?[[:space:]]*([=<>~!;]|$)' \
     requirements.in requirements.txt requirements-dev.in requirements-dev.txt 2>/dev/null; then
  note "금지 패키지가 requirements 에 있음"
fi

# 2. IP 리터럴 — 값 단위로 뽑아 허용 목록(192.0.2.0/24 시험 자료 · 127.x 루프백 · 0.0.0.0)과 대조. OID 같은 긴 점 숫자는 제외.
ips=$(grep -rnoE '(^|[^0-9.])([0-9]{1,3}\.){3}[0-9]{1,3}([^0-9.]|$)' "$SRC" tests alembic scripts \
        --include='*.py' --include='*.sh' --include='*.sql' 2>/dev/null \
      | grep -v '^scripts/gate.sh:' \
      | sed -E 's/^([^:]+:[0-9]+):[^0-9]*(([0-9]{1,3}\.){3}[0-9]{1,3}).*$/\1 \2/' \
      | awk '$2 !~ /^(192\.0\.2\.[0-9]+|127\.[0-9]+\.[0-9]+\.[0-9]+|0\.0\.0\.0)$/')
if [ -n "$ips" ]; then
  echo "$ips"; note "IP 리터럴 (시험 자료는 192.0.2.0/24 만)"
fi

# 3. 실고객사명·도메인 (scripts/forbidden_terms.txt, 한 줄 하나, # 주석)
if [ -s scripts/forbidden_terms.txt ]; then
  terms=$(grep -vE '^[[:space:]]*(#|$)' scripts/forbidden_terms.txt | paste -sd'|' -)
  if [ -n "$terms" ] && grep -rniE "$terms" "$SRC" tests alembic scripts \
       --include='*.py' --include='*.json' --include='*.sql' --include='*.sh'; then
    note "금지 용어 (실고객사명·도메인)"
  fi
fi

# 4. 정면(facade) 재노출을 unittest.mock.patch 로 때리는 시험 — stale_patch_guard 는 monkeypatch 만 감시한다
if grep -rnE "\bpatch(\.object)?\([[:space:]]*[\"']classfit\.models\." tests --include='*.py'; then
  note "classfit.models(정면) 을 mock.patch — 원래 모듈(classfit.models.<파일>) 을 patch 하라"
fi

# 5. 파일 크기
"$PY" scripts/check_file_size.py || note "파일 크기 상한"

# 6. 비밀
bash scripts/check_secrets.sh || note "비밀"

# 7. 패키징 — 비-.py 패키지 자료(JSON 스키마 등)가 생기면 check_packaging.py 를 더한다 (글롭이 0장이어도 조용하다)

if [ "$fail" -eq 0 ]; then echo "gate: OK"; fi
exit "$fail"
