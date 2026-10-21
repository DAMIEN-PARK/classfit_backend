---
type: Task Plan
title: "Plan: T0a sdlc-bootstrap"
description: SDLC 1~3단계(계획·차단기·자동 문지기)와 ADR-002·003 을 ClassFit 저장소에 까는 첫 태스크 계획
date: 2026-10-21
tags: [plan, task, t0a, sdlc, classfit]
Archives: false
URL: ""
---

# Plan: T0a sdlc-bootstrap (from plan.md#T0a, 2026-10-21)

- 근거: 플랜 r3 §5.2 T0a 행 · 부록 E0~E3·E7~E11·J · §6 E-1·E-2·E-6 · 승인 기록(2026-10-21). plan.md 는 T0b 에서 생기므로 태스크 출처는 "r3 §5.2" 다.
- 승인: 
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T0a" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다(r3 §5.1-2). 그 커밋 전에는 코드 변경이 없다.
- 부록 J 확인 조건: 아래 **R1~R3** 중 하나라도 빠졌으면 승인하지 않는다. **R4** 도 이 계획에서 확인한다(r3 부록 J 끝 단락).
- 가지 `T0a-sdlc-bootstrap`, 만든 시점 `git merge-base T0a-sdlc-bootstrap master` = `e80387f7c70d74e421633a30411de8d99f3080f0` (R3 값).

**승인으로 정해진 값** (r3 승인 기록 · §1.1)

| 칸 | 값 | T0a 에서 쓰는 곳 |
|---|---|---|
| ① 승인자 표기 | `DAMIEN-PARK` | CLAUDE.md Rules · docs/plans/README.md · merge_task.sh 트레일러 |
| ② 실고객사명·도메인 금지 목록 | "없음" | scripts/forbidden_terms.txt 주석(답·날짜) |
| ③ 원격 개통 시 PR 전환 | 예 | CLAUDE.md "Starting a task" · docs/plans/README.md |
| ④ 수강생 세션 수명 | 1일 | T0a 범위 밖. T1 설정 기본값(r3 부록 J T1) |

## 바뀌는 파일

부록 E0 배치 · E1~E3 의 T0a 분 전부. 새 셸 스크립트·훅은 `chmod +x` 한다(SDLC §6 머리).

