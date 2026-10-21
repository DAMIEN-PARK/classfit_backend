---
type: Task Plan
title: "Plan: T0b sdlc-okf"
description: SDLC 4단계 문서 사슬(intent·spec·Design·ADR-001·004·plan·agent·research)과 OKF 1~7단계(okf.py·okf.toml·label·link·index·check·guard)를 깔고, T0a 리뷰 잔여 nit 와 CI 액션 판을 정리하는 태스크 계획
date: 2026-10-21
tags: [plan, task, t0b, sdlc, okf, classfit]
Archives: false
URL: ""
---

# Plan: T0b sdlc-okf (from plan.md#T0b, 2026-10-21)

- 근거: 플랜 r3 §5.2 T0b 행 · 부록 E4~E7·E9·E10 · §6 E-2~E-7·E-9 · 승인 기록(2026-10-21) · r1 D7(문서마다 채울 내용의 출처) · OKF 안내서 §5.2·§6·§7.2·§7.3·§8·§9 · SDLC 안내서 §5 4단계·§6.3·§6.4 · T0a 리뷰 nit 4·5([`docs/plans/T0a-sdlc-bootstrap.md`](T0a-sdlc-bootstrap.md) 리뷰 절). 태스크 출처는 r3 §5.2 T0b 이고, 이 태스크에서 [`docs/process/plan.md`](../process/plan.md) 로 옮긴다. 그 뒤로는 plan.md#T0b 가 출처다.
- 승인: 
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T0b" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 그 커밋 전에는 코드 변경이 없고, 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다(r3 §5.1-2).
- 가지 `T0b-sdlc-okf`, `git merge-base T0b-sdlc-okf master` = `181006e510f630b914ca7af69c2a7bd02e9955a8`(master `merge: T0a sdlc-bootstrap`).
- 번호: D1~D4·E0~E8 은 이 계획의 단계다. E1~E7 은 OKF 안내서 §6 의 1~7단계와 순서가 같다. 하이픈이 든 `E-n` 은 r3 §6 수용 기준이다.

## 착수 조건

| 조건 | 상태 | 출처 |
|---|---|---|
| T0a 병합 | 됐다. master `181006e` | r3 §5.2 |
| `pyyaml`(dev) 추가 | **이 계획의 approve 커밋이 그 승인이다** | r3 §1 · H-3 |
| 그 밖의 새 의존성 | 없다 | — |
| 원격 | 있다. `origin` = `https://github.com/DAMIEN-PARK/classfit_backend.git`(public), origin/master = `181006e`, 가지 T0a 푸시됨, master CI 2건 success(뼈대·T0a 병합), 브랜치 보호 없음. 착수를 막지 않는다. CI 는 master push·PR 에만 돌아서, 이 태스크의 CI 변경은 병합 뒤 첫 master push 의 CI 가 처음 돌린다 | r3 §1 · §5.1 · E-15 |

| 칸 | 2026-10-21 에 확인한 값 (확인 방법) |
|---|---|
| okf.py 원본 | `/Users/damienpark/Desktop/BHQ/plan/scripts/okf/okf.py` 822줄, sha256 `b8bfb796f0deade6bcda93370f7df27c0945aa56fba01f68f68c8060216a2f3c`(앞 16자 = 팀 핸드오프 값, `shasum -a 256`) |
| OKF 기준 규격 | `SPEC.md` 마지막 커밋 `0b87c52c6ef999286c745e19998fdfcd03d5dbee`(2026-08-21) = OKF §5.2 템플릿의 `spec_commit`(`gh api …/commits?path=SPEC.md`) |
| CI 액션 판 | `actions/checkout@v5`(node24, 2025-08-11)·`actions/setup-python@v6`(node24, 2025-09-04) 태그가 있다(`gh api repos/actions/<이름>/git/ref/tags/<판>`). 최신은 checkout v7.0.1·setup-python v7.0.0(2026-07-20)이다. 이번에는 node24 최소 판 v5·v6 으로 올리고, v7 은 범위 밖이다 |
| `.venv` · git 설정 | PyYAML 없음(`ModuleNotFoundError: No module named 'yaml'`), E1 의 첫 일이다. `core.hooksPath=.githooks` 라서 훅 파일은 저장하는 순간 이 사본의 커밋에 걸린다 |
| OKF 시뮬레이션 | 스크래치 사본(기존 6 + 머리말만 단 그룹 D 자리 9)에 이 계획의 okf.toml 로 BHQ okf.py 를 돌렸다. label 재실행 `{'같음': 15}` · index 재실행 `목차 0개 만들 것 · 같음 7개` · check 는 로컬 모양 `위반 0건 — 통과`, `.omc` 없는 CI 모양 exit 1(깨진 링크 1개, 위험 표 5행) |
| sha256 `기획/BCTONE_기획안_v3.html`(제품 정본, 미추적) | `54b8c90730d06641d2add5beaa419bad450c9549db6723bde7d06050ea54e9d1` |
| sha256 `기획/BCTONE_파이프라인_v3.html`(미추적) | `4519cb4b371a5fa028e85e98261a51c0e1992f588bfaf4028c65bf70eafe729b` |
| sha256 `시안/관리자.html`(참고, 미추적) | `c14d5e9631fe0c411c2af5ff254195d87dfef7c7412bf4a137c17aaa9f781be2` |
| sha256 `시안/강사.html`(참고, 미추적) | `041260b79b1dfcac6001f38f0e76ab2e7b21849fa065aa2454ac4cc0b0187e29` |
| sha256 `시안/학습자.html`(참고, 미추적) | `ea33694171a9823cfd6dbd65cb0ac89c1939ecf61e62d20c5634a0351a037551` |

