#!/usr/bin/env bash
# 비밀이 저장소에 들어오는지 본다.
# git 이 있으면 추적 + 미추적(ignore 제외) 파일을 NUL 구분으로 받는다(한글 경로도 그대로). 기획·시안은 제외.
cd "$(dirname "$0")/.." || exit 2
fail=0
pat='(-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]{10,}|postgres(ql)?(\+[a-z0-9]+)?://[^:/@[:space:]]+:[^@[:space:]]+@)'
# 로컬 개발·CI 의 더미 비밀번호(…@localhost:… / …@127.0.0.1:…)만 예외. 호스트 이름이 localhost 로 시작하는 원격은 예외가 아니다.
allow='@(localhost|127\.0\.0\.1)(:|/|$)'

list_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -c core.quotePath=false ls-files -z -- . ':!기획' ':!시안'
    git -c core.quotePath=false ls-files -z --others --exclude-standard -- . ':!기획' ':!시안'
  else
    find . \( -path './.venv*' -o -path './.git' -o -path './기획' -o -path './시안' -o -path './.omc' \
              -o -name '__pycache__' -o -name '.*_cache' \) -prune -o \
         -type f ! -name '.env' ! -name '.env.*' -print0
  fi
}

hits=$(list_files | xargs -0 grep -nHIE --exclude='check_secrets.sh' "$pat" 2>/dev/null | grep -vE "$allow")
if [ -n "$hits" ]; then
  echo "$hits"; echo "SECRETS: 비밀로 보이는 문자열"; fail=1
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  tracked=$(git ls-files -- '.env' '.env.*' ':!.env.example')
  if [ -n "$tracked" ]; then echo "SECRETS: 환경 파일이 git 에 추적됩니다: $tracked"; fail=1; fi
fi
exit $fail
