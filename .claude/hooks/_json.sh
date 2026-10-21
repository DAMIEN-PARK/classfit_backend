#!/usr/bin/env bash
# 훅 공통: stdin의 Claude Code 훅 JSON을 셸 변수로 푼다.
# usage: . "$(dirname "$0")/_json.sh"; eval "$(hook_read)"  -> HOOK_TOOL HOOK_FILE HOOK_CMD HOOK_TEXT
# 주의: 파이썬 코드는 -c 로 넘긴다(heredoc으로 넘기면 stdin의 JSON을 잃는다).
hook_read() {
python3 -c '
import json, sys, shlex
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
ti = d.get("tool_input") or {}
text = ti.get("new_string") or ti.get("content") or ""
if isinstance(ti.get("edits"), list):
    text = "\n".join(e.get("new_string", "") for e in ti["edits"])
out = {
    "HOOK_TOOL": d.get("tool_name", ""),
    "HOOK_FILE": ti.get("file_path", ""),
    "HOOK_CMD": ti.get("command", ""),
    "HOOK_TEXT": text,
}
for k, v in out.items():
    print(f"{k}={shlex.quote(str(v))}")
'
}