## 바뀌는 파일

레인 소유 파일: **worker-d** 는 `docs/process/**`(templates 제외)와 `scripts/check_docs.sh` 를 맡는다. **worker-e** 는 그 밖 전부를 맡는다(Makefile·CLAUDE.md·pyproject 포함). label·link·index 는 docs 전체를 고치므로 E2~E5 는 그룹 D 커밋 뒤에만 돈다. 새 셸 스크립트는 `chmod +x` 한다.

**그룹 D — SDLC 4단계 (r3 E4, worker-d).** 새 문서 머리말은 7칸(type·title·description·date·tags·Archives·URL)이고, type 은 아래 okf.toml 규칙과 같게 단다. 그래야 label 이 "같음"으로 지나간다(r3 N1).

| 경로 | 종류 | 단계 | 한 줄 이유 (출처) |
|---|---|---|---|
| `docs/plans/T0b-sdlc-okf.md` | new | E0 | 이 계획. 가지 첫 커밋 `plan: T0b sdlc-okf`, 트레일러 없음(r3 §5.1-1) |
| [`docs/process/intent.md`](../process/intent.md) | new | D1 | product. 틀 [`docs/process/templates/intent.md`](../process/templates/intent.md)(SDLC §6.3). 기획안 01 제품 정의·03 운영 원칙 13·9-1 현행 실측(r1 D7). 바라는 결과는 잴 수 있는 문장으로 쓴다. 예: 관리자가 코드 수정 없이 강의 1건을 개설·배정·코드 발급하고, 수강생이 코드와 이메일로 입장해 강의안을 연다 |
| [`docs/process/intents/2026-10-21-phase1-backend.md`](../process/intents/2026-10-21-phase1-backend.md) | new | D1 | feature. r3 §2 가정 · §7 열린 질문 · 부록 A3(시안 전용 5종 1차 제외) · A5(공개홈은 API 만) · r1 B3 "명시적으로 빼는 것" |
| [`docs/process/research/2026-10-21-mockup-review.md`](../process/research/2026-10-21-mockup-review.md) | new | D1 | r3 부록 A1~A5 를 옮긴다(A6 은 ADR-001). 머리말 `type: Research` |
| [`docs/process/spec.md`](../process/spec.md) | new | D2 | SDLC §6.4 틀 4절. 아래 "spec.md 내용" |
| [`docs/process/2026-10-21-phase1-backend-design.md`](../process/2026-10-21-phase1-backend-design.md) | new | D2 | Design 정본. r3 §4 결정 · 부록 C ERD · 부록 D 공통 규칙(r1 B0~B2 와 다르면 r3). 규칙표에 **T 열**. 엔드포인트는 적지 않는다(OpenAPI 정본, r3 §4). 부록에 r3 A4 "규칙 ↔ 시험 이름" 대응표(열 규칙·T·시험 이름, 이름은 r3 부록 D 규약과 부록 B 시험 세부) |
| [`docs/process/adr/ADR-001-mockups.md`](../process/adr/ADR-001-mockups.md) | new | D2 | r3 §4 ADR-001 행 + 부록 A6(C1 참고 자료로만, C2·C3 기각). 머리말 `type: ADR` |
| [`docs/process/adr/ADR-004-public-home.md`](../process/adr/ADR-004-public-home.md) | new | D2 | r3 §4 ADR-004 행 + 부록 A5 + §7-1(H-1 답에 따라 다시 본다). 머리말 `type: ADR` |
| [`docs/process/plan.md`](../process/plan.md) | new | D3 | SDLC §6.4 틀. 1 규칙(r3 §5.1 한 바퀴) · 2 단계와 레인(1인, 레인 A) · 3 순서표 13행 T0a(완료, merge `181006e`)·T0b·T1·T2a·T2b·T3~T8·T9a·T9b. 열은 선행·관문 요약(r3 §5.2)·마이그레이션(부록 C 0002~0011)·계획 파일·상태 |
| [`docs/process/agent.md`](../process/agent.md) | new | D3 | SDLC §6.4 틀. 승인자 `DAMIEN-PARK`. 편성표는 빌더 세션·팀 워커·verifier·reviewer(다른 세션)·CI(GitHub Actions, master push·PR). "하지 않는 것"은 승인(approve 커밋·승인 트레일러) · master 직접 변경(병합·push·reset) · 사용자 미커밋 변경 건드리기(checkout·restore·stash 포함) · 테스트 약화 · 정책 완화 · 운영 배포 |
| `scripts/check_docs.sh` | new, +x | D4 | r3 E-7·E-9. 아래 "check_docs.sh 검사" |

