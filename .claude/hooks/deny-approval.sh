#!/usr/bin/env bash
# PreToolUse(Bash): 에이전트의 git commit 이 승인 표시를 쓰지 못하게 한다(r3 §5.1-2). exit 2 = 차단.
#   - 명령 문자열에 git commit 과 Approved-by(대소문자 무시)가 함께 있으면 차단한다. 승인 트레일러는 승인자만 쓴다.
#   - 명령 문자열에 git commit 과 approve:(대소문자 무시)가 함께 있으면 차단한다. approve: T<n> 빈 커밋도 승인자만 한다.
# 한계: 훅은 명령 문자열만 본다. -F <파일>·-C/-c <커밋>(메시지 재사용)·편집기로 쓴 메시지의 내용은 보지 못한다.
#       같은 계정에서 돌아 위조를 기계로 완전히 막을 수 없다. 그 길로 쓰는 것도 agent.md "하지 않는 것" 위반이다.
set -euo pipefail
. "$(dirname "$0")/_json.sh"; eval "$(hook_read)"
cmd="${HOOK_CMD:-}"
# git 과 commit 사이에는 전역 옵션(-c 키=값 · -C 경로 · --no-pager 등)만 올 수 있다. commit-tree 같은 다른 하위 명령은 대상이 아니다.
GIT_COMMIT='(^|[^[:alnum:]_.-])git([[:space:]]+-[cC][[:space:]]+[^[:space:]]+|[[:space:]]+--[[:alnum:]-]+(=[^[:space:]]+)?)*[[:space:]]+commit([[:space:]]|$)'
grep -Eq "$GIT_COMMIT" <<<"$cmd" || exit 0
LIMIT="이 훅은 명령 문자열만 본다. -F 파일·메시지 재사용으로 피해 가도 같은 위반이다(agent.md 하지 않는 것)."
if grep -Eiq 'approved-by' <<<"$cmd"; then
  echo "승인 트레일러는 승인자만 쓴다(r3 §5.1-2). 에이전트 커밋 메시지에 Approved-by 를 넣지 말 것. $LIMIT" >&2
  exit 2
fi
if grep -Eiq 'approve[[:space:]]*:' <<<"$cmd"; then
  echo "승인 트레일러는 승인자만 쓴다(r3 §5.1-2). approve: 커밋은 승인자가 한다 — 에이전트 커밋 제목은 plan: T<n> <slug> 또는 T<n>: <요약>. $LIMIT" >&2
  exit 2
fi
exit 0
