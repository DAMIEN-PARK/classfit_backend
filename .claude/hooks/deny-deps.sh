#!/usr/bin/env bash
# PreToolUse(Edit|Write|MultiEdit): 금지 의존성의 import 또는 의존성 파일 행을 쓰려는 편집을 차단한다.
# 금지 목록은 r3 부록 E8 — gate.sh 와 같은 모듈: asyncpg·psycopg2·openai·langchain·langchain_*(langchain_core 만 허용).
# 동기 Session·sessionmaker·create_engine 은 정규식으로 안정적으로 표현할 수 없어 ruff TID251(pyproject banned-api)만 맡는다(E8).
set -u
. "$(dirname "$0")/_json.sh"; eval "$(hook_read)"
FORBID='asyncpg|psycopg2|openai|langchain(_[[:alnum:]_]+)?'                         # import 모듈 최상위 이름
ALLOW='langchain_core'                                                             # langgraph 이행 의존성
PKG_FORBID='asyncpg|openai|psycopg2|psycopg2-binary|langchain|langchain-[a-z0-9-]+'  # PEP 503 정규화한 패키지 이름
PKG_ALLOW='langchain-core'
WHY="금지 의존성(asyncpg·psycopg2·openai·langchain·langchain_*, langchain_core 만 허용). 드라이버는 psycopg 3, OpenAI 호환 API 는 httpx 로 직접 부를 것 — CLAUDE.md Rules"

# import 줄에서 모듈 최상위 이름을 뽑는다: "from X.y import z" → X, "import a.b as c, d" → a, d. 상대 import(.x)는 빈 이름이 된다.
mods=$(printf '%s\n' "$HOOK_TEXT" \
  | grep -E '^[[:space:]]*(from|import)[[:space:]]' \
  | sed -E 's/#.*//; s/^[[:space:]]*from[[:space:]]+([^[:space:]]+).*/\1/; s/^[[:space:]]*import[[:space:]]+//' \
  | tr ',' '\n' \
  | sed -E 's/^[[:space:]]+//; s/[[:space:]].*//; s/\..*//')
bad=$(printf '%s\n' "$mods" | grep -E "^($FORBID)\$" | grep -vE "^($ALLOW)\$")
if [ -n "$bad" ]; then
  echo "$WHY — import: $(printf '%s' "$bad" | tr '\n' ' ')" >&2; exit 2
fi

# 의존성 파일 행. pip 는 -_. 를 같은 이름으로 보므로(PEP 503) 이름을 소문자·[-_.]+ → - 로 정규화한 뒤 대조한다.
# 주석·옵션 행(-r·-c·--hash)은 이름이 영숫자로 시작하지 않아 건너뛴다.
# pyproject.toml 은 대상이 아니다: ClassFit 은 의존성을 requirements.in 에 두고(pyproject 는 dynamic),
# pyproject 의 banned-api 목록은 금지 모듈 이름을 일부러 적는 곳이라 여기서 막으면 그 목록을 고칠 수 없다.
case "$HOOK_FILE" in
  *requirements*.in|*requirements*.txt)
    names=$(printf '%s\n' "$HOOK_TEXT" \
      | sed -nE 's/^[[:space:]]*([A-Za-z0-9][A-Za-z0-9._-]*).*/\1/p' \
      | tr 'A-Z' 'a-z' \
      | sed -E 's/[-_.]+/-/g')
    badpkg=$(printf '%s\n' "$names" | grep -E "^($PKG_FORBID)\$" | grep -vE "^($PKG_ALLOW)\$")
    if [ -n "$badpkg" ]; then
      echo "$WHY (의존성 파일 행: $(printf '%s' "$badpkg" | tr '\n' ' '))" >&2; exit 2
    fi;;
esac
exit 0