**spec.md 내용 (D2)**

| 절 | 채울 것 (출처) |
|---|---|
| 1 정본 색인 | §6.4 열에 `위치`(저장소 · 외부)와 `sha256`(외부만)을 더한다. 행은 기획안 v3(제품 정본, 외부) · 파이프라인 v3(외부) · 시안 3종(외부, 참고, 정본 아님) · 요구정의서(검토용 요구 목록, 정본 아님) · Design · ADR-001~004 · plan · agent · intent 2장 · research 다. sha 는 위 확인값을 쓰기 직전에 다시 재서 같을 때만 적는다 |
| 2 정책 대조표 | r3 원칙 ①~⑤ + 기획안 원칙 2(수강생 문은 초대코드 하나)·5(준비 중 카드)·10(응답 비연결)·12(실고객사명 금지)·13(관리자가 개설·배정). "어디에 코드로" 칸은 지금 있는 장치(gate · banned-api · deny-deps · deny-approval · check_task_order · merge_task · okf guard · check_docs · conftest 가드 · ADR)를 적는다. 코드가 아직 없으면 `예정: T<n> + 시험 이름`(Design 대응표)으로 적는다. 빈칸은 0 이다 |
| 3 우려 | r3 A2 데이터 계약 차이 11건 · A3 시안 전용 5종 · §2 가정 7(기획안 내부 모순, r1 가정 11) · 요구정의서 §10 DEC-001~016 요약(행마다 한 줄 + 요구정의서 §10 링크) |
| 4 변경 규칙 | §6.4 틀 그대로. 외부 정본이 바뀌면 같은 커밋에서 색인 sha 를 고친다 |

**check_docs.sh 검사 (D4).** 마지막 줄이 `docs check: OK` 면 exit 0, 위반은 exit 1 이다. master 참조가 없으면 exit 2(못 쟀다)이고, 참조 순서는 `check_task_order.sh` 처럼 master → origin/master 다. exit 2 는 pre-push 가 경고만 하고 push 를 막지 않는다(check_task_order 와 같은 정책, r3 E10). 파이프는 `pipefail` 로 돌린다. 검사는 표의 백틱 글자를 읽는다. link 가 표를 링크로 감싸도 백틱 글자는 링크 글 안에 남으므로 결과가 같아야 한다(OKF §8-11, 작업 순서 9번에서 다시 돌린다).

| # | 검사 | 실패 조건 |
|---|---|---|
| ① | spec 1절 색인의 `위치=저장소` 행 경로마다 `test -e` | 없는 경로 |
| ② | `위치=외부` 행의 sha256 대조 | `CLASSFIT_REQUIRE_EXTERNAL=1` 일 때만 실패한다. 아니면 `외부 정본 검사 건너뜀` 을 찍고 넘어간다(r3 N8) |
| ③ | spec 2절 대조표 "어디에 코드로" 칸 | 빈칸·`-`·`—` 가 하나라도 있음 |
| ④ | Design 대응표에서 master first-parent 에 `merge: T<n>` 이 있는 T 의 행만 본다. 시험 이름마다 `tests/` 에 `def <이름>` 이 있어야 한다(`_` 로 끝나면 접두) | 없는 시험. T0b 시점은 대상 0행이다(T0a 행 없음) |

**그룹 E — OKF 1~7단계 + 잔여 (r3 E5·E6, worker-e)**