| 경로 | 종류 | 단계 | 한 줄 이유 (출처) |
|---|---|---|---|
| `docs/plans/T0a-sdlc-bootstrap.md` | new | E1 | 이 계획. 가지 첫 커밋 `plan: T0a sdlc-bootstrap`, 트레일러 없음(§5.1-1) |
| `CLAUDE.md` | new | E1 | §6.1 한 페이지. Rules 는 E7 칸(승인자·금지 의존성 E8·경계·단일 진입점·권한 쿼리·파일 크기), 흐름은 §5.1(approve 커밋·merge_task·`master`) |
| `docs/plans/README.md` | new | E1 | §6.2 + approve 빈 커밋 규약, 제목 규약 `plan:`·`approve:`·`T<n>:`·`sync:`·`merge:`. 머리말 `type: Readme`(E7) |
| `docs/process/templates/task-plan.md` | new | E1 | §6.2 틀 + "리뷰" 절(§5.1-3). 머리말 `type: Task Plan`(OKF §5.3) |
| `docs/process/templates/intent.md` | new | E1 | §6.3 틀. 머리말 `type: Intent`. 폴더는 T0b okf.toml 에서 뺀다(E7 `exclude_dirs`) |
| `docs/process/adr/ADR-002-learner-session.md` | new | E1 | r3 §4 ADR-002 행(결정·대가). 머리말 `type: ADR`(N1, OKF §2) |
| `docs/process/adr/ADR-003-external-ports.md` | new | E1 | r3 §4 ADR-003 행(결정·대가). 머리말 `type: ADR` |
| `.github/pull_request_template.md` | new | E1 | §6.13. 원격 전에는 merge_task 병합 본문이 기록이다 |
| `Makefile` | modify | E1·E2 | `fix-start`·`fix-end`(§6.10) 추가, `hooks` 에 `git config merge.ff false` 추가(E1) |
| `.gitignore` | modify | E1 | `.claude/fix-mode`·`.claude/settings.local.json`·`var.nosync/`(E1, §6.7) |
| `scripts/task_order_base` | new | E1 | **R3** 위 merge-base 전체 해시 한 줄(E1, J) |
| `scripts/check_task_order.sh` | new | E1 | E-1 판정. 가지 안 `sync: T<n>` 병합 허용(**R1**, J) |
| `scripts/sync_task.sh` | new | E1 | **R1** 현재 가지가 master 면 거절, 아니면 `git merge --no-ff master -m "sync: T<n> …"`. 에이전트 허용(E11) |
| `scripts/merge_task.sh` | new | E1 | **R2** 승인자 전용(Claude 밖 터미널). 첫 단계 검사 셋 → `--no-ff --no-commit` → `make verify` → 커밋/`--abort`, `trap` 으로 원래 가지 복귀(J, §5.1-4). 경로는 `$0`·`dirname` 대신 `git rev-parse --show-toplevel` 로 잡는다(사본 실행 대비) |
| `scripts/forbidden_terms.txt` | modify | E1 | 이미 추적 중(주석 2줄). 답 "없음"과 날짜 2026-10-21 주석만 더한다. 목록 행은 없다(§1.1 ②, E8) |
| `.claude/settings.json` | new | E2 | §6.7 allow·deny·훅 등록 + E11 deny 전부 + allow `Bash(bash scripts/sync_task.sh*)`(**R1**) |
| `.claude/hooks/_json.sh` | new | E2 | §6.8 공통 JSON 풀이 |
| `.claude/hooks/protect-tests.sh` | new | E2 | §6.8 fix-mode 에서 `tests/**` 편집 차단 |
| `.claude/hooks/deny-deps.sh` | new | E2 | §6.8 + E8: gate 와 같은 모듈 import·PEP 503 정규화한 requirements 행. langchain-core 는 막지 않는다 |
| `.claude/hooks/deploy-gate.sh` | new | E2 | §6.8 그대로. 배포가 없어 시험만 통과하는 빈 차단기(E2) |
| `.claude/hooks/format-on-edit.sh` | new | E2 | §6.8 `.py` 편집 뒤 ruff 정리, 막지 않음 |
| `.claude/hooks/deny-approval.sh` | new | E2 | 에이전트 `git commit` 메시지의 `Approved-by` 차단(N2, §5.1-2) |
| `.claude/hooks/test_hooks.sh` | new | E2 | §6.8 8건 + deny-approval 2건(차단 1·허용 1, 이 계획이 정한 분배) → `10/10 OK`(E-2) |
| `REVIEW.md` | new | E2 | §6.5 + Security 패스에 원칙 10·파일 key·교차 강의(E2). 원격 전 결과는 계획 "리뷰" 절(§5.1-3) |
| `.claude/agents/reviewer.md` | new | E2 | §6.6. 원격 전에는 `gh pr` 대신 `git diff master...HEAD` 를 읽는다 |
| `.claude/agents/verifier.md` | new | E2 | §6.6 그대로 |
| `pyproject.toml` | modify | E3 | banned-api 에 langchain_openai·langchain_community·langchain_anthropic·langchain_google_genai·langchain_text_splitters·langchain_experimental(E8 1행) |
| `scripts/gate.sh` | modify | E3 | E8: 목록 밖 `langchain_*` import 접두 검사(langchain_core 예외), requirements 이름 PEP 503 정규화(소문자, `[-_.]+` → `-`) 뒤 대조. **R4** 금지 용어 범위에 `docs/`·루트 `*.md`, 출력 `file:line` 만. `CLASSFIT_FORBIDDEN_TERMS_REQUIRED=1` 인데 `scripts/forbidden_terms.txt` 가 없으면 `GATE FAIL`(E8) |
| `scripts/test_gate.sh` | new | E3 | E-6 임시 사본 음성 5종·양성 2종(E8) |
| `.githooks/pre-commit` | new | E3 | MERGE_HEAD 없는 master 커밋 차단. docs guard 는 T0b(E9) |
| `.githooks/pre-merge-commit` | new | E3 | **R1** 현재 가지가 master 일 때만 차단. 다른 가지 병합(sync_task)은 통과. merge_task 는 `--no-commit` 이라 이 훅을 타지 않는다(J) |
| `.githooks/pre-push` | modify | E3 | 기존 editable-check·gate·lint·lint-imports + test_hooks·test_gate·check_task_order(E9). gate 호출 전에 `export CLASSFIT_FORBIDDEN_TERMS_REQUIRED=1`(E8 "pre-push·CI"). check_docs·golden 은 T0b·T2a |
| `.github/workflows/ci.yml` | modify | E3 | concurrency(`cancel-in-progress: github.ref_name != 'master'`, §6.12 의 main → master, E10) + gates 잡에 test_hooks·test_gate·`bash scripts/check_task_order.sh` 단계(checkout 은 `fetch-depth: 0`, §6.12). check_task_order 단계는 r3 E9 표의 누락이고 E11 을 따른다. gates 잡 `env` 에 `CLASSFIT_FORBIDDEN_TERMS_REQUIRED: "1"`(E8). 트리거는 유지(부록 I-1) |

