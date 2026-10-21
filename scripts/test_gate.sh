#!/usr/bin/env bash
# E-6 gate 회귀 시험: ruff(TID251)·gate.sh·hook(deny-deps.sh) 세 층이 금지 줄을 실제로 막고, 허용할 것은 통과시키는지 잰다.
# 원본 작업 트리는 건드리지 않는다 — 추적 파일의 "작업 트리 내용"을 임시 사본(.git 없음)에 복사해 넣고 빼며 잰다.
# 사본에 .git 이 없으므로 check_secrets.sh 는 find 갈래를 탄다. .venv 는 복사하지 않고 원본의 PYTHON·RUFF 를 쓴다.
# 층마다 그 층 하나로 막히는지 따로 본다. "ruff 또는 gate" 로 합치면 한 층이 죽어도 녹색이다(T0b, T0a 리뷰 nit 4).
#   음성 8 — ruff 2: ① import asyncpg ② import langchain_openai → TID251
#            gate 4: ③ asyncpg 행 ④ langchain-openai==0.2 행 ⑤ langchain_openai==0.2 행 → 금지 패키지
#                    ⑥ import langchain_foo → langchain_* import (ruff 목록 밖이라 ruff 는 통과해야 한다)
#            hook 2: ⑦ Write import asyncpg ⑧ Edit requirements.in langchain-openai==0.2 → deny-deps exit 2
#   양성 3 — ⑨ 깨끗한 사본이 gate·ruff 통과 ⑩ langchain-core==0.3 행 + import langchain_core 가 gate·ruff 통과
#            ⑪ Edit requirements.in langchain-core==0.3 · Write import langchain_core → deny-deps 둘 다 exit 0
# ⚠️ 양성 ⑨·⑩ 은 작업 트리 내용을 그대로 쓰므로, 추적 파일에 미커밋 위반(예: alembic.ini 에 DB 자격)이 있으면
#    gate 와 같이 빨갛다. 그 위반을 고치기 전까지는 원본 트리에서 녹색이 될 수 없다(그 경우 `make gate` 도 실패).
# 출력 마지막 줄: "음성 8/8 OK · 양성 3/3 OK" 이면 exit 0, 아니면 "음성 n/8 · 양성 m/3" + 틀린 사례, exit 1.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
PYTHON="${PYTHON:-$root/.venv/bin/python}"
RUFF="${RUFF:-$root/.venv/bin/ruff}"
[ -x "$PYTHON" ] || { echo "test_gate: PYTHON 없음 ($PYTHON) — make venv install"; exit 1; }
[ -x "$RUFF" ] || { echo "test_gate: RUFF 없음 ($RUFF) — make install"; exit 1; }

work="$(mktemp -d "${TMPDIR:-/tmp}/classfit-test-gate.XXXXXX")"
trap 'rm -rf "$work"' EXIT
copy="$work/repo"
logs="$work/logs"
mkdir -p "$copy" "$logs"

# 추적 파일만, 작업 트리 내용 그대로. 작업 트리에서 지워진 추적 파일은 건너뛴다.
git -c core.quotePath=false ls-files -z | while IFS= read -r -d '' f; do
  if [ -e "$f" ] || [ -L "$f" ]; then printf '%s\0' "$f"; fi
done | tar --null -T - -cf - | tar -xf - -C "$copy"

probe="src/classfit/service/_t.py"
req="requirements.in"
mkdir -p "$copy/$(dirname "$probe")"
cp "$copy/$req" "$work/requirements.in.orig"
[ -f "$copy/.claude/hooks/deny-deps.sh" ] || { echo "test_gate: 사본에 .claude/hooks/deny-deps.sh 없음"; exit 1; }