| 경로 | 종류 | 단계 | 한 줄 이유 (출처) |
|---|---|---|---|
| `requirements-dev.in` | modify | E1 | `pyyaml` 한 줄(착수 조건) |
| `requirements-dev.txt` | modify | E1 | `make lock` 산출물. `requirements.txt` 는 diff 0 이어야 한다. 바뀌면 멈추고 보고한다 |
| `scripts/okf/okf.py` | new | E1 | BHQ 원본을 `cp` 로 그대로 둔다(수정 0) |
| `scripts/okf/okf.py.sha256` | new | E1 | 해시 64자 한 줄만(E-5) |
| `pyproject.toml` | modify | E1 | ruff `extend-exclude` 에 `"scripts/okf"`(그대로면 ruff 9건, Architect 재현) |
| `docs/okf.toml` | new | E1 | 아래 "okf.toml" |
| [`docs/requirements/2026-10-21-요구정의서.md`](../requirements/2026-10-21-요구정의서.md) | modify | E2·E3 | label 이 머리말(`type: Requirements`·H1 제목·파일 이름의 날짜)을 새로 만든다. 본문은 §1.1 근거 표 P1 행의 링크 1개만 바꾼다(위험 표 5행) |
| docs 문서들의 백틱 이름 | modify | E3 | link 가 백틱 이름을 상대 경로 링크로 감싼다. 글자는 그대로다. T0a 문서와 이 계획도 포함된다 |
| docs 의 목차 파일 7개 | new | E4 | index 가 만드는 자동 목차(뿌리·plans·process·process/adr·process/intents·process/research·requirements) |
| `scripts/okf/guard.sh` | new, +x | E6 | OKF §7.2 원문 + 맨 앞에 `okf.py` sha256 을 `okf.py.sha256` 과 대조해 다르면 exit 1 |
| `.githooks/pre-commit` | modify | E6 | master 직접 커밋 차단은 그대로 둔다. `git diff --cached --name-only -- docs` 가 비어 있지 않을 때만 `OKF_PYTHON=.venv/bin/python bash scripts/okf/guard.sh docs`(OKF §7.3, r3 E6) |
| `Makefile` | modify | E6 | `okf` = `OKF_PYTHON=$(BIN)/python bash scripts/okf/guard.sh docs`, `verify` 맨 끝(test 다음)에 okf(r3 E9), `check-docs` 타깃. 머리 주석·`.PHONY` 갱신. 같은 파일을 두 워커가 고치지 않게 worker-e 가 맡는다 |
| `.github/workflows/ci.yml` | modify | E6·E8 | gates 잡 마지막에 `make okf` · `bash scripts/check_docs.sh`(변수 없이, 건너뜀 출력). 두 잡의 checkout v4→v5, setup-python v5→v6. PyYAML 은 `make install` 이 requirements-dev 로 깐다(OKF §7.3 조각의 `pip install pyyaml` 대신). 이 단계들의 첫 실행은 병합 뒤 첫 master push 의 CI 이고, 결과는 증명 기록 칸에 적는다(E-15) |
| `.githooks/pre-push` | modify | E6 | check_task_order 뒤에 `make okf` · `CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh`(r3 E9). check_docs 의 exit 2(못 쟀다)는 check_task_order 처럼 경고만 하고 push 를 막지 않는다(E10). T2a golden 주석은 남긴다 |
| `CLAUDE.md` | modify | E7 | Commands 에 OKF 한 줄(OKF §6 7단계 문구 + `okf()` 함수 + `make okf`·`check_docs`)을 더하고 verify 순서에 okf 를 넣는다. Rules 에 "새 docs 문서는 틀에서 시작해 머리말 `type` 을 단다 · CI 체크아웃에 없는 경로(미추적·gitignore·저장소 밖)는 링크 대신 백틱 글자로 쓴다". 3행의 "T0b 에서 생긴다" 문장을 고친다 |
| `scripts/test_gate.sh` | modify | E8 | nit 4. ② 를 ruff 전용과 gate 전용으로 나누고 hook 층 3건을 더한다(아래 표) → `음성 8/8 OK · 양성 3/3 OK` |
| `.claude/hooks/test_hooks.sh` | modify | E8 | nit 4. 9번을 "승인 제목만 차단"(`approve: T1` 빈 커밋)과 "트레일러만 차단"(`T1: …` + 트레일러) 둘로 나눈다 → `11/11 OK`. 머리 주석의 `10/10 OK` 를 `11/11 OK` 로, 분배를 deny-approval 3(차단 2·허용 1)으로 고친다 |
| `scripts/gate.sh` | modify | E8 | nit 5. 금지 용어는 주석·빈 줄을 뺀 임시 파일로 `grep -rnoiF -f` 한다. grep rc 2 는 `GATE FAIL` 이다. 있는 경로만 넘긴다. "용어가 경로 이름에 들면 file:line 의 경로로 드러난다(실측 docs/acmesecret-dir/n.md:1)" 주석을 단다 |
| `scripts/check_secrets.sh` | modify | E8 | 맞은 줄 내용을 찍지 않고 `file:line` 만 찍는다(2026-10-21 비밀번호가 터미널에 찍힌 실측). 허용 필터(`@localhost`)는 계속 줄 내용으로 판정하고 출력만 자른다 |

