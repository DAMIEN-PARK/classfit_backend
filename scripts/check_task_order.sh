#!/usr/bin/env bash
# 커밋 순서 검사(r3 §5.1 · §6 E-1 · 부록 E11·J). 위반마다 "위반 <해시> <이유>" 를 찍고 exit 1, 없으면 마지막 줄 "task order: OK".
# usage: bash scripts/check_task_order.sh [<가지>]
#   master: scripts/task_order_base 다음 first-parent 커밋이 전부 `merge: T<n> <slug>` 병합 커밋이고,
#           본문에 merge_task.sh 가 쓰는 "make verify: exit 0" 꼬리 표시와 `Approved-by:` 가 있다.
#   가지:   인자 가지(없으면 현재 가지. master·분리된 HEAD 면 건너뜀)의 master..가지 커밋이
#           `plan: T<n> <slug>`(첫 커밋) → `approve: T<n>`(빈 커밋, Approved-by:) → `T<n>: …` 순서다.
#           `sync: T<n> …` 병합 커밋은 plan 뒤 어디든 허용한다. Approved-by 는 approve 커밋에만 있어야 한다.
# exit 0 통과 · 1 위반 · 2 못 쟀다(master 참조·base 커밋·인자 가지가 이 사본에 없음)
# merge_task.sh 가 `git show` 로 받은 사본을 임시 파일에서 돌리므로 경로는 $0 이 아니라 git 으로 잡는다.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

TID_RE='T[0-9]+[a-z]?'
SLUG_RE='[A-Za-z0-9][A-Za-z0-9._-]*'
violations=0

violate() {
  local where=$1
  if [ "$where" != "-" ]; then where=$(git rev-parse --short "$where"); fi
  echo "위반 $where $2"
  violations=$((violations + 1))
}

has_approved_by() { grep -qiE '^approved-by:' <<<"$1"; }
is_merge() { git rev-parse --verify -q "$1^2" >/dev/null; }

# master 참조: 로컬 master, 없으면(CI 체크아웃) origin/master
master=""
for ref in master origin/master; do
  if git rev-parse --verify -q "$ref^{commit}" >/dev/null; then master=$ref; break; fi
done
if [ -z "$master" ]; then echo "못 쟀다: master 참조가 없다(master · origin/master)"; exit 2; fi

target=${1:-}
if [ -n "$target" ]; then
  if ! git rev-parse --verify -q "$target^{commit}" >/dev/null; then echo "못 쟀다: 가지가 없다: $target"; exit 2; fi
else
  # exit 1 = 분리된 HEAD(CI 의 PR 체크아웃)라 가지 검사를 건너뛴다. 그 밖의 실패는 못 쟀다.
  rc=0
  target=$(git symbolic-ref --short -q HEAD) || rc=$?
  if [ "$rc" -eq 1 ]; then
    target=""
  elif [ "$rc" -ne 0 ]; then
    echo "못 쟀다: 현재 가지를 읽지 못했다(git symbolic-ref exit $rc)"; exit 2
  fi
fi

# base: 검사할 가지에 커밋된 값 → master 에 커밋된 값 → 작업 트리 파일 순
base=""
for ref in "${target:-HEAD}" "$master"; do
  if raw=$(git show "$ref:scripts/task_order_base" 2>/dev/null); then
    base=$(printf '%s' "$raw" | tr -d '[:space:]'); break
  fi
done
if [ -z "$base" ] && [ -f scripts/task_order_base ]; then base=$(tr -d '[:space:]' <scripts/task_order_base); fi
if [ -z "$base" ]; then echo "위반 - scripts/task_order_base 가 없다"; echo "task order: FAIL (위반 1건)"; exit 1; fi
if ! git rev-parse --verify -q "$base^{commit}" >/dev/null; then
  echo "못 쟀다: base 커밋 $base 이 이 사본에 없다(얕은 clone 이면 fetch-depth: 0)"; exit 2
fi
if ! git merge-base --is-ancestor "$base" "$master"; then
  echo "위반 - base $base 가 $master 의 조상이 아니다(master 기록이 바뀌었다)"
  echo "task order: FAIL (위반 1건)"; exit 1
