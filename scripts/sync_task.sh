#!/usr/bin/env bash
# 태스크 가지에 master 를 들인다(r3 §5.1-4 · 부록 E11·J R1). 에이전트가 써도 되는 유일한 병합 길이다(settings allow).
# usage: bash scripts/sync_task.sh      (태스크 가지 T<n>-<slug> 위에서)
# exit 0 병합(또는 이미 최신) · 2 master·분리된 HEAD·가지 이름 규약 밖 · 3 추적 파일 미커밋 변경
#      그 밖은 git merge 의 종료 코드다. 충돌이면 손으로 풀고 `git commit` 하면 제목 `sync: T<n> …` 이 그대로 쓰인다.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

branch=$(git symbolic-ref --short -q HEAD || true)
if [ "$branch" = master ]; then
  echo "sync_task: master 에서는 쓰지 않는다. 태스크 가지(T<n>-<slug>)에서 돌린다." >&2
  exit 2
fi
if [ -z "$branch" ]; then
  echo "sync_task: 분리된 HEAD 에서는 쓰지 않는다. 태스크 가지(T<n>-<slug>)에서 돌린다." >&2
  exit 2
fi
re='^(T[0-9]+[a-z]?)-.+$'
if ! [[ $branch =~ $re ]]; then
  echo "sync_task: 가지 이름이 T<n>-<slug> 꼴이 아니다: $branch" >&2
  exit 2
fi
tid=${BASH_REMATCH[1]}

dirty=$(git status --porcelain --untracked-files=no)
if [ -n "$dirty" ]; then
  echo "sync_task: 추적 파일에 미커밋 변경이 있다. 내 변경은 파일을 지정해 먼저 커밋하고, 사용자 미커밋 변경(alembic.ini 등)은 건드리지 않는다." >&2
  printf '%s\n' "$dirty" >&2
  exit 3
fi

git merge --no-ff master -m "sync: $tid master → $branch"
