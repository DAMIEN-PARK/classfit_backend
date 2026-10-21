#!/usr/bin/env bash
# E-6 gate 회귀 시험: gate.sh·ruff(TID251)가 금지 줄을 실제로 막고, 허용할 것은 통과시키는지 잰다.
# 원본 작업 트리는 건드리지 않는다 — 추적 파일의 "작업 트리 내용"을 임시 사본(.git 없음)에 복사해 넣고 빼며 잰다.
# 사본에 .git 이 없으므로 check_secrets.sh 는 find 갈래를 탄다. .venv 는 복사하지 않고 원본의 PYTHON·RUFF 를 쓴다.
#   음성 5: ① import asyncpg ② import langchain_openai ③ asyncpg 행 ④ langchain-openai==0.2 행 ⑤ langchain_openai==0.2 행
#   양성 2: ⑥ 깨끗한 사본이 gate·ruff 통과 ⑦ langchain-core==0.3 행 + import langchain_core 통과
# ⚠️ 양성 ⑥·⑦ 은 작업 트리 내용을 그대로 쓰므로, 추적 파일에 미커밋 위반(예: alembic.ini 에 DB 자격)이 있으면
#    gate 와 같이 빨갛다. 그 위반을 고치기 전까지는 원본 트리에서 녹색이 될 수 없다(그 경우 `make gate` 도 실패).
# 출력 마지막 줄: "음성 5/5 OK · 양성 2/2 OK" 이면 exit 0, 아니면 "음성 n/5 · 양성 m/2" + 틀린 사례, exit 1.
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

# 사본 위의 git 탐색을 사본에서 멈춘다(TMPDIR 이 어떤 저장소 안이어도 check_secrets 가 find 갈래를 타도록)
run_gate() {
  (cd "$copy" && GIT_CEILING_DIRECTORIES="$work" PYTHON="$PYTHON" bash scripts/gate.sh) >"$logs/$1.gate" 2>&1
}
run_ruff() {
  (cd "$copy" && "$RUFF" check --no-cache .) >"$logs/$1.ruff" 2>&1
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

# ⑥ 깨끗한 사본 — 먼저 잰다. 이게 빨가면 음성 결과는 아래 메시지 대조로만 믿을 수 있다.
grc=0; run_gate p6 || grc=$?
rrc=0; run_ruff p6 || rrc=$?
if [ "$grc" -eq 0 ] && grep -q '^gate: OK$' "$logs/p6.gate" && [ "$rrc" -eq 0 ]; then
  pos_ok=$((pos_ok + 1)); pass "⑥" "깨끗한 사본: gate OK · ruff 통과"
else
  miss "⑥" "깨끗한 사본이 통과해야 함 (gate rc=$grc, ruff rc=$rrc)" p6
fi

# ① import asyncpg → ruff TID251
reset_copy
printf 'import asyncpg  # noqa: F401\n' >"$copy/$probe"
rrc=0; run_ruff n1 || rrc=$?
if [ "$rrc" -ne 0 ] && grep -q 'TID251' "$logs/n1.ruff"; then
  neg_ok=$((neg_ok + 1)); pass "①" "import asyncpg → ruff TID251"
else
  miss "①" "import asyncpg 가 ruff TID251 로 막혀야 함 (ruff rc=$rrc)" n1
fi

# ② import langchain_openai → ruff TID251 또는 gate langchain_* 검사
reset_copy
printf 'import langchain_openai  # noqa: F401\n' >"$copy/$probe"
rrc=0; run_ruff n2 || rrc=$?
grc=0; run_gate n2 || grc=$?
by=""
if [ "$rrc" -ne 0 ] && grep -q 'TID251' "$logs/n2.ruff"; then by="ruff TID251"; fi
if [ "$grc" -ne 0 ] && grep -q '^GATE FAIL: langchain_\* import' "$logs/n2.gate"; then by="${by:+$by + }gate"; fi
if [ -n "$by" ]; then
  neg_ok=$((neg_ok + 1)); pass "②" "import langchain_openai → $by"
else
  miss "②" "import langchain_openai 가 ruff 또는 gate 로 막혀야 함 (ruff rc=$rrc, gate rc=$grc)" n2
fi

# ③④⑤ requirements 행 → gate
n=3
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

# ⑦ langchain-core 행 + import langchain_core → gate·ruff 둘 다 통과
reset_copy
add_req 'langchain-core==0.3'
printf 'import langchain_core  # noqa: F401\n' >"$copy/$probe"
grc=0; run_gate p7 || grc=$?
rrc=0; run_ruff p7 || rrc=$?
if [ "$grc" -eq 0 ] && grep -q '^gate: OK$' "$logs/p7.gate" && [ "$rrc" -eq 0 ]; then
  pos_ok=$((pos_ok + 1)); pass "⑦" "langchain-core==0.3 행 + import langchain_core → gate OK · ruff 통과"
else
  miss "⑦" "langchain-core 행·import langchain_core 는 통과해야 함 (gate rc=$grc, ruff rc=$rrc)" p7
fi
reset_copy

if [ "$neg_ok" -eq 5 ] && [ "$pos_ok" -eq 2 ]; then
  echo "음성 5/5 OK · 양성 2/2 OK"
  exit 0
fi
echo "음성 $neg_ok/5 · 양성 $pos_ok/2 — 틀린 사례:$wrong"
exit 1