바꾸지 않는 것: `alembic.ini`(사용자 미커밋 변경, 승인 기록) · `README.md` · `scripts/check_secrets.sh` · `make verify` 순서(okf 는 T0b) · 미추적 `기획/`·`시안/`·`공개홈_v24.html`.

## 작업 순서

안내서 코드는 돌려 본 발췌다. 바꾸는 곳은 금지 목록·경로·`main` → `master` 뿐이고, 바꾼 뒤 관문 명령을 다시 돌린다(E10). 커밋은 파일을 지정한다. `git add -A`·`git add .`·`git commit -a` 는 쓰지 않는다(E10 · OKF §8-12).

**E0 계획과 승인**
1. 에이전트: 이 파일만 스테이징해 `plan: T0a sdlc-bootstrap` 으로 커밋한다. 트레일러는 없다.
2. 승인자: R1~R4 를 확인하고 `approve: T0a` 빈 커밋을 더한다. 이 커밋 전에는 아래를 시작하지 않는다.

**E1 SDLC 1단계 — 뼈대**
3. CLAUDE.md · docs/plans/README.md · templates 2장 · ADR-002·003 · PR 템플릿 · Makefile · .gitignore · forbidden_terms.txt 를 쓴다.
4. **R3** `scripts/task_order_base` 에 `e80387f7c70d74e421633a30411de8d99f3080f0` 한 줄을 적는다. 가지를 만든 시점의 merge-base 이고 지금 다시 재지 않는다.
5. **R1** `sync_task.sh`: `git symbolic-ref --short HEAD` 가 master 면 거절하고, 아니면 `git merge --no-ff master -m "sync: T<n> …"` 를 한다.
6. `check_task_order.sh`: base 다음 master first-parent 가 전부 `merge: T<n>` 이고 본문에 verify 꼬리·`Approved-by` 가 있는지, 가지는 `plan:` → `approve:`(`Approved-by`) → `T<n>:` 순서인지 잰다. 그 사이 `sync: T<n>` 병합은 허용한다(**R1**).
7. **R2** `merge_task.sh` 첫 단계 검사 셋: ① `git status --porcelain --untracked-files=no` 가 비어 있음 ② "에이전트 세션을 멈췄는가 [y/N]" 대화형 확인 ③ 병합할 가지에서 `check_task_order.sh` 통과. 원래 가지는 `trap … EXIT` 로 복귀한다.
8. **R2** 그다음 master 에서 `git merge --no-ff --no-commit <가지>` → `make verify >"$out" 2>&1; rc=$?`(파이프 없음) → rc 0 이면 제목 `merge: T<n> <slug>`, 본문 `$out` 끝 20줄 + `Approved-by:` 로 커밋, 아니면 `git merge --abort`.
9. `make hooks` 로 `core.hooksPath`·`merge.ff=false` 를 건다(로컬 설정, 커밋되지 않음).
- 관문: `bash scripts/check_task_order.sh` → `task order: OK` · `git config --get merge.ff` → `false`. SDLC §5 1단계 관문 "한 바퀴"는 맨 끝 16번에서 닫힌다.

