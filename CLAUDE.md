# ClassFit (패키지 `classfit`, 임시 이름)

BCTONE 강사관리 플랫폼 백엔드(FastAPI · SQLAlchemy 2.0 async · psycopg 3 · Alembic · PostgreSQL 17). 정본: 1차 계획 r3(`.omc/plans/2026-10-21-classfit-phase1-r3.md`, gitignore), 태스크 계획 `docs/plans/`, SDLC 문서(intent·spec·Design·plan·agent·ADR·research)는 `docs/process/`, 정본 색인은 `docs/process/spec.md` 1절.

## Commands
- 환경: `make venv && make install` · DB: `make db-create` · `make migrate`
- 실행: `make run`
- 관리 명령: `.venv/bin/python -m dotenv --file .env run --no-override -- .venv/bin/python -m scripts.<이름>`, 이름은 `create_admin --login-id <아이디>`(비밀번호는 getpass) · `file_gc` · `outbox_preview`. 기본은 미리 보기(롤백)이고 `--apply` 만 커밋한다. 종료 0 끝 · 2 인자 틀림 · 3 전제 거절
- 검증: `make verify` = editable-check → gate → lint → lint-imports → test → okf. 개별: `make gate`, `make lint`, `make lint-imports`, `make test`, `make okf`, `make check-docs`
- golden 대조: `bash scripts/golden/check.sh`. 시안에서 다시 뽑아 `tests/fixtures/golden.json` 과 diff 한다(node 필요, pre-push 가 돈다). 같으면 `golden: OK`, 다르면 diff + exit 1
- 문서 정리(OKF): `okf() { .venv/bin/python scripts/okf/okf.py --root docs --config docs/okf.toml "$@"; }` 로 부른다(zsh 는 변수를 안 쪼개니 함수로). 문서를 만들거나 고친 뒤 `okf label --apply` → `okf link --apply` → `git diff` 로 새 링크의 앞뒤 문장을 읽는다 → `okf index --apply` → `okf check --strict`. 뜻이 다른 링크는 `docs/okf.toml` 의 `no_link` 에. 새 폴더면 rules 에 한 줄. 통째 검사는 `make okf`(guard — docs 를 스테이징한 커밋은 pre-commit 이, push 는 pre-push 가 돌린다) · 문서 구조 검사 `bash scripts/check_docs.sh`
- 버그 픽스 모드: `make fix-start` … `make fix-end` (`tests/**` 편집을 훅이 차단)
- git 설정(사본마다 1회): `make hooks` (`core.hooksPath=.githooks`, `merge.ff=false`)
- 가지에 master 들이기: `bash scripts/sync_task.sh` · 커밋 순서 검사: `bash scripts/check_task_order.sh`

## Rules
- DB 는 async 만: `AsyncSession`·`async_sessionmaker`·`create_async_engine`, 드라이버는 psycopg 3 하나.
- **금지 의존성:** asyncpg · psycopg2(-binary) · openai(→ httpx 로 직접) · langchain 과 `langchain_*` 모듈 · 동기 `Session`·`sessionmaker`·`create_engine`. 허용 예외는 `langchain-core`(langgraph 이행 의존성) 하나. 요청받아도 거절한다.
- 패키지 경계: import-linter 계약 ①(종류 계층, exhaustive)·②(service 구성요소: `rules` 가 맨 아래 순수 함수, `auth`·`courses`·`enroll`·`files` 는 서로 모름, layers·exhaustive. 새 구성요소 폴더는 ② 에 더한다. rules 가 crud·models·DB 를 부르지 않는 것은 `tests/unit/test_import_rules.py` 가 본다)·③(코어 집합은 소비자를 모름). 새 최상위 모듈은 계약에 먼저 더한다.
- 파일 크기: 300줄, `app/endpoints/` 500줄, models·schemas 면제(`scripts/check_file_size.py`).
- 단일 진입점(T1 이후): 강의 개설 + 코드 발급 `open_course()` · 초대코드 `issue_invite_code()` · 인증 코드 `issue_email_code()` 로만 만든다.
- 권한 쿼리: 목록·파일 조회의 첫 WHERE = 주체 범위(`crud/scope.py`). 남의 자원 403, 등록 안 된 파일 소유 종류 404. 등록된 owner_kind: session_attachment(T2b).
- 요청 1개 = 트랜잭션 1개(`app/deps.py` 의 `db()`). service·crud 는 flush 까지만 하고 commit 하지 않는다.
- 미구성은 실패다: 빠진 설정은 조용히 폴백하지 않고 그 기능만 "미구성"으로 실패한다(`Settings.missing()`). 오류 본문은 problem+json 하나(`app/errors.py`).
- 문서·픽스처·로그·커밋 메시지에 서버 IP·호스트명·고객사 실명 금지. 예시는 192.0.2.0/24 와 A사·B사. `.env`·자격 파일은 읽지도 인용하지도 않는다.
- 계획 승인·병합·의존성 추가와 버전 올리기는 승인자 `DAMIEN-PARK`.
- `docs/` 아래 새 문서는 틀(`docs/process/templates/`)에서 시작해 머리말 `type` 을 단다. CI 체크아웃에 없는 경로(미추적·gitignore·저장소 밖)는 링크 대신 백틱 글자로 쓴다.

