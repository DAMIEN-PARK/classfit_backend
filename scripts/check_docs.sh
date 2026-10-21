#!/usr/bin/env bash
# 문서 구조 검사(r3 §6 E-7·E-9 · 부록 E4·E10, T0b 계획 D4). 위반마다 "위반 <어디> <이유>" 를 찍고 exit 1, 없으면 마지막 줄 "docs check: OK".
#   ① docs/process/spec.md 1절 정본 색인: 위치=저장소 행의 경로(파일 칸의 첫 백틱 글자, 저장소 루트 기준)가 실제로 있다.
#   ② 같은 색인의 위치=외부 행: sha256 칸(백틱 안 64자)이 그 파일의 sha256 과 같다. CLASSFIT_REQUIRE_EXTERNAL=1 일 때만 잰다.
#      아니면 "외부 정본 검사 건너뜀" 을 찍고 넘어간다. 외부 파일(기획/·시안/)은 미추적이라 CI 체크아웃에 없다(r3 N8).
#   ③ spec.md 2절 정책 대조표: "어디에 코드로" 칸이 빈칸·-·— 가 아니다.
#   ④ Design 부록 A 규칙 ↔ 시험 이름 대응표: master first-parent 에 `merge: T<n>` 이 있는 T 의 행만 본다.
#      시험 이름마다 tests/ 의 .py 에 `def <이름>(` 이 있어야 한다. 이름이 _ 로 끝나면 접두(`def <이름>…(`)다.
# 표는 백틱 글자를 읽는다. okf link 가 경로를 링크로 감싸도 백틱 글자는 링크 글 안에 남으므로 결과가 같다(OKF §8-11).
# 표·열을 못 찾으면 위반이다(조용히 통과하지 않는다). 읽는 모양의 정본은 spec.md 4절 6번이다.
# exit 0 통과 · 1 위반 · 2 못 쟀다(git 저장소가 아니거나 master 참조가 없다). pre-push 는 2 를 경고만 한다(check_task_order 와 같은 정책).
# 문서를 못 읽는 것(awk·shasum 실패)은 "못 쟀다" 가 아니라 위반이다. set -e 로 그 rc 가 그대로 새어 2 와 섞이지 않게 묶는다(T0b 리뷰 nit 3).
# macOS 기본 bash 3.2 에서 돈다(연관 배열·mapfile·${v,,} 를 쓰지 않는다).
set -euo pipefail
set -f   # 시험 이름을 낱말로 나눌 때 * 같은 글자가 파일 이름으로 펼쳐지지 않게

if ! top=$(git rev-parse --show-toplevel 2>/dev/null); then
  echo "못 쟀다: git 저장소가 아니다"; exit 2
fi
cd "$top"

SPEC=docs/process/spec.md
DESIGN=docs/process/2026-10-21-phase1-backend-design.md
EMPTY=__EMPTY__
violations=0

violate() {
  echo "위반 $1 $2"
  violations=$((violations + 1))
}

# master 참조: 로컬 master, 없으면(CI 체크아웃) origin/master — check_task_order.sh 와 같은 순서
master=""
for ref in master origin/master; do
  if git rev-parse --verify -q "$ref^{commit}" >/dev/null; then master=$ref; break; fi
done
if [ -z "$master" ]; then echo "못 쟀다: master 참조가 없다(master · origin/master)"; exit 2; fi

