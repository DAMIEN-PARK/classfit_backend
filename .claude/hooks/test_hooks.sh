#!/usr/bin/env bash
# 훅 회귀 테스트: 샘플 stdin JSON으로 exit 코드를 검사한다. CI gates 잡과 pre-push가 실행. 전부 맞으면 "11/11 OK".
# 분배: protect-tests 3 · deny-deps 3(r3 부록 E8 목록) · deploy-gate 2 · deny-approval 3(차단 2·허용 1).
# deny-approval 의 두 차단 분기(approve: 제목 · Approved-by 트레일러)는 따로 잰다 — 한 명령에 합치면 한 분기가 죽어도 녹색이다(T0b, T0a 리뷰 nit 4).
set -u
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/.claude" "$tmp/tests" "$tmp/src"
pass=0; total=0
run() { # name hook json expected [env...]
  local name="$1" hook="$2" json="$3" want="$4"; shift 4
  total=$((total+1))
  local got
  printf '%s' "$json" | env CLAUDE_PROJECT_DIR="$tmp" "$@" bash "$here/$hook" >/dev/null 2>"$tmp/err"; got=$?
  if [ "$got" -eq "$want" ]; then pass=$((pass+1)); echo "ok   $name (exit $got)"; else echo "FAIL $name: want $want got $got — $(cat "$tmp/err")"; fi
}
J_TEST='{"tool_name":"Edit","tool_input":{"file_path":"'"$tmp"'/tests/test_x.py","old_string":"a","new_string":"b"}}'
J_SRC='{"tool_name":"Edit","tool_input":{"file_path":"'"$tmp"'/src/x.py","old_string":"a","new_string":"b"}}'
run "1 no fix-mode, tests edit allowed"   protect-tests.sh "$J_TEST" 0
touch "$tmp/.claude/fix-mode"
run "2 fix-mode, tests edit blocked"      protect-tests.sh "$J_TEST" 2
run "3 fix-mode, src edit allowed"        protect-tests.sh "$J_SRC" 0
rm -f "$tmp/.claude/fix-mode"
run "4 forbidden import blocked"          deny-deps.sh '{"tool_name":"Write","tool_input":{"file_path":"src/x.py","content":"import os\nfrom langchain_openai import ChatOpenAI\n"}}' 2
run "5 allowed import passes"             deny-deps.sh '{"tool_name":"Write","tool_input":{"file_path":"src/x.py","content":"import langchain_core\nfrom langgraph.graph import StateGraph\n"}}' 0
run "6 requirements.in forbidden blocked" deny-deps.sh '{"tool_name":"Edit","tool_input":{"file_path":"requirements.in","old_string":"fastapi","new_string":"fastapi\nlangchain_openai==0.2\n"}}' 2
run "7 deploy without approval blocked"   deploy-gate.sh '{"tool_name":"Bash","tool_input":{"command":"bash scripts/deploy.sh --sha abc123"}}' 2 env -u RELEASE_APPROVAL
run "8 deploy with approval allowed"      deploy-gate.sh '{"tool_name":"Bash","tool_input":{"command":"bash scripts/deploy.sh --sha abc123"}}' 0 RELEASE_APPROVAL=tester
run "9 approve subject only blocked"      deny-approval.sh '{"tool_name":"Bash","tool_input":{"command":"git commit --allow-empty -m \"approve: T1\""}}' 2
run "10 Approved-by trailer only blocked" deny-approval.sh '{"tool_name":"Bash","tool_input":{"command":"git commit -m \"T1: 작업\" -m \"Approved-by: X\""}}' 2
run "11 agent task commit allowed"        deny-approval.sh '{"tool_name":"Bash","tool_input":{"command":"git commit -m \"T1: 작업\""}}' 0
echo "$pass/$total OK"
[ "$pass" -eq "$total" ]