**E2 SDLC 2단계 — 차단기**
10. 훅 7개(`_json`·protect-tests·deny-deps·deploy-gate·format-on-edit·deny-approval·test_hooks)를 쓰고 `chmod +x` 한다. settings.json 에 E11 deny 와 sync_task allow(**R1**)를 넣고 deny-approval 을 PreToolUse(Bash)에 등록한다. REVIEW.md·reviewer·verifier 를 쓴다.
11. 사람: 새 Claude 세션에서 trust 를 수락하고 deny 를 손으로 확인한다(증명 기록 칸).
- 관문: `bash .claude/hooks/test_hooks.sh` → `10/10 OK`(SDLC §5 2단계의 `8/8` 에 deny-approval 2건). `gh pr comment` 리뷰는 원격이 없어 14번의 "리뷰" 절로 대신한다(§5.1-3).

**E3 SDLC 3단계 — 자동 문지기**
12. pyproject banned-api · gate.sh(E8, `CLASSFIT_FORBIDDEN_TERMS_REQUIRED=1` 인데 목록 파일이 없으면 `GATE FAIL`) · test_gate.sh · pre-commit · pre-merge-commit(**R1**, 현재 가지가 master 일 때만 차단, 다른 가지 병합(sync_task)은 통과) · pre-push · ci.yml 을 고친다. `CLASSFIT_FORBIDDEN_TERMS_REQUIRED=1` 은 pre-push 가 gate 호출 전에 export 하고 ci.yml gates 잡 `env` 에 넣는다(E8). ci.yml gates 잡에는 test_hooks·test_gate 와 함께 `bash scripts/check_task_order.sh` 단계를 더한다(r3 E9 표의 누락, E11 을 따름).
13. **R4** gate.sh 금지 용어 검사 범위를 src·tests·alembic·scripts 에 `docs/`·루트 `*.md` 까지 넓히고, 출력은 `grep -rnoiE … | cut -d: -f1,2` 로 `file:line` 만 남긴다(맞은 줄 내용은 찍지 않는다, E8·J). 판정은 맨 파이프의 종료 코드가 아니라 `hits=$( … )` 캡처 뒤 `[ -n "$hits" ]` 로 한다(또는 `set -o pipefail`).
- 관문: `bash scripts/test_gate.sh` → `음성 5/5 OK · 양성 2/2 OK`(SDLC §5 3단계 "금지 import 1줄 → GATE FAIL" 의 확장) · `make verify` exit 0.

**마무리**
14. 다른 세션의 reviewer 가 아래 "리뷰" 절을 쓰고, Important 0 이 될 때까지 고친다(§5.1-3).
15. verifier 가 "증명" 명령을 다시 돌린다(§6 끝 단락).
16. 승인자(Claude 밖 터미널): `bash scripts/merge_task.sh T0a-sdlc-bootstrap` → master 에 `merge: T0a sdlc-bootstrap`. T0a 만은 master 에 스크립트가 없어 위험 표의 사본 실행 명령으로 돌린다. 이것이 E1 관문 "T0a 가 5.1 한 바퀴를 돈다"다.

## 위험