fi

# (a) master first-parent
mcount=0
for sha in $(git rev-list --first-parent "$base..$master"); do
  mcount=$((mcount + 1))
  subj=$(git log -1 --format=%s "$sha")
  body=$(git log -1 --format=%b "$sha")
  if ! grep -qE "^merge: $TID_RE $SLUG_RE\$" <<<"$subj"; then
    violate "$sha" "master: 제목이 'merge: T<n> <slug>' 가 아니다 — $subj"; continue
  fi
  is_merge "$sha" || violate "$sha" "master: 병합 커밋이 아니다(--no-ff 병합만)"
  grep -q '^make verify: exit 0' <<<"$body" || violate "$sha" "master: 본문에 make verify 꼬리가 없다"
  grep -qE '^Approved-by: [^[:space:]]' <<<"$body" || violate "$sha" "master: 본문에 Approved-by 가 없다"
done
echo "master($master): base $(git rev-parse --short "$base") 다음 first-parent ${mcount}개 검사"

# (b) 가지
if [ -z "$target" ]; then
  echo "가지 검사 건너뜀: 분리된 HEAD"
elif [ "$target" = master ] || [ "$target" = "$master" ]; then
  echo "가지 검사 건너뜀: $target"
else
  bname=${target##*/}
  re="^($TID_RE)-($SLUG_RE)\$"
  if ! [[ $bname =~ $re ]]; then
    violate - "가지 이름이 T<n>-<slug> 꼴이 아니다: $target"
  else
    tid=${BASH_REMATCH[1]}
    slug=${BASH_REMATCH[2]}
    count=0
    approved=0
    for sha in $(git rev-list --reverse --topo-order "$master..$target"); do
      count=$((count + 1))
      subj=$(git log -1 --format=%s "$sha")
      body=$(git log -1 --format=%b "$sha")
      if [ "$count" -eq 1 ]; then
        if [ "$subj" != "plan: $tid $slug" ]; then
          violate "$sha" "가지 첫 커밋이 'plan: $tid $slug' 가 아니다 — $subj"
        elif has_approved_by "$body"; then
          violate "$sha" "plan 커밋에 Approved-by 가 있다(승인자만 쓴다)"
        fi
        continue
      fi
      case "$subj" in
        "approve: $tid")
          if is_merge "$sha"; then violate "$sha" "approve 가 병합 커밋이다"; fi
          if [ "$(git rev-parse "$sha^{tree}")" != "$(git rev-parse "$sha^1^{tree}")" ]; then
            violate "$sha" "approve 커밋이 비어 있지 않다(--allow-empty 빈 커밋만)"
          fi
          grep -qE '^Approved-by: [^[:space:]]' <<<"$body" || violate "$sha" "approve 본문에 Approved-by 가 없다"
          approved=1
          ;;
        "sync: $tid" | "sync: $tid "*)
          is_merge "$sha" || violate "$sha" "sync 커밋이 병합 커밋이 아니다(sync_task.sh 로만)"
          if has_approved_by "$body"; then violate "$sha" "sync 커밋에 Approved-by 가 있다"; fi
          ;;
        "$tid: "*)
          [ "$approved" -eq 1 ] || violate "$sha" "approve: $tid 보다 앞선 구현 커밋 — $subj"
          if is_merge "$sha"; then violate "$sha" "구현 커밋이 병합 커밋이다(가지 병합은 sync_task.sh 만)"; fi
          if has_approved_by "$body"; then violate "$sha" "구현 커밋에 Approved-by 가 있다(승인자만 쓴다)"; fi
          ;;
        *)
          violate "$sha" "규약 밖 제목(plan:·approve:·$tid:·sync: 만) — $subj"
          ;;
      esac
    done
    echo "가지 $target: master..가지 커밋 ${count}개 검사"
  fi
fi

if [ "$violations" -gt 0 ]; then
  echo "task order: FAIL (위반 ${violations}건)"
  exit 1
fi
echo "task order: OK"
