#!/usr/bin/env bash
# OKF 밀림 막기: 정리할 것이 남아 있으면 exit 1. pre-commit · pre-push · CI 가 같은 스크립트를 쓴다.
# usage: scripts/okf/guard.sh [묶음 뿌리=docs] [설정=<뿌리>/okf.toml]
# 본문은 OKF 안내서 §7.2 원문이다. 맨 앞의 사본 대조(§7.4)만 ClassFit 이 더했다.
# set -e 는 일부러 두지 않는다(원문). 실패 분기 안의 grep·head 가 중간에 끊겨도 나머지 검사와 안내를 끝까지 찍는다.
set -uo pipefail

# 사본 대조: okf.py 는 BHQ 원본의 사본이다(수정 0). okf.py.sha256 과 다르면 도구가 어긋난 것이라 실패한다.
# 도구를 바꾸려면 원본을 다시 복사하고 같은 커밋에서 sha 파일도 고친다. 러너에 sha256sum 이 없으면 shasum 을 쓴다.
HERE="$(cd "$(dirname "$0")" && pwd)"
if command -v sha256sum >/dev/null 2>&1; then
  got=$(sha256sum "$HERE/okf.py" 2>/dev/null | cut -d' ' -f1)
else
  got=$(shasum -a 256 "$HERE/okf.py" 2>/dev/null | cut -d' ' -f1)
fi
want=$(cat "$HERE/okf.py.sha256" 2>/dev/null)
if [ -z "$got" ] || [ "$got" != "$want" ]; then
  echo "OKF: scripts/okf/okf.py 가 okf.py.sha256 과 다르다(사본이 어긋났다) → BHQ 원본을 다시 복사하거나 sha 파일을 같이 고친다"
  exit 1
fi

ROOT="${1:-docs}"; CONF="${2:-$ROOT/okf.toml}"
PY="${OKF_PYTHON:-python3}"
"$PY" -c 'import tomllib, yaml' 2>/dev/null \
  || { echo "OKF: $PY 에 PyYAML 이 없거나 3.11 미만이다 → OKF_PYTHON 에 PyYAML 있는 파이썬을 준다"; exit 1; }
OKF=("$PY" "$(dirname "$0")/okf.py" --root "$ROOT" --config "$CONF")
fail=0
out=$("${OKF[@]}" label 2>&1) || { echo "$out" | tail -3; exit 1; }
echo "$out" | grep -qE "^요약: \{'같음': [0-9]+\}$" \
  || { echo "OKF: type 이 없는 문서가 있다 → label --apply"; echo "$out" | grep -vE '^ +같음' | head -8; fail=1; }
out=$("${OKF[@]}" link 2>&1) || { echo "$out" | tail -3; exit 1; }
echo "$out" | grep -q '바뀌는 문서 0개' \
  || { echo "OKF: 링크로 안 감싼 참조가 있다 → link --apply 뒤 git diff 로 새 링크의 문장을 읽는다"; echo "$out" | head -4; fail=1; }
out=$("${OKF[@]}" index 2>&1) || { echo "$out" | tail -3; exit 1; }
echo "$out" | grep -q '목차 0개 만들 것' \
  || { echo "OKF: 목차가 낡았다 → index --apply"; echo "$out" | grep -v '같음' | head -6; fail=1; }
"${OKF[@]}" check --strict >/dev/null 2>&1 \
  || { echo "OKF: check --strict 실패"; "${OKF[@]}" check --strict 2>&1 | tail -5; fail=1; }
[ "$fail" = 0 ] && echo "OKF guard OK"
exit "$fail"