| 위험 | 알아채는 법 | 완화 (출처) |
|---|---|---|
| `alembic.ini` 미커밋 변경 때문에 merge_task 검사 ① 이 병합을 거절한다 | 16번 첫 단계 메시지 | 병합 전에 사용자가 그 변경을 `.env`(`CLASSFIT_DATABASE_URL`)로 옮기고 `git checkout -- alembic.ini` 로 되돌려야 한다(승인 기록 권장). 에이전트는 하지 않는다 |
| T0a 병합 때 master 에는 merge_task.sh 가 아직 없고, 가지 전환 중 스크립트 파일이 바뀐다 | 16번 실행 | 승인자가 master 에서 `bash <(git show T0a-sdlc-bootstrap:scripts/merge_task.sh) T0a-sdlc-bootstrap` 로 가지의 사본을 돌린다. 작업 트리의 파일을 읽지 않으므로 가지 전환 중에 파일이 바뀌어도 상관없다 |
| 사본 실행에서는 스크립트가 `/dev/fd` 로 읽혀 `$0`·`dirname` 이 저장소를 가리키지 않는다 | 16번 실행 중 경로 오류 | merge_task.sh 는 `git rev-parse --show-toplevel` 로 경로를 잡는다 |
| 자가 승인(위조) | `check_task_order.sh` · deny-approval 시험 | approve 는 승인자만. `git commit -F` 처럼 훅이 못 보는 길이 있고 같은 계정이라 완전히 막지 못한다. 위조는 agent.md 위반(부록 F, §5.1-2) |
| 에이전트가 master 를 움직인다 | `check_task_order.sh`. 원격 전에는 다음 merge_task 와 수동 실행에서만 돈다 | E11 deny(완전하지 않음) + MERGE_HEAD 없는 master 커밋 금지 pre-commit(부록 F, E11) |
| deny 가 필요한 명령까지 막는다 | 증명의 수동 확인 | `git merge`·`git merge *` 로 좁혀 merge-base·mergetool 허용, `-c` 는 hooksPath·merge.ff 만. 스테이지 해제는 `git restore --staged`(E11, J) |
| 설정 키 대소문자 변형은 deny 패턴이 못 덮는다 | — | 최종 방어 두 겹(pre-commit + check_task_order)에 맡긴다(E11) |
| settings.json 이 작업 트리에 생기면 지금 돌고 있는 세션에도 deny 가 걸릴 수 있다 | 10번 뒤 막힌 명령 | 그 뒤 git 작업은 deny 목록 안에서 한다. 가지 갱신은 sync_task.sh |
| 병합 결과가 가지의 verify 와 다르다 | 병합 본문의 verify 꼬리 | merge_task 가 병합 결과 트리에서 verify(부록 F) |
| `검사 \| tail` 이 실패를 삼킨다 | — | merge_task 는 출력 파일·종료 코드 분리, 스크립트는 `set -o pipefail`(E10, SDLC §8) |
| 대조 실험이 미커밋 변경을 지운다 | — | test_gate 는 임시 사본에서만 넣고 뺀다(SDLC §5 3단계 ⚠️, E10) |
| 훅은 trust 전에는 로드되지 않는다. test_hooks 는 trust 와 무관하게 녹색이다 | 11번 수동 확인 | trust 수락을 증명에 기록(SDLC §5 2단계 ⚠️) |
| 금지 용어 출력으로 실명이 CI 로그에 샌다 | gate 출력에 줄 내용이 없음 | **R4** `file:line` 만. 지금 목록은 비어 있다(E8) |
| 나중에 실명이 생긴다 | — | 실명이 생기면 `scripts/forbidden_terms.txt` 를 gitignore 하고 CI secret(`FORBIDDEN_TERMS`) 주입 단계를 추가한다(E8). T0a 는 gate.sh 의 필수 목록 검사만 넣고 secret 단계는 넣지 않는다 |
| `merge.ff`·`core.hooksPath` 는 git 설정이라 다른 사본에는 없다 | `git config --get merge.ff` | `make hooks` 에 넣고 증명에 기록 |
| CI 변경은 원격 전에 돌려 볼 수 없다 | 원격 개통 관문 | 그날 E-15 로 확인(§5.1) |

## 증명

r3 §6 의 명령과 기대 출력 그대로(E-1·E-2·E-6):