# 사본 위의 git 탐색을 사본에서 멈춘다(TMPDIR 이 어떤 저장소 안이어도 check_secrets 가 find 갈래를 타도록)
run_gate() {
  (cd "$copy" && GIT_CEILING_DIRECTORIES="$work" PYTHON="$PYTHON" bash scripts/gate.sh) >"$logs/$1.gate" 2>&1
}
run_ruff() {
  (cd "$copy" && "$RUFF" check --no-cache .) >"$logs/$1.ruff" 2>&1
}
run_hook() {  # 로그 이름 · 훅 JSON. 사본의 deny-deps.sh 에 Claude Code 훅 JSON 을 stdin 으로 넣는다(exit 2 = 차단)
  printf '%s' "$2" | (cd "$copy" && CLAUDE_PROJECT_DIR="$copy" bash .claude/hooks/deny-deps.sh) >"$logs/$1.hook" 2>&1
}
add_req() {
  if [ -s "$copy/$req" ] && [ -n "$(tail -c1 "$copy/$req")" ]; then echo >>"$copy/$req"; fi
  printf '%s\n' "$1" >>"$copy/$req"
}
reset_copy() {
  rm -f "$copy/$probe"
  cp "$work/requirements.in.orig" "$copy/$req"
}
show_log() {  # 틀린 사례의 근거. 상태는 위에서 이미 판정했다(출력 자르기가 판정을 바꾸지 않는다)
  local f
  for f in "$logs/$1".*; do
    [ -f "$f" ] || continue
    echo "  --- $(basename "$f")"
    sed -n '1,15p' "$f" | sed 's/^/  | /'
  done
}

neg_ok=0
pos_ok=0
wrong=""
pass() { echo "$1 OK  $2"; }
miss() { echo "$1 틀림  $2"; show_log "$3"; wrong="$wrong $1"; }

# ⑨ 깨끗한 사본 — 먼저 잰다. 이게 빨가면 음성 결과는 아래 메시지 대조로만 믿을 수 있다.
grc=0; run_gate p9 || grc=$?
rrc=0; run_ruff p9 || rrc=$?
if [ "$grc" -eq 0 ] && grep -q '^gate: OK$' "$logs/p9.gate" && [ "$rrc" -eq 0 ]; then
  pos_ok=$((pos_ok + 1)); pass "⑨" "깨끗한 사본: gate OK · ruff 통과"
else
  miss "⑨" "깨끗한 사본이 통과해야 함 (gate rc=$grc, ruff rc=$rrc)" p9
fi

# ①② ruff 층 — TID251 하나로 막혀야 한다
n=1
for mod in asyncpg langchain_openai; do
  case $n in 1) mark="①" ;; *) mark="②" ;; esac
  reset_copy
  printf 'import %s  # noqa: F401\n' "$mod" >"$copy/$probe"
  rrc=0; run_ruff "n$n" || rrc=$?
  if [ "$rrc" -ne 0 ] && grep -q 'TID251' "$logs/n$n.ruff"; then
    neg_ok=$((neg_ok + 1)); pass "$mark" "import $mod → ruff TID251"
  else
    miss "$mark" "import $mod 가 ruff TID251 로 막혀야 함 (ruff rc=$rrc)" "n$n"
  fi
  n=$((n + 1))
done

# ③④⑤ gate 층 — requirements 행
for line in 'asyncpg' 'langchain-openai==0.2' 'langchain_openai==0.2'; do
  case $n in 3) mark="③" ;; 4) mark="④" ;; *) mark="⑤" ;; esac
  reset_copy
  add_req "$line"
  grc=0; run_gate "n$n" || grc=$?
  if [ "$grc" -ne 0 ] && grep -q '^GATE FAIL: 금지 패키지가 requirements 에 있음' "$logs/n$n.gate"; then
    neg_ok=$((neg_ok + 1)); pass "$mark" "requirements 행 '$line' → gate"
  else
    miss "$mark" "requirements 행 '$line' 이 gate 로 막혀야 함 (gate rc=$grc)" "n$n"
  fi
  n=$((n + 1))
done