**okf.toml (E1).** OKF §5.2 템플릿 + r3 E7 목록 + `requirements/*` 다. 규칙은 폴더 먼저, 이름 꼴 다음이다(OKF §5.3). "나머지 전부" 규칙은 두지 않는다.

| 칸 | 값 |
|---|---|
| `okf_version` · `spec_commit` · `spec_commit_date` | `"0.2"` · 위 확인값 · `"2026-08-21"` |
| `bundle_name` · `exclude_dirs` | `"docs"` · `["process/templates"]` |
| `stop_names` | README.md · CLAUDE.md · AGENTS.md · SKILL.md · index.md · log.md |
| `rules` (위부터) | `process/intents/*` Intent · `process/adr/*` ADR · `process/research/*` Research · `plans/README.md` Readme · `plans/T*` Task Plan · `runbooks/*` Runbook · `requirements/*` Requirements · `process/intent.md` Intent · `process/spec.md` Spec · `process/plan.md` Plan · `process/agent.md` Agent Guide · `process/*-design.md` Design. `plans/T*` 는 r3 E7 그대로다. `plans/*` 보다 좁아서 README 도 계획도 아닌 새 파일이 생기면 도구가 멈춘다 |
| `no_link` · `external_roots` | 처음엔 비운다. 문장 판정에서 틀린 링크가 나오면 `no_link` 에 적는다. 묶음 밖은 잇지 않는다 |

**test_gate.sh 사례 (E8)**

| 층 | 음성 (막혀야 함) | 양성 (통과해야 함) |
|---|---|---|
| ruff TID251 | `import asyncpg` · `import langchain_openai` | 깨끗한 사본(gate 와 같이 잰다) |
| gate.sh | `import langchain_foo`(ruff 는 통과해야 함) · requirements 행 `asyncpg` · `langchain-openai==0.2` · `langchain_openai==0.2` | `langchain-core==0.3` 행 + `import langchain_core`(ruff 와 같이 잰다) |
| hook deny-deps.sh | Write `import asyncpg` · Edit requirements.in `langchain-openai==0.2` → exit 2 | Edit requirements.in `langchain-core==0.3` + `import langchain_core` → exit 0 |

바꾸지 않는 것: `alembic.ini` · 루트 `README.md` · `memo.md` · `.env` · `src/`·`tests/`·`alembic/`(시험 추가 없음) · `.claude/settings.json` · `docs/process/templates/*` · merge_task·sync_task·check_task_order·task_order_base · 미추적 `기획/`·`시안/`·`공개홈_v24.html`(sha 만 읽는다) · BHQ 원본(읽기만).

## 작업 순서

커밋은 묶음마다 파일을 지정해서 하고, 메시지는 `-F` 파일로 넘긴다(deny-approval 훅이 명령 문자열의 승인 낱말을 막는다). `git add -A`·`git add .`·`git commit -a` 는 쓰지 않는다. 같은 작업 트리에서 두 워커가 커밋하므로 `git commit -F <메시지 파일> -- <경로…>` 로 자기 파일만 담는다(새 파일은 먼저 `git add <경로>`). OKF 명령은 함수로 부른다(OKF §8-10): `okf() { .venv/bin/python scripts/okf/okf.py --root docs --config docs/okf.toml "$@"; }`

**E0 계획과 승인**
1. 에이전트: 가지 `T0b-sdlc-okf` 에서 이 파일만 스테이징해 `plan: T0b sdlc-okf` 로 커밋한다. 트레일러는 없다.
2. 승인자: approve 빈 커밋을 더한다. 이것이 pyyaml 승인이다. 그 전에는 아래를 시작하지 않는다.

**병렬 — worker-d(D1~D4)와 worker-e(E1·E8)**
3. D1 intent 2장·research → D2 spec·Design·ADR-001·004 → D3 plan·agent → D4 check_docs.sh. CI 체크아웃에 없는 경로(미추적 `기획/`·`시안/`, gitignore `.omc/`, 저장소 밖)는 손으로 링크를 쓰지 않고 백틱 글자로 쓴다(CI 에서 깨진 링크가 된다). 일반 개념으로 파일 이름을 쓸 때는 백틱을 쓰지 않는다(OKF §8-1). 관문: SDLC §5 4단계 관문인 색인 실재(check_docs ①)와 대조표 빈칸 0(③)을 check_docs 가 잰다. `CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh` → `docs check: OK`, 변수 없이 → `외부 정본 검사 건너뜀` 줄 뒤 `docs check: OK`.
4. E1 `requirements-dev.in` 에 pyyaml → `make lock` → `make install` → `.venv/bin/python -c 'import yaml'` exit 0 → okf.py 복사 · sha 파일 · ruff 제외 · `docs/okf.toml`. 관문: E-5 `okf-copy-ok` · `make lint` → `All checks passed!` · `git diff --stat requirements.txt` 빈 출력.
5. E8 test_gate · test_hooks · gate · check_secrets · ci.yml 액션 판. 관문: `음성 8/8 OK · 양성 3/3 OK` · `11/11 OK` · `make gate` → `gate: OK`.