# table_rows <파일> <절 머리 글자> <열 지정>
#   <절 머리 글자> 로 시작하는 '# '·'## ' 줄 아래, 다음 '# '·'## ' 줄 전까지에서 첫 표를 읽는다.
#   <열 지정> 은 "열이름:모드,…". 열 이름은 머리 행 칸의 앞부분과 맞춘다. 모드 raw = 칸 글자 · first = 첫 백틱 글자 · all = 백틱 글자 전부(빈칸으로 잇기).
#   데이터 행마다 "줄번호<TAB>값<TAB>값…" 을 찍는다. 빈 값은 __EMPTY__.
#   표가 없으면 "__NOTABLE__", 열이 없으면 "__NOCOL__<TAB>열이름".
table_rows() {
  awk -v head="$2" -v spec="$3" -v empty="$EMPTY" '
    function trim(s) { gsub(/^[ \t]+/, "", s); gsub(/[ \t]+$/, "", s); return s }
    function split_cells(line, arr,   m, k) {
      line = trim(line); sub(/^\|/, "", line); sub(/\|$/, "", line)
      m = split(line, arr, "|")
      for (k = 1; k <= m; k++) arr[k] = trim(arr[k])
      return m
    }
    function ticks(s, all,   out, t) {
      out = ""
      while (match(s, /`[^`]+`/)) {
        t = substr(s, RSTART + 1, RLENGTH - 2)
        out = (out == "") ? t : out " " t
        if (!all) break
        s = substr(s, RSTART + RLENGTH)
      }
      return out
    }
    BEGIN {
      n = split(spec, want, ",")
      for (i = 1; i <= n; i++) { split(want[i], kv, ":"); wname[i] = kv[1]; wmode[i] = kv[2]; widx[i] = 0 }
      insec = 0; intable = 0; done = 0
    }
    done { next }
    /^# / || /^## / {
      if (insec) { done = 1; next }
      if (index($0, head) == 1) insec = 1
      next
    }
    insec && /^\|/ {
      if (!intable) {
        intable = 1
        nh = split_cells($0, h)
        for (i = 1; i <= n; i++)
          for (j = 1; j <= nh; j++)
            if (widx[i] == 0 && index(h[j], wname[i]) == 1) widx[i] = j
        bad = 0
        for (i = 1; i <= n; i++) if (widx[i] == 0) { print "__NOCOL__\t" wname[i]; bad = 1 }
        if (bad) done = 1
        sep = 1
        next
      }
      # 머리 바로 다음 줄만 구분 행(|---|)으로 본다. 데이터 행이 "-" 뿐이어도 건너뛰지 않는다.
      if (sep) { sep = 0; if ($0 ~ /^\|[ \t:|-]*-[ \t:|-]*$/) next }
      nc = split_cells($0, c)
      out = NR
      for (i = 1; i <= n; i++) {
        v = (widx[i] <= nc) ? c[widx[i]] : ""
        if (wmode[i] == "first") v = ticks(v, 0)
        else if (wmode[i] == "all") v = ticks(v, 1)
        if (v == "") v = empty
        out = out "\t" v
      }
      print out
      next
    }
    insec && intable { done = 1 }
    END { if (!intable) print "__NOTABLE__" }
  ' "$1"
}

# 표 읽기 결과의 머리 표시(__NOTABLE__·__NOCOL__)를 위반으로 바꾼다. 표가 멀쩡하면 0.
table_ok() {
  local where=$1 rows=$2 line rc=0
  while IFS= read -r line; do
    case "$line" in
      __NOTABLE__) violate "$where" "표를 못 찾았다"; rc=1 ;;
      __NOCOL__*) violate "$where" "머리 행에 '${line#__NOCOL__?}' 열이 없다"; rc=1 ;;
    esac
  done <<<"$rows"
  if [ "$rc" -eq 0 ] && [ -z "$rows" ]; then violate "$where" "표에 행이 없다"; rc=1; fi
  return "$rc"
}

sha_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else sha256sum "$1" | cut -d' ' -f1
  fi
}

for f in "$SPEC" "$DESIGN"; do
  [ -f "$f" ] || violate "$f" "파일이 없다"
done

# ①② spec 1절 정본 색인
if [ -f "$SPEC" ]; then
  rrc=0; rows=$(table_rows "$SPEC" "## 1. " "영역:raw,위치:raw,파일:first,sha256:first") || rrc=$?
  if [ "$rrc" -ne 0 ]; then violate "$SPEC 1절" "표를 읽지 못했다(awk rc $rrc)"
  elif table_ok "$SPEC 1절" "$rows"; then
    repo_n=0; ext_n=0; ext_checked=0
    while IFS=$'\t' read -r ln area loc path sha; do
      where="$SPEC:$ln"
      case "$loc" in
        저장소)
          repo_n=$((repo_n + 1))
          if [ "$path" = "$EMPTY" ]; then violate "$where" "($area) 파일 칸에 백틱 경로가 없다"
          elif [ ! -e "$path" ]; then violate "$where" "($area) 색인 경로가 없다: $path"
          fi
          ;;
        외부)
          ext_n=$((ext_n + 1))
          if [ "${CLASSFIT_REQUIRE_EXTERNAL:-}" = "1" ]; then
            ext_checked=$((ext_checked + 1))
            if [ "$path" = "$EMPTY" ]; then violate "$where" "($area) 파일 칸에 백틱 경로가 없다"
            elif ! [[ $sha =~ ^[0-9a-f]{64}$ ]]; then violate "$where" "($area) sha256 칸이 백틱 안 64자 소문자 16진수가 아니다"
            elif [ ! -f "$path" ]; then violate "$where" "($area) 외부 정본이 없다: $path"
            elif ! got=$(sha_of "$path"); then violate "$where" "($area) 외부 정본을 읽지 못했다: $path"
            elif [ "$got" != "$sha" ]; then violate "$where" "($area) sha256 이 다르다: $path 색인 ${sha:0:16}… 실제 ${got:0:16}…"
            fi
          fi
          ;;
        *) violate "$where" "($area) 위치 칸은 '저장소' 또는 '외부' 여야 한다: $loc" ;;
      esac
    done <<<"$rows"
    echo "① 색인 저장소 경로 ${repo_n}개 검사"
    if [ "${CLASSFIT_REQUIRE_EXTERNAL:-}" = "1" ]; then
      echo "② 외부 정본 ${ext_checked}개 sha256 대조"
    else
      echo "외부 정본 검사 건너뜀 (외부 ${ext_n}행, CLASSFIT_REQUIRE_EXTERNAL=1 일 때만 잰다)"
    fi
  fi
fi

# ③ spec 2절 정책 대조표
if [ -f "$SPEC" ]; then
  rrc=0; rows=$(table_rows "$SPEC" "## 2. " "#:raw,어디에 코드로:raw") || rrc=$?
  if [ "$rrc" -ne 0 ]; then violate "$SPEC 2절" "표를 읽지 못했다(awk rc $rrc)"
  elif table_ok "$SPEC 2절" "$rows"; then
    pol_n=0
    while IFS=$'\t' read -r ln num cell; do
      pol_n=$((pol_n + 1))
      case "$cell" in
        "$EMPTY" | "-" | "—" | "–") violate "$SPEC:$ln" "대조표 #$num '어디에 코드로' 칸이 비었다: $cell" ;;
      esac
    done <<<"$rows"
    echo "③ 대조표 ${pol_n}행 검사"
  fi
fi

# ④ Design 부록 A 대응표 — 병합된 T 의 행만
merged=$(git log --first-parent --format=%s "$master" | sed -nE 's/^merge: (T[0-9]+[a-z]?) .*$/\1/p' | sort -u | tr '\n' ' ')
merged=" ${merged}"
if [ -f "$DESIGN" ]; then
  rrc=0; rows=$(table_rows "$DESIGN" "## 부록 A." "T:raw,시험 이름:all") || rrc=$?
  if [ "$rrc" -ne 0 ]; then violate "$DESIGN 부록 A" "표를 읽지 못했다(awk rc $rrc)"
  elif table_ok "$DESIGN 부록 A" "$rows"; then
    all_n=0; target_n=0
    while IFS=$'\t' read -r ln tid names; do
      all_n=$((all_n + 1))
      where="$DESIGN:$ln"
      if ! [[ $tid =~ ^T[0-9]+[a-z]?$ ]]; then violate "$where" "T 칸은 태스크 하나(T<n>)여야 한다: $tid"; continue; fi
      if [ "$names" = "$EMPTY" ]; then violate "$where" "$tid 행에 시험 이름(백틱)이 없다"; continue; fi
      case "$merged" in *" $tid "*) ;; *) continue ;; esac
      target_n=$((target_n + 1))
      for name in $names; do
        if ! [[ $name =~ ^test_[A-Za-z0-9_]*$ ]]; then violate "$where" "$tid 시험 이름 꼴이 아니다: $name"; continue; fi
        case "$name" in
          *_) pat="def ${name}[A-Za-z0-9_]*\\(" ;;
          *) pat="def ${name}\\(" ;;
        esac
        grep -rqE --include='*.py' "$pat" tests 2>/dev/null || violate "$where" "$tid 시험이 tests/ 에 없다: $name"
      done
    done <<<"$rows"
    echo "④ 병합된 T:${merged% } · 대응표 ${all_n}행 중 대상 ${target_n}행"
  fi
fi

if [ "$violations" -gt 0 ]; then
  echo "docs check: FAIL (위반 ${violations}건)"
  exit 1
fi
echo "docs check: OK"