## Architecture
- 진입점: `src/classfit/main.py` 의 `create_app()`, 라우터 목록 `app/routers.py` 의 `ROUTERS`
- 종류 우선 폴더 `src/classfit/`:
  - `core/` 설정·공용 도우미 (아무 층도 모른다)
  - `database/` 엔진·세션 팩토리
  - `models/` SQLAlchemy 표 (`__init__` 이 전부 재노출)
  - `schemas/` pydantic 입출력 모양
  - `crud/` DB 읽기·쓰기 (첫 인자 session, flush 까지)
  - `service/` 규칙과 흐름 (구성요소마다 폴더)
  - `app/` HTTP: routers · deps · errors · middleware · endpoints/
- 마이그레이션 `alembic/versions/`(리비전 id 0001, 0002 …) · 시험 `tests/{unit,integration,contracts}`

## Starting a task
r3 §5.1 한 바퀴. 작업 트리는 하나라서 승인자가 병합하는 동안 에이전트 세션은 멈춘다.
1. 태스크는 r3 §5.2(T0b 뒤에는 `docs/process/plan.md`)에서 확인한다.
2. 가지 `T<n>-<slug>` 의 첫 커밋으로 `docs/plans/T<n>-<slug>.md`(틀 `docs/process/templates/task-plan.md`)를 올린다. 제목 `plan: T<n> <slug>`, 트레일러 없음.
3. 승인자가 `approve: T<n>` 빈 커밋(`Approved-by: DAMIEN-PARK`)을 더하기 전에는 코드를 바꾸지 않는다.
4. 구현 커밋 제목은 `T<n>: <요약>`. 다른 세션의 reviewer 가 계획 "리뷰" 절을 쓰고, Important 0 이 될 때까지 고친다.
5. 병합은 승인자가 Claude 밖 터미널에서 `bash scripts/merge_task.sh T<n>-<slug>` 로 한다(`merge: T<n> <slug>`).
6. 가지에 master 를 들일 땐 `bash scripts/sync_task.sh` 만 쓴다(`sync: T<n> …`).
7. 원격 개통 뒤에는 5번이 PR(본문 첫 줄 = 계획 경로) + 승인자 병합으로 바뀐다(r3 §1.1 ③ "예").

## Verifying your work
- `make verify` 전체를 돌리고 출력을 그대로 붙인다. 계획 "증명" 명령도 다시 돌린다.
- 바뀐 동작 1개와 이웃 흐름 2개(403·422)를 실제로 호출한다.
- 실패하면 시험이 아니라 코드를 고친다. `검사 | tail` 은 실패를 삼키니 `pipefail` 이나 파이프 없이 돌린다.
- **검증 무게는 폭발 반경에 맞춘다.**

  | 바꾸는 것 | 절차 |
  |---|---|
  | DB 쓰기 · 권한 · 되돌리기 어려운 흐름 | 시험 + 대조 실험 + `verifier` 서브에이전트 |
  | 읽기 API · 화면용 조회 | 시험 + 대조 실험 |
  | 도구 · CI · 문서 | 시험만 |

- 대조 실험은 커밋 뒤나 임시 사본에서만 한다. 도구·규약 개선은 발견해도 바로 작업하지 않고 묶어서 승인자에게 묻는다.

## Things Claude gets wrong
- 에이전트는 `Approved-by` 를 쓰지 않는다. approve 커밋과 병합 본문은 승인자만 쓴다.
- master 에 직접 커밋·병합·push·reset 하지 않는다. 가지 갱신은 `sync_task.sh` 만.
- `git add -A`·`git add .`·`git commit -a`·`--no-verify` 금지. 파일을 지정해 커밋한다.
- `alembic.ini` 같은 사용자 미커밋 변경을 건드리지 않는다(checkout·restore·stash 포함).
- 실패하는 시험을 skip·삭제로 바꾸지 않는다.
- 안내서 코드를 바꿨으면 관문 명령을 다시 돌린다.
