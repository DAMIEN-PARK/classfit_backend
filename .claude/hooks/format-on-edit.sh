#!/usr/bin/env bash
# PostToolUse(Edit|Write|MultiEdit): .py 편집 뒤 ruff 포맷·자동 수정(가상환경이 있을 때만). 항상 exit 0 — 정리만 하고 막지 않는다.
# 편집된 그 파일 하나에만 돈다. ruff 실패(문법 오류 등)는 삼키고, 남은 위반은 make lint 가 잡는다.
set -u
. "$(dirname "$0")/_json.sh"; eval "$(hook_read)"
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
case "$HOOK_FILE" in
  *.py)
    if [ -x "$root/.venv/bin/ruff" ] && [ -f "$HOOK_FILE" ]; then
      "$root/.venv/bin/ruff" format "$HOOK_FILE" >/dev/null 2>&1 || true
      "$root/.venv/bin/ruff" check --fix "$HOOK_FILE" >/dev/null 2>&1 || true
    fi;;
esac
exit 0