**worker-e(E2~E7) — 동기화 지점 뒤.** worker-d 가 D1~D4 를 커밋하고 리드에게 알린 뒤 시작한다. 그 뒤로 docs 에 새 초안을 두지 않는다(guard 는 작업 트리를 본다).
6. E2 `okf label` 미리 보기가 멈추지 않아야 한다(규칙이 모든 문서를 덮는다는 뜻). 그다음 `okf label --apply`. 요구정의서 1건이 "머리말 새로 만듦"이다. 관문: 다시 `okf label` → `요약: {'같음': 15}`(기존 6 + 그룹 D 9).
7. E3 link. ① `okf link` 미리 보기 ② 스크래치에 docs 사본을 만들고 `--root <사본> --workspace "$PWD"` 로 `--apply` ③ `diff -r docs <사본>` 을 다른 세션 verifier 에게 넘긴다. verifier 는 새 링크마다 앞뒤 문장을 읽고 "문장이 말하는 문서 = 대상"인지 판정한다 ④ 틀린 것은 `no_link` 에 적고 ②부터 다시 ⑤ 잘못 0 이면 원본에 `--apply` 하고 사본과 `diff -r` 0 ⑥ 요구정의서 P1 행 링크를 백틱 글자로 바꾼다(위험 표 5행). 관문: 문장 판정 "잘못 0"(OKF §6 3단계). 기계 검사만으로는 이 관문을 못 넘는다.
8. E4 `okf index --apply`. 관문: 다시 `okf index` → `목차 0개 만들 것 · 같음 7개`. 새 목차 파일을 가리키는 글자가 있으면 link 할 일이 다시 생기므로 `okf link` 미리 보기가 `바뀌는 문서 0개` 인지 본다(스크래치 실측: 목차 경로를 백틱으로 쓴 문서 1개가 걸렸다).
9. E5 `okf check --strict`. 관문: E-4 `위반 0건 — 통과`(외톨이는 위반이 아니다). 이어서 check_docs 를 다시 돌려 link 뒤에도 `docs check: OK` 인지 본다.
10. E6 guard.sh → Makefile → ci.yml → pre-push 순서로 고치고, **pre-commit 은 마지막**에 고친다. core.hooksPath 가 걸려 있어 저장하는 순간 커밋에 걸리기 때문이다. 관문: `make okf` → `OKF guard OK`. guard 관문 3종은 12번에서 본다.
11. E7 CLAUDE.md. 관문(OKF §6 7단계): 새 세션에게 "계획서 하나 써 줘"라고 시키면 커밋 전에 네 명령을 돌리거나 guard 가 막는다. 결과는 증명 기록 칸에 적는다.

**통합과 마무리**
12. `make verify` exit 0, 마지막 줄 `OKF guard OK`. 이어서 guard 관문(OKF §6 6단계의 통과·차단·삭제 3종, r3 E6)을 본다. 덤으로 docs 없는 커밋은 OKF 줄 없이 통과하는지 본다.
    1. 정상 docs 문서를 고쳐 커밋한다(예: 이 계획의 "계획과 다르게 한 것" 갱신). pre-commit 이 `OKF guard OK` 를 찍고 커밋된다.
    2. 머리말 없는 임시 `docs/plans/T0b-guard-probe.md` 를 스테이징해 커밋하면 `OKF: type 이 없는 문서가 있다` 로 막힌다. `Permission denied`·`PyYAML 이 없거나` 로 막히면 통과가 아니다. 확인 뒤 `git restore --staged` 하고 그 파일을 지워 `git status --porcelain docs` 가 빈 출력인지 본다.
13. 다른 세션의 reviewer 가 "리뷰" 절을 쓰고 Important 0 이 될 때까지 고친다(r3 §5.1-3). verifier 가 "증명" 명령을 다시 돌린다.
14. 승인자(Claude 밖 터미널): `bash scripts/merge_task.sh T0b-sdlc-okf` → master 에 `merge: T0b sdlc-okf` → `git push origin master`. 이 push 의 CI 가 okf·check_docs 단계와 checkout@v5·setup-python@v6 를 처음 돌린다. 결론을 증명 기록 칸에 적는다(E-15).

## 위험