# ⑥ gate 층 전용 — ruff 목록 밖 langchain_* 는 gate 의 접두 검사만 잡는다. ruff 는 통과해야 사례가 gate 하나를 잰다.
reset_copy
printf 'import langchain_foo  # noqa: F401\n' >"$copy/$probe"
rrc=0; run_ruff n6 || rrc=$?
grc=0; run_gate n6 || grc=$?
if [ "$rrc" -eq 0 ] && [ "$grc" -ne 0 ] && grep -q '^GATE FAIL: langchain_\* import' "$logs/n6.gate"; then
  neg_ok=$((neg_ok + 1)); pass "⑥" "import langchain_foo → gate (ruff 는 통과: 목록 밖)"
else
  miss "⑥" "import langchain_foo 는 ruff 통과 · gate 차단이어야 함 (ruff rc=$rrc, gate rc=$grc)" n6
fi
reset_copy

# ⑦⑧ hook 층 — deny-deps.sh 가 편집 단계에서 exit 2 로 막는다
J7='{"tool_name":"Write","tool_input":{"file_path":"src/classfit/service/_t.py","content":"import os\nimport asyncpg\n"}}'
J8='{"tool_name":"Edit","tool_input":{"file_path":"requirements.in","old_string":"fastapi","new_string":"fastapi\nlangchain-openai==0.2\n"}}'
n=7
for j in "$J7" "$J8"; do
  case $n in 7) mark="⑦"; what="Write import asyncpg" ;; *) mark="⑧"; what="Edit requirements.in langchain-openai==0.2" ;; esac
  hrc=0; run_hook "n$n" "$j" || hrc=$?
  if [ "$hrc" -eq 2 ] && grep -q '금지 의존성' "$logs/n$n.hook"; then
    neg_ok=$((neg_ok + 1)); pass "$mark" "$what → deny-deps exit 2"
  else
    miss "$mark" "$what 가 deny-deps 로 막혀야 함 (hook rc=$hrc)" "n$n"
  fi
  n=$((n + 1))
done

# ⑩ langchain-core 행 + import langchain_core → gate·ruff 둘 다 통과
reset_copy
add_req 'langchain-core==0.3'
printf 'import langchain_core  # noqa: F401\n' >"$copy/$probe"
grc=0; run_gate p10 || grc=$?
rrc=0; run_ruff p10 || rrc=$?
if [ "$grc" -eq 0 ] && grep -q '^gate: OK$' "$logs/p10.gate" && [ "$rrc" -eq 0 ]; then
  pos_ok=$((pos_ok + 1)); pass "⑩" "langchain-core==0.3 행 + import langchain_core → gate OK · ruff 통과"
else
  miss "⑩" "langchain-core 행·import langchain_core 는 통과해야 함 (gate rc=$grc, ruff rc=$rrc)" p10
fi
reset_copy

# ⑪ hook 허용 — langchain-core 행과 langchain_core import 는 deny-deps 가 통과시킨다
J11R='{"tool_name":"Edit","tool_input":{"file_path":"requirements.in","old_string":"fastapi","new_string":"fastapi\nlangchain-core==0.3\n"}}'
J11P='{"tool_name":"Write","tool_input":{"file_path":"src/classfit/service/_t.py","content":"import langchain_core\nfrom langchain_core.messages import AIMessage\n"}}'
hrc_r=0; run_hook p11.req "$J11R" || hrc_r=$?
hrc_p=0; run_hook p11.py "$J11P" || hrc_p=$?
if [ "$hrc_r" -eq 0 ] && [ "$hrc_p" -eq 0 ]; then
  pos_ok=$((pos_ok + 1)); pass "⑪" "Edit requirements.in langchain-core==0.3 · Write import langchain_core → deny-deps exit 0"
else
  miss "⑪" "langchain-core 행·import langchain_core 는 deny-deps 가 통과시켜야 함 (rc 행=$hrc_r, import=$hrc_p)" p11
fi

if [ "$neg_ok" -eq 8 ] && [ "$pos_ok" -eq 3 ]; then
  echo "음성 8/8 OK · 양성 3/3 OK"
  exit 0
fi
echo "음성 $neg_ok/8 · 양성 $pos_ok/3 — 틀린 사례:$wrong"
exit 1
