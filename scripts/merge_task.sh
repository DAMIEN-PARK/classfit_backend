#!/usr/bin/env bash
# 태스크 가지를 master 에 병합한다(r3 §5.1-4 · 부록 J R2). 승인자 전용 — Claude 밖 터미널에서 돌린다.
# usage: bash scripts/merge_task.sh T<n>-<slug>
#   master 에 이 스크립트가 아직 없으면(T0a): bash <(git show T<n>-<slug>:scripts/merge_task.sh) T<n>-<slug>
# 순서: ① 추적 파일 미커밋 변경 0 ② 대화형 터미널(stdin TTY)에서 에이전트 세션 정지 확인 [y/N]
#       ③ check_task_order.sh·task_order_base 는 master 판 우선(master 에 없을 때만 가지 사본)으로 그 가지를 잼
#       ④ master 로 전환(끝나면 trap 으로 원래 가지 복귀) ⑤ git merge --no-ff --no-commit
#       ⑥ make verify(출력은 파일, 종료 코드 따로, 파이프 없음)
#       ⑦ 통과면 `merge: T<n> <slug>` 커밋(본문 "make verify: exit 0" + 끝 20줄 + Approved-by), 실패면 git merge --abort
# 승인자 이름은 APPROVER 로 덮어쓴다(기본 DAMIEN-PARK).
# exit 0 병합 · 1 검사·충돌·verify 실패(master 는 그대로) · 2 사용법
# 경로는 $0 대신 git 으로 잡는다(사본 실행 대비). 본문은 main 함수로 감싸 가지 전환 중 이 파일이 바뀌어도 이미 다 읽은 뒤다.
set -euo pipefail

orig=""
tmp_check=""
out=""
msg=""

cleanup() {
  local rc=$?
  if git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    git merge --abort || echo "git merge --abort 실패 — 손으로 정리한다" >&2
  fi
  if [ -n "$orig" ]; then
    local cur
    cur=$(git symbolic-ref --short -q HEAD || git rev-parse HEAD)
    if [ "$cur" != "$orig" ]; then
      git checkout -q "$orig" || echo "원래 가지($orig)로 돌아가지 못했다" >&2
    fi
  fi
  rm -f "$tmp_check" "$out" "$msg"
  exit "$rc"
}

main() {
  local branch=${1:-}
  local approver=${APPROVER:-DAMIEN-PARK}
  local re='^(T[0-9]+[a-z]?)-(.+)$'
  if [ "$#" -ne 1 ] || [ -z "$branch" ]; then
    echo "usage: bash scripts/merge_task.sh T<n>-<slug>" >&2
    exit 2
  fi
  if ! [[ $branch =~ $re ]]; then
    echo "가지 이름이 T<n>-<slug> 꼴이 아니다: $branch" >&2
    exit 2
  fi
  local tid=${BASH_REMATCH[1]}
  local slug=${BASH_REMATCH[2]}

  cd "$(git rev-parse --show-toplevel)"
  if ! git rev-parse --verify -q "refs/heads/$branch" >/dev/null; then echo "가지가 없다: $branch" >&2; exit 2; fi
  if ! git rev-parse --verify -q refs/heads/master >/dev/null; then echo "master 가지가 없다" >&2; exit 2; fi
  if git rev-parse -q --verify MERGE_HEAD >/dev/null; then
    echo "중단: 진행 중인 병합이 있다. 먼저 정리한다(git merge --abort)." >&2
    exit 1
  fi

  # ① 추적 파일 미커밋 변경 0 (미추적 기획/·시안/ 은 늘 있으므로 제외)
  local dirty
  dirty=$(git status --porcelain --untracked-files=no)
  if [ -n "$dirty" ]; then
    echo "중단: 추적 파일에 미커밋 변경이 있다. alembic.ini 같은 미커밋 변경을 먼저 정리한다." >&2
    printf '%s\n' "$dirty" >&2
    exit 1
  fi

  # ② 작업 트리는 하나다. 병합하는 동안 에이전트 세션은 멈춘다.
  local ans=""
  [ -t 0 ] || { echo "merge_task.sh 는 대화형 터미널에서만 돈다(stdin 이 TTY 아님)" >&2; exit 1; }
  read -r -p "에이전트 세션을 모두 멈췄는가? [y/N] " ans || ans=""
  case "$ans" in
    y | Y) ;;
    *) echo "중단: 에이전트 세션을 멈춘 뒤 다시 돌린다." >&2; exit 1 ;;
  esac

  trap cleanup EXIT
  tmp_check=$(mktemp)
  out=$(mktemp)
  msg=$(mktemp)

  # ③ 검사기·base 는 master 판 우선 — 가지가 검사기를 약하게 고쳐 자기를 통과시키는 길을 막는다. master 에 없을 때(T0a)만 가지 사본.
  local src=$branch
  if git cat-file -e "master:scripts/check_task_order.sh" 2>/dev/null; then src=master; fi
  if ! git show "$src:scripts/check_task_order.sh" >"$tmp_check"; then
    echo "중단: $src 의 scripts/check_task_order.sh 를 읽지 못했다." >&2
    exit 1
  fi
  if git cat-file -e "master:scripts/task_order_base" 2>/dev/null \
     && [ "$(git show master:scripts/task_order_base | tr -d '[:space:]')" != "$(git show "$branch:scripts/task_order_base" 2>/dev/null | tr -d '[:space:]')" ]; then
    echo "중단: $branch 의 scripts/task_order_base 가 master 판과 다르다(가지가 지웠거나 바꿨다)." >&2
    exit 1
  fi
  if ! bash "$tmp_check" "$branch"; then
    echo "중단: $branch 커밋 순서 검사 실패." >&2
    exit 1
  fi

  # ④ master 로 전환 (원래 가지는 trap 이 복귀)
  orig=$(git symbolic-ref --short -q HEAD || git rev-parse HEAD)
  if [ "$orig" != master ]; then git checkout -q master; fi

  # ⑤ 병합 (커밋은 verify 뒤)
  if ! git merge --no-ff --no-commit "$branch"; then
    echo "중단: 병합 충돌. 가지에서 bash scripts/sync_task.sh 로 master 를 들여 충돌을 푼 뒤 다시 돌린다." >&2
    exit 1
  fi
  if ! git rev-parse -q --verify MERGE_HEAD >/dev/null; then
    echo "중단: 병합할 것이 없다($branch 는 이미 master 에 들어 있다)." >&2
    exit 1
  fi

  # ⑥ 병합 결과 트리에서 verify — 출력은 파일로, 종료 코드는 따로
  local rc=0
  make verify >"$out" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "make verify 실패(exit $rc). 병합을 취소한다. 출력 끝 40줄:" >&2
    tail -n 40 "$out" >&2
    git merge --abort
    exit 1
  fi

  # ⑦ 병합 커밋
  {
    printf 'merge: %s %s\n\n' "$tid" "$slug"
    printf 'make verify: exit 0 (병합 결과 트리) — 출력 끝 20줄\n'
    tail -n 20 "$out"
    printf '\nApproved-by: %s\n' "$approver"
  } >"$msg"
  git commit -q -F "$msg"
  git log -1 --format='병합 완료: %h %s' master
}

# 한 줄로 둔다: bash 는 이 줄까지 읽고 main 을 돈다. exit 가 같은 줄이라 전환 뒤 바뀐 파일을 더 읽지 않는다.
main "$@"; exit 0