```bash
bash scripts/check_task_order.sh                    # E-1 scripts/task_order_base(T0a 가지를 만들 때의 master HEAD) 다음부터 master first-parent 가 전부 merge: T<n>, 가지 첫 커밋 plan:(가지 안 sync: 병합 허용), approve:(Approved-by)가 첫 T<n>: 보다 앞, 병합 본문에 verify 꼬리·Approved-by → "task order: OK"
bash .claude/hooks/test_hooks.sh                    # E-2 안내서 8건 + deny-approval 2건 → "10/10 OK"
bash scripts/test_gate.sh                           # E-6 음성: 임시 사본에 금지 줄 5종(asyncpg·langchain_openai import, asyncpg·langchain-openai·langchain_openai 행)을 하나씩 넣으면 실패. 양성: 깨끗한 사본 통과, langchain-core 행·import langchain_core 허용 → "음성 5/5 OK · 양성 2/2 OK"
make verify                                         # T0a 시점: exit 0, "gate: OK"·"All checks passed!"·"Contracts: 2 kept, 0 broken."(pyproject 계약 ①·③, ② 는 T1)·"passed"(failed·error·skipped 0). "OKF guard OK" 는 T0b 부터(E-3 은 1차 끝 기준)
```

| 기록 칸 | 값 |
|---|---|
| `scripts/task_order_base` (**R3**) | `e80387f7c70d74e421633a30411de8d99f3080f0` — 2026-10-21 `git merge-base T0a-sdlc-bootstrap master` |
| trust 수락 (날짜 · 세션) | |
| 허용 확인 `git -c core.quotepath=false status` | |
| 허용 확인 `git merge-base T0a-sdlc-bootstrap master` | |
| 허용 확인 `git mergetool --tool-help` | |
| **R4** 임시 사본(목록에 시험 용어 1줄 + 그 용어가 든 줄 1개)에서 gate 출력이 `file:line` 만이고 GATE FAIL | 2026-10-21 reviewer 사본 실험: 출력 4건 모두 `file:line`, 줄 내용 0, 목록 삭제+REQUIRED=1 → GATE FAIL |
| `make hooks` 뒤 `git config --get core.hooksPath` / `merge.ff` | |
| 병합 뒤 `git log --first-parent -1 --format=%s master` | |

## 리뷰

reviewer-t0a(다른 세션) · 2026-10-21 · 범위 `git diff master...HEAD` 33 files · REVIEW.md 패스 Bugs → Security → Compliance · 판정 **Important 0 / nit 10(표시 5)**

**실행해 본 것**: `bash -n` 16개 OK · test_hooks 10/10 · check_task_order OK · settings.json 파싱 OK · ruby YAML(ci.yml concurrency · fetch-depth · env 정상) · tomllib(banned-api 정상) · _json.sh 주입 시험(따옴표 · `$(…)` · 백틱 · 개행 → 값 그대로, PWNED 0) · deny-deps 차단/허용 사례 · deny-approval 이 리뷰 세션 명령을 실제로 막음(`-F` 는 알려진 한계) · gate R4 사본 실험(출력 `file:line` 만, 줄 내용 0, 목록 삭제 + REQUIRED=1 → GATE FAIL) · 가지 이름 표본(`T1-a/T2-b` 처럼 슬래시 든 이름은 두 스크립트가 다르게 읽음) · Claude Bash 의 stdin 은 TTY 가 아니고 파이프로 넣은 y 를 `read -p` 가 받음.

**nit(표시 5)** — 줄 번호는 리뷰 시점(111bdd6) 기준

