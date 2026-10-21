#!/usr/bin/env bash
# golden 대조(r3 N8·E9). 시안에서 다시 뽑은 값이 커밋된 tests/fixtures/golden.json 과 같은지 본다.
# 검사 본문은 여기 한 곳이다. .githooks/pre-push · 손 실행 · 대조 실험이 같은 이것을 부른다.
# CI 는 시안이 없어 이 대조를 못 하고, 커밋된 golden.json 을 단위 시험이 읽는다.
# 종료 0 같음("golden: OK") · 1 다름(diff 를 찍는다) · node 없음(미구성) · 추출 실패. 조용히 건너뛰지 않는다.
set -euo pipefail
cd "$(dirname "$0")/../.."

if ! command -v node >/dev/null 2>&1; then
  echo "미구성: node 가 없어 golden 대조를 못 한다"
  exit 1
fi

out=$(mktemp "${TMPDIR:-/tmp}/classfit-golden.XXXXXX")
trap 'rm -f "$out"' EXIT
if ! node scripts/golden/extract.mjs >"$out"; then
  echo "golden: 추출 실패 (scripts/golden/extract.mjs)"
  exit 1
fi
if ! diff -u tests/fixtures/golden.json "$out"; then
  echo "golden: 다름 — 시안에서 다시 뽑은 값(+)이 tests/fixtures/golden.json(-)과 다르다"
  exit 1
fi
echo "golden: OK"