| 위험 | 알아채는 법 | 완화 (출처) |
|---|---|---|
| guard 는 스테이징이 아니라 작업 트리를 본다 | pre-commit 메시지 | docs 커밋 전에 다른 초안을 치운다. CI 에서 한 번 더 돈다(OKF §7.2 한계, r3 부록 F) |
| link 가 같은 글자 다른 뜻을 잇는다 | verifier 문장 판정 | 사본 → `diff -r` → 다른 세션 판정 → `no_link`. 판정 없이 원본에 `--apply` 하지 않는다(OKF §8-1·§6 3단계) |
| okf.py 사본이 lint 를 깨거나 원본과 어긋난다 | `make lint` · E-5 · guard 첫 검사 | ruff 제외 + sha 파일 대조(r3 부록 F) |
| label 이 사용자 문서(요구정의서)에 머리말을 만든다 | `git diff master -- docs/requirements/` | 본문은 그대로 두고 머리말 줄(`---`·type·title·date·`---`)과 빈 줄만 더한다. 리뷰 절과 "계획과 다르게 한 것"에 적는다 |
| 요구정의서 §1.1 P1 행(원래 34행) 링크는 `.omc/plans/…r3.md`(gitignore)를 가리킨다. 로컬은 통과하지만 CI 체크아웃에는 그 파일이 없어 `check --strict`·`make okf` 가 깨진 링크 1개로 실패한다(2026-10-21 스크래치 실측, exit 1) | 임시 clone 에서 `okf check --strict`(증명) | 그 링크 하나를 같은 경로의 백틱 글자(로컬 전용 표시)로 바꾼다. 사용자 문서 본문의 유일한 변경이고 이 계획 승인에 포함된다. 승인자가 빼라고 하면 그대로 두고, 병합 뒤 첫 master CI 의 okf 단계 실패를 그때 처리한다 |
| PyYAML 없는 파이썬으로 guard 가 돌면 docs 커밋이 전부 막힌다. pyyaml 설치 전에 pre-commit 을 걸었거나, `OKF_PYTHON` 이 빠져 맨 python3 로 갔을 때다 | `PyYAML 이 없거나` 메시지 | E1 이 pyyaml 을 먼저 깔고 pre-commit 은 E6 의 마지막에 고친다. pre-commit 은 `OKF_PYTHON=.venv/bin/python`, Makefile 은 `$(BIN)/python` 을 넘긴다(OKF §8-6) |
| 건드리면 안 되는 md 를 도구가 고친다 | `git diff` · check_docs 재실행 | 틀은 `exclude_dirs` 로 뺀다. CLAUDE.md·REVIEW.md 는 docs 묶음 밖(루트)이다. spec.md 는 check_docs 가 읽으므로 link 뒤 작업 순서 9번에서 check_docs 를 다시 돌린다(OKF §8-3) |
| 다른 세션이 문단을 다시 쓰면 링크가 보통 글자로 풀려 guard 가 막는다 | guard `링크로 안 감싼 참조가 있다` | 같은 문서를 두 세션이 동시에 고치지 않는다(레인 소유). 막히면 `link --apply` 뒤 `git diff` 로 새 링크의 앞뒤 문장을 읽는다(OKF §8-13·§7.2 한계) |
| `make lock` 이 `requirements.txt` 판을 바꾼다 | `git diff --stat requirements.txt` | 빈 출력이어야 한다. 바뀌면 멈추고 보고한다(판 올리기는 승인 범위 밖) |
| CI 변경(okf·check_docs 단계, 액션 판, 러너의 `shasum`)은 병합 전에 돌지 않는다. CI 는 master push·PR 에만 걸리고 에이전트는 push 하지 않는다 | 병합 뒤 첫 master push 의 CI 결론 | 그 결과를 증명 기록 칸에 적는다(E-15). 그 전에는 임시 clone 의 `okf check --strict` 로 근사한다 |
| 외부 정본 sha 는 로컬에서만 잴 수 있다(`기획/`·`시안/` 미추적) | CI 출력 `외부 정본 검사 건너뜀` | pre-push 만 `CLASSFIT_REQUIRE_EXTERNAL=1` 이다. 사용자가 기획안을 고치면 pre-push 가 막는다 → spec 4절대로 색인 sha 를 고친다(r3 N8) |
| 목차는 문서 추가·제목·설명이 바뀔 때마다 낡는다 | guard `목차가 낡았다` | 의도한 강제다. 새 계획 파일마다 `index --apply` 를 돌린다(CLAUDE.md 한 줄) |
| 금지 용어 grep 의 rc 2 를 실패로 바꾸면 없는 경로 하나로 gate 가 빨개진다 | test_gate 양성 · `make gate` | 있는 경로만 넘긴다. 목록이 비어 있는 지금은 grep 을 부르지 않는다 |
| 두 워커가 같은 파일을 고친다 | `git status` · 커밋 diff | 레인 소유 파일("바뀌는 파일" 머리). label·link·index 는 그룹 D 커밋 뒤 worker-e 만 돌린다 |
| iCloud dataless 파일 때문에 읽기가 EDEADLK 로 실패한다 | `Resource deadlock avoided` | venv 는 2026-10-21 에 다시 만들었다. 다시 나면 재시도하고, verifier 는 스크래치 venv 로 잰다(T0a "계획과 다르게 한 것" 10) |