| # | [nit·분류] 파일:줄 | 요지 | 처리 |
|---|---|---|---|
| 1 | [nit·Security] `scripts/merge_task.sh:69` | ② `read -p` 가 파이프 입력을 받아 대화형 확인에 y 를 흘려 넣을 수 있다 | **반영(이 커밋)**: `read` 앞에 `[ -t 0 ]` 검사 |
| 2 | [nit·Security] `scripts/merge_task.sh:81-85` | 가지에 커밋된 `check_task_order.sh` · `task_order_base` 로 그 가지를 잰다. 가지가 검사기를 약하게 고치면 자기를 통과시킨다 | **반영(이 커밋)**: master 판 우선, master 에 없을 때(T0a)만 가지 사본. 가지의 base 가 master 판과 다르면 중단 |
| 3 | [nit·Compliance] `.claude/settings.json:15-16` | allow `Bash(git add *)` · `Bash(git commit *)` 가 `git add -A` · `git add .` · `git commit -a` 를 통과시킨다(`CLAUDE.md:64` 와 불일치) | **반영(이 커밋)**: deny 5줄 `git add -A*` · `git add --all*` · `git add .` · `git add . *` · `git commit -a*`. `git add .*` 는 `.gitignore` 추가까지 막아 쓰지 않았다 |
| 4 | [nit·Compliance] `scripts/test_gate.sh:83-94` · `.claude/hooks/test_hooks.sh:28` | test_gate 에 hook 층이 없다(E8 "위 셋"). test_gate ② 는 "ruff 또는 gate" 로 통과한다. test_hooks 9번이 승인 제목·트레일러 두 분기를 한 명령에 합쳤다 | **보류, T0b 계획 후보** |
| 5 | [nit·Security] `scripts/gate.sh:60-65` | 금지 용어를 ERE 로 결합해 괄호 든 `XX(주)` 를 못 맞히고, grep rc 2 를 삼킨다 | **보류**: 목록이 비어 지금은 영향 없다. 실명이 생길 때 `grep -F -f` 로 바꾸고 rc 2 를 알린다 |

미표시 nit 5건(슬래시 가지 이름 판독 차이 등)은 reviewer 세션 원문에만 있다. 위 표와 실행 내역의 요약은 `.omc/handoffs/team-exec-phase2.md`(gitignore 라 git 밖)에 있다.

**계획 ↔ diff 대조**: 바뀌는 파일 33 = diff 33(차집합 0) · 바꾸지 않는 것 4종 diff 없음 · 기록 안 된 편차 1(E8 "위 셋" — nit 4 로 기록됨).

## 계획과 다르게 한 것

