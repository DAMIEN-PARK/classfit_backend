#!/usr/bin/env bash
# 비밀이 저장소에 들어오는지 본다.
# git 이 있으면 추적 + 미추적(ignore 제외) 파일을 NUL 구분으로 받는다(한글 경로도 그대로). 기획·시안은 제외.
# 맞으면 `file:line: <패턴 이름>` 만 찍는다. 맞은 줄 내용(비밀 값)은 찍지 않는다
# (2026-10-21 실측: 줄 내용을 찍던 판이 DB 비밀번호를 터미널에 그대로 찍었다). 허용 판정은 줄 내용으로 하고 출력만 자른다.
cd "$(dirname "$0")/.." || exit 2
fail=0
# 이름과 정규식(ERE)은 같은 순서다. 한 줄이 여러 패턴에 맞으면 패턴마다 한 줄씩 찍는다.
names=("개인 키" "AWS 액세스 키" "sk- API 키" "GitHub 토큰" "Slack 토큰" "DB URL 비밀번호")
pats=(
  '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
  'AKIA[0-9A-Z]{16}'
  'sk-[A-Za-z0-9_-]{20,}'
  'ghp_[A-Za-z0-9]{36}'
  'xox[baprs]-[A-Za-z0-9-]{10,}'
  'postgres(ql)?(\+[a-z0-9]+)?://[^:/@[:space:]]+:[^@[:space:]]+@'
)
# 로컬 개발·CI 의 더미 비밀번호(…@localhost:… / …@127.0.0.1:…)만 예외. 호스트 이름이 localhost 로 시작하는 원격은 예외가 아니다.
# 예외는 DB URL 패턴(맨 끝)에만 건다. 같은 줄에 localhost 가 있어도 다른 패턴(키·토큰)은 찍힌다(T0b 리뷰 nit 2).
allow='@(localhost|127\.0\.0\.1)(:|/|$)'
allow_idx=$((${#pats[@]} - 1))

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

# grep -nH 의 "file:line:내용" 에서 처음 나오는 ":숫자:" 로 위치와 내용을 가른다. 내용이 허용에 맞으면 버리고, 위치만 찍는다.
# 정규식·이름은 환경 변수로 넘긴다(awk -v 는 백슬래시를 풀어 정규식이 바뀐다).
hits=""
i=0
while [ "$i" -lt "${#pats[@]}" ]; do
  a=""; if [ "$i" -eq "$allow_idx" ]; then a="$allow"; fi
  h=$(list_files | xargs -0 grep -nHIE --exclude='check_secrets.sh' -e "${pats[$i]}" 2>/dev/null \
      | ALLOW="$a" NAME="${names[$i]}" awk '
          match($0, /:[0-9]+:/) {
            if (ENVIRON["ALLOW"] != "" && substr($0, RSTART + RLENGTH) ~ ENVIRON["ALLOW"]) next
            print substr($0, 1, RSTART + RLENGTH - 2) ": " ENVIRON["NAME"]
          }')
  if [ -n "$h" ]; then hits="${hits:+$hits
}$h"; fi
  i=$((i + 1))
done
if [ -n "$hits" ]; then
  printf '%s\n' "$hits"; echo "SECRETS: 비밀로 보이는 문자열 — 위치와 패턴 이름만 표시(값은 찍지 않는다)"; fail=1
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  tracked=$(git ls-files -- '.env' '.env.*' ':!.env.example')
  if [ -n "$tracked" ]; then echo "SECRETS: 환경 파일이 git 에 추적됩니다: $tracked"; fail=1; fi
fi
exit $fail