## 증명

r3 §6 의 명령과 기대 출력이다. E-2·E-6 은 이 계획이 문구를 고쳤고, E-3 은 T0b 시점 값이다.

```bash
bash scripts/check_task_order.sh                    # E-1 → "task order: OK"
bash .claude/hooks/test_hooks.sh                    # E-2(T0b 갱신) 9번을 승인 제목·트레일러 둘로 → "11/11 OK"
make verify                                         # E-3 exit 0, "gate: OK"·"All checks passed!"·"Contracts: 2 kept, 0 broken."(② 는 T1)·"passed"(failed·error·skipped 0)·마지막 "OKF guard OK"
okf() { .venv/bin/python scripts/okf/okf.py --root docs --config docs/okf.toml "$@"; }
okf check --strict                                  # E-4 → "위반 0건 — 통과"
okf label                                           # 재실행 → "요약: {'같음': 15}"
okf index                                           # 재실행 → "목차 0개 만들 것 · 같음 7개"
test "$(shasum -a 256 scripts/okf/okf.py | cut -d' ' -f1)" = "$(cat scripts/okf/okf.py.sha256)" && grep -q '"scripts/okf"' pyproject.toml && echo okf-copy-ok   # E-5
bash scripts/test_gate.sh                           # E-6(T0b 갱신) ruff·gate·hook 세 층 → "음성 8/8 OK · 양성 3/3 OK"
CLASSFIT_REQUIRE_EXTERNAL=1 bash scripts/check_docs.sh   # E-7·E-9 → "docs check: OK"
bash scripts/check_docs.sh                          # CI 모양 → "외부 정본 검사 건너뜀" 줄 + "docs check: OK"
gh run list -b master -L 1 --json conclusion -q '.[0].conclusion'      # E-15 병합 뒤 첫 master push → "success"
```

여기에 작업 순서 12번의 guard 관문 3종을 더한다. 또 `.omc`·`기획/`·`시안/` 이 없는 임시 clone 에서 원본 `.venv/bin/python` 으로 `okf check --strict` 를 돌려 `위반 0건 — 통과` 를 본다(CI 근사, 위험 표 5행).

| 기록 칸 | 값 |
|---|---|
| okf.py sha256 (64자) | `b8bfb796f0deade6bcda93370f7df27c0945aa56fba01f68f68c8060216a2f3c` — 2026-10-21 원본 측정. 사본은 E-5 로 확인 |
| 문장 판정 (verifier 세션 · 날짜 · 새 링크 수 · 잘못 · 애매) | |
| guard 관문 출력 원문 (정상 커밋 · 차단 메시지 · docs 없는 커밋) | |
| 요구정의서 diff (머리말 줄 수 · 링크 감싸기 · P1 행) | |
| `git diff --stat requirements.txt` | |
| CI: 임시 clone 의 `okf check --strict` · 병합 뒤 첫 master push CI(gates 의 okf·check_docs 단계, test 잡, 결론) | |
| trust 재수락 여부 | settings.json 은 바꾸지 않는다. 새 세션에서 재수락을 요구했는지 적는다 |
| OKF §6 7단계 새 세션 시험 | |

## 리뷰

(다른 세션의 reviewer 가 쓴다. Important n건 · Nit n건, 소견과 고친 커밋. Important 0 이 될 때까지 고친다 — r3 §5.1-3)

## 계획과 다르게 한 것

(구현 중 채운다. 비어 있으면 계획대로다.)




---

# Resources

- 플랜 r3 `.omc/plans/2026-10-21-classfit-phase1-r3.md` · r1(D7 표) `.omc/plans/2026-10-21-classfit-phase1.md` · 팀 핸드오프 `.omc/handoffs/team-plan-t0b.md`·`team-exec-phase2.md`(저장소 루트 기준, gitignore 라 git 에 남지 않음)
- 안내서(저장소 루트): OKF `2026-10-21-okf-sdlc-porting-guide.md` · SDLC `2026-10-06-ai-native-sdlc-porting-guide.md` · okf.py 원본 `/Users/damienpark/Desktop/BHQ/plan/scripts/okf/`(읽기만)
- OKF 규격: https://github.com/GoogleCloudPlatform/open-knowledge-format (`SPEC.md` @ `0b87c52c6ef9`, 2026-08-21)
