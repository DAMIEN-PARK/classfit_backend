#!/usr/bin/env bash
# PreToolUse(Bash): 운영 배포 명령은 RELEASE_APPROVAL=<이름> 없이는 차단한다. scripts/deploy.sh 가 같은 검사를 한 번 더 한다.
# ClassFit 은 아직 배포 명령(scripts/deploy.sh)이 없다. 지금은 test_hooks.sh 시험만 통과하는 빈 차단기다(r3 부록 E2).
# 배포가 생기면(SDLC 5단계) scripts/deploy.sh 에 같은 RELEASE_APPROVAL 검사를 넣는다.
set -u
. "$(dirname "$0")/_json.sh"; eval "$(hook_read)"
if printf '%s' "$HOOK_CMD" | grep -Eq 'scripts/deploy\.sh|docker compose[^|;&]*--profile[= ]prod'; then
  if [ -z "${RELEASE_APPROVAL:-}" ]; then
    echo "운영 배포는 릴리스 승인이 필요. 승인자가 RELEASE_APPROVAL=<이름> 을 두고 다시 실행할 것(결정은 deploy_log 에 남는다). 롤백은 scripts/deploy.sh --rollback" >&2
    exit 2
  fi
fi
exit 0
