#!/usr/bin/env bash
# PreToolUse(Edit|Write|MultiEdit): 버그 픽스 모드(.claude/fix-mode)에서 tests/** 편집을 차단한다. exit 2 = 차단.
# fix-mode 는 make fix-start 가 만들고 make fix-end 가 지운다(안내서 §6.10).
set -u
. "$(dirname "$0")/_json.sh"; eval "$(hook_read)"
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
[ -f "$root/.claude/fix-mode" ] || exit 0
case "$HOOK_FILE" in
  "$root"/tests/*|tests/*|./tests/*)
    echo "버그 픽스 모드: 실패하는 테스트가 버그의 증명이므로 테스트($HOOK_FILE)를 고치지 말고 코드를 고칠 것. 테스트 자체가 틀렸다면 make fix-end 후 별도 커밋으로." >&2
    exit 2;;
esac
exit 0