1. **merge_task.sh 검사 순서와 종료 코드**: 검사 셋(깨끗한 트리 → y/N 확인 → 가지 `check_task_order`)을 master 전환보다 앞에 두었다. 본문은 `main "$@"; exit 0` 한 줄로 감싸 사본 실행 중 파일이 바뀌어도 안전하다. 진행 중인 병합·병합할 것 없음은 exit 1. 종료 코드는 0 병합 · 1 검사·충돌·verify 실패 · 2 사용법.
2. **check_task_order.sh 가 계획보다 엄격하다**: 가지 이름 `^(T[0-9]+[a-z]?)-([A-Za-z0-9][A-Za-z0-9._-]*)$`, plan 제목 `plan: <tid> <slug>` 의 슬러그가 가지와 일치, 승인 커밋은 빈 커밋 + 본문 트레일러 줄 `^Approved-by: [^[:space:]]`(대소문자 구분) 필수, `T<n>:` 는 승인 커밋 뒤, `sync: <tid>` 는 2-parent 병합, master first-parent 는 `^merge: T… <slug>$` + 본문 `^make verify: exit 0` 줄 + 트레일러 줄 필수. 종료 코드는 0 통과 · 1 위반 · 2 못 쟀다. "plan 커밋은 docs/plans/ 만" 검사는 뺐다(iCloud 읽기 오류가 `|| true` 에 삼켜지기 때문).
3. **settings.json deny 에 E11 밖 4줄**: `Bash(bash scripts/merge_task.sh*)` · `Bash(./scripts/merge_task.sh*)` · `Bash(scripts/merge_task.sh*)` 3줄로 승인자 전용 병합 스크립트의 직접 실행을 막는다(allow `Bash(bash scripts/*)` 가 그 스크립트를 통과시키기 때문). `Bash(.venv/bin/alembic downgrade*)` 도 더했다.
4. **deny-deps.sh 범위**: 의존성 파일 검사는 `requirements*.in` · `requirements*.txt` 만 본다. pyproject.toml 은 banned-api 설정 줄이 걸리므로 제외했다. 동기 Session 금지는 훅이 아니라 ruff 가 맡는다.
5. **test_hooks 10건 분배**: protect-tests 3 · deny-deps 3(차단 `langchain_openai` import · requirements `langchain_openai==0.2`, 허용 `langchain_core` · `langgraph`) · deploy-gate 2 · 승인 차단(deny-approval) 2.
6. **템플릿 머리말**: task-plan · intent 템플릿 머리말에 Archives/URL 기본값을 넣고 끝에 Resources 꼬리를 붙였다. ruby 로 머리말을 검사할 때는 `permitted_classes: [Date]` 가 필요하다.
7. **`make hooks` 는 워커가 돌리지 않았다**: `make hooks`(merge.ff=false)는 E11 deny 대상 설정이다. 승인자가 병합 전에 돌린다.
8. **CI 와 pre-push**: CI gates 잡에 check_task_order 단계를 더했다(E9 에는 없고 E11 이 우선). `CLASSFIT_FORBIDDEN_TERMS_REQUIRED` env 와 `fetch-depth: 0` 도 넣었다. pre-push 는 check_task_order 의 "못 쟀다"(exit 2, master 참조 없음)를 경고만 하고 push 를 막지 않는다.
9. **deny 글롭의 알려진 구멍(verifier 메모)**: 인자 없는 `git push`, `git branch -D` · `-m` · `--force`, `git commit -m x -n` 은 deny 글롭에 걸리지 않는다. E11 이 deny 를 "불완전"하다고 둔 범위이고, 최종 방어는 pre-commit + check_task_order 두 겹이다. master 위 병합 실험 2건(자동 병합 커밋 차단 · `--no-ff --no-commit` 뒤 병합 커밋 통과)은 세션 deny 때문에 에이전트가 돌리지 못한다. 승인자가 Claude 밖 터미널에서 `/private/tmp/claude-501/-Users-damienpark-Documents-PROJECT-ClassFit/ce64a957-6aee-4b65-aee0-dc1999802ff8/scratchpad/exp_master_hooks.sh` 로 확인한다(임시 clone 에서만 병합).
10. **환경: iCloud dataless venv**: 원본 `.venv.nosync` 에 iCloud dataless 파일이 18개 있어(verifier 측정, 통합 직전 재측정 17개) 원본 venv 로 pytest 를 돌리면 EDEADLK(`Resource deadlock avoided`)가 난다. verifier 는 스크래치 venv 로 `make verify` exit 0 · 20 passed 를 확인했다. 병합 전에 venv 를 다시 만들거나 저장소를 iCloud 밖으로 옮겨야 한다.
11. **reviewer nit 1·2·3 반영**: 이 커밋(`T0a: 리뷰 반영 — TTY 확인·master 판 검사기·add -A deny, 리뷰 절 기록`)으로 반영했다(TTY 확인, master 판 검사기 우선, git add -A/./commit -a deny). 그래서 merge_task.sh ③ 은 이제 master 판 `check_task_order.sh` 를 먼저 쓰고, 가지의 `task_order_base` 가 master 판과 다르면 중단한다(1번 항목의 "가지 `check_task_order`" 는 master 에 검사기가 없는 T0a 에만 해당).




---

# Resources

- 승인된 플랜 r3: `.omc/plans/2026-10-21-classfit-phase1-r3.md`(저장소 루트 기준, gitignore 라 git 에 남지 않음)
- SDLC 이식 안내서: `2026-10-06-ai-native-sdlc-porting-guide.md`(저장소 루트)
- OKF 이식 안내서: `2026-10-21-okf-sdlc-porting-guide.md`(저장소 루트)
